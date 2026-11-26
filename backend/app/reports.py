"""Weekly manager report: PDF + text summary, plus a scheduler that pushes it (webhook/Telegram)."""
from __future__ import annotations

import io
import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

log = logging.getLogger("reports")


def build_text(r: dict, name: str) -> str:
    k = r["kpis"]
    worst = max(r["service"]["by_table"], key=lambda t: t["service_alerts"] + t["cleaning_alerts"], default=None)
    lines = [
        f"📊 Weekly report · {name}",
        f"{r['range']['from']} → {r['range']['to']}",
        "",
        f"👥 Guests: {k['total_guests']}  ·  Parties: {k['total_parties']}  (avg {k['avg_party_size']})",
        f"⏰ Peak hour: {k['peak_hour']}  ·  Busiest day: {k['busiest_day']}",
        f"🔄 Turns/table/day: {k['turns_per_table_per_day']}  ·  Avg table time: {k['avg_dwell_min']} min",
        f"🧹 Clean turnaround: {k['avg_clean_turnaround_min']} min  ·  First waiter visit: {k['avg_first_visit_wait_min']} min",
        f"🚨 Alerts: {r['alerts']['by_kind'].get('service_wait', 0)} service, "
        f"{r['alerts']['by_kind'].get('uncleaned_table', 0)} cleaning",
    ]
    if worst and (worst["service_alerts"] + worst["cleaning_alerts"]):
        lines.append(f"⚠️ Most alerts: {worst['table']} ({worst['service_alerts']} service / "
                     f"{worst['cleaning_alerts']} cleaning)")
    return "\n".join(lines)


def _table(data, col_widths=None):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def build_pdf(r: dict, name: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title=f"Weekly report - {name}")
    st = getSampleStyleSheet()
    h1, h2, body = st["Heading1"], st["Heading2"], st["BodyText"]
    k = r["kpis"]
    el = [Paragraph(f"Weekly Manager Report - {name}", h1),
          Paragraph(f"{r['range']['from']} to {r['range']['to']} ({r['range']['tz']})", body), Spacer(1, 6)]

    el.append(_table([
        ["Guest footfall", "Parties", "Avg party", "Peak hour", "Busiest day"],
        [k["total_guests"], k["total_parties"], k["avg_party_size"], k["peak_hour"], k["busiest_day"]],
        ["Turns / table / day", "Avg table time", "Clean turnaround", "First waiter visit", "Alerts"],
        [k["turns_per_table_per_day"], f"{k['avg_dwell_min']} min", f"{k['avg_clean_turnaround_min']} min",
         f"{k['avg_first_visit_wait_min']} min", r["alerts"]["total"]]]))
    el.append(Spacer(1, 10))

    el.append(Paragraph("Peak hours (avg guests seated per hour)", h2))
    hours = [h for h in r["hourly"] if 10 <= h["hour"] <= 23]
    d = Drawing(170 * mm, 55 * mm)
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 10, 12, 160 * mm - 10, 42 * mm
    bc.data = [[h["guests"] for h in hours]]
    bc.categoryAxis.categoryNames = [str(h["hour"]) for h in hours]
    bc.categoryAxis.labels.fontSize = 7
    bc.valueAxis.labels.fontSize = 7
    bc.bars[0].fillColor = colors.HexColor("#38bdf8")
    bc.valueAxis.valueMin = 0
    d.add(bc)
    el += [d, Spacer(1, 4)]

    el.append(Paragraph("Daily footfall", h2))
    el.append(_table([["Day", "Guests", "Parties", "Avg table time (min)", "Turns / table"]] +
                     [[x["label"], x["guests"], x["parties"], x["avg_dwell_min"], x["turns_per_table"]]
                      for x in r["daily"]]))
    el.append(Paragraph("Table turnover", h2))
    el.append(_table([["Table", "Turns", "Guests", "Avg table time (min)"]] +
                     [[x["table"], x["turns"], x["guests"], x["avg_dwell_min"]] for x in r["per_table"]]))
    el.append(Paragraph("Service performance", h2))
    hdr = ["", "Parties", "1st visit (min)", "Clean turnaround (min)", "Service alerts", "Cleaning alerts"]
    rows = [hdr]
    for key, label in (("by_shift", "shift"), ("by_section", "section"), ("by_table", "table")):
        for x in r["service"][key]:
            rows.append([f"{label.title()} {x[label]}", x["parties"], x["avg_first_visit_min"], x["avg_clean_min"],
                         x["service_alerts"], x["cleaning_alerts"]])
    el.append(_table(rows))
    el.append(Spacer(1, 8))
    el.append(Paragraph("Generated automatically from CCTV analytics. Counts and timestamps only - no video or "
                        "faces are stored.", st["Italic"]))
    doc.build(el)
    return buf.getvalue()


class ReportScheduler(threading.Thread):
    """Sends the weekly report once, on the configured weekday/hour (restaurant local time)."""

    def __init__(self, settings, db, pipeline, make_report):
        super().__init__(daemon=True, name="report-scheduler")
        self.s, self.db, self.pipe, self.make_report = settings, db, pipeline, make_report
        self._stop_ev = threading.Event()

    def stop(self):
        self._stop_ev.set()

    def send_now(self) -> bool:
        r = self.make_report()
        name = self.s.restaurant_name
        pdf = build_pdf(r, name)
        return self.pipe.notifier.send_report(build_text(r, name), pdf,
                                              f"weekly-report-{r['range']['to']}.pdf")

    def run(self):
        while not self._stop_ev.wait(30):
            try:
                if not self.s.report_enabled:
                    continue
                now = datetime.now(ZoneInfo(self.s.timezone))
                today = now.date().isoformat()
                if (now.weekday() == self.s.report_weekday and now.hour == self.s.report_hour
                        and self.db.get_settings().get("last_report_date") != today):
                    self.db.set_setting("last_report_date", today)
                    ok = self.send_now()
                    log.info("weekly report %s", "sent" if ok else "skipped (no notification channel configured)")
            except Exception:
                log.exception("report scheduler failed")
