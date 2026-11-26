"""Weekly manager analytics computed from the `sessions` and `alerts` tables."""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .db import Database

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def weekly_report(db: Database, tz_name: str, table_ids: list[str], now: float | None = None,
                  table_sections: dict[str, str] | None = None) -> dict:
    tz = ZoneInfo(tz_name)
    now = now or time.time()
    today = datetime.fromtimestamp(now, tz).replace(hour=0, minute=0, second=0, microsecond=0)
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    start_ts = days[0].timestamp()

    sessions = db.sessions_since(start_ts)
    alerts = db.alerts_since(start_ts, 5000)

    per_day = {d.date().isoformat(): {"guests": 0, "parties": 0, "dwell": [], "tables": set()} for d in days}
    hourly_guests = [0] * 24
    hourly_parties = [0] * 24
    heat = {d.date().isoformat(): [0] * 24 for d in days}
    per_table = defaultdict(lambda: {"turns": 0, "guests": 0, "dwell": []})
    first_visit_waits, turnarounds, dwell_all = [], [], []

    for s in sessions:
        dt = datetime.fromtimestamp(s["start_ts"], tz)
        key = dt.date().isoformat()
        if key not in per_day:
            continue
        dwell = (s["end_ts"] - s["start_ts"]) / 60.0
        pd = per_day[key]
        pd["guests"] += s["guests"]
        pd["parties"] += 1
        pd["dwell"].append(dwell)
        hourly_guests[dt.hour] += s["guests"]
        hourly_parties[dt.hour] += 1
        heat[key][dt.hour] += s["guests"]
        pt = per_table[s["table_id"]]
        pt["turns"] += 1
        pt["guests"] += s["guests"]
        pt["dwell"].append(dwell)
        dwell_all.append(dwell)
        if s["first_visit_ts"]:
            first_visit_waits.append(s["first_visit_ts"] - s["start_ts"])
        if s["cleaned_ts"] and s["end_ts"]:
            turnarounds.append(s["cleaned_ts"] - s["end_ts"])

    def avg(xs):
        return round(sum(xs) / len(xs), 1) if xs else 0

    n_days_with_data = max(1, sum(1 for d in per_day.values() if d["parties"]))
    daily = []
    for d in days:
        k = d.date().isoformat()
        pd = per_day[k]
        daily.append({
            "date": k, "label": f"{DOW[d.weekday()]} {d.day}",
            "guests": pd["guests"], "parties": pd["parties"],
            "avg_dwell_min": avg(pd["dwell"]),
            "turns_per_table": round(pd["parties"] / max(1, len(table_ids)), 1),
        })

    hourly = [{"hour": h, "label": f"{h:02d}:00",
               "guests": round(hourly_guests[h] / n_days_with_data, 1),
               "parties": round(hourly_parties[h] / n_days_with_data, 1)} for h in range(24)]
    peak = max(hourly, key=lambda x: x["guests"])
    best_day = max(daily, key=lambda x: x["guests"])
    kinds: dict[str, int] = defaultdict(int)
    for a in alerts:
        kinds[a["kind"]] += 1

    # ---- service performance (per table / section / shift) -------------------------------------
    sec_of = table_sections or {}
    shifts = {"Lunch (11-16)": range(11, 16), "Evening (16-19)": range(16, 19), "Dinner (19-24)": range(19, 24)}

    def bucket():
        return {"waits": [], "cleans": [], "svc_alerts": 0, "clean_alerts": 0, "parties": 0}

    by_table, by_section, by_shift = defaultdict(bucket), defaultdict(bucket), defaultdict(bucket)
    for s_ in sessions:
        dt = datetime.fromtimestamp(s_["start_ts"], tz)
        if dt.date().isoformat() not in per_day:
            continue
        shift = next((n for n, r in shifts.items() if dt.hour in r), None)
        for b in (by_table[s_["table_id"]], by_section[sec_of.get(s_["table_id"], "-")]) + (
                (by_shift[shift],) if shift else ()):
            b["parties"] += 1
            if s_["first_visit_ts"]:
                b["waits"].append(s_["first_visit_ts"] - s_["start_ts"])
            if s_["cleaned_ts"] and s_["end_ts"]:
                b["cleans"].append(s_["cleaned_ts"] - s_["end_ts"])
    for a in alerts:
        if a["kind"] not in ("service_wait", "uncleaned_table"):
            continue
        dt = datetime.fromtimestamp(a["ts"], tz)
        shift = next((n for n, r in shifts.items() if dt.hour in r), None)
        field = "svc_alerts" if a["kind"] == "service_wait" else "clean_alerts"
        for b in (by_table[a["table_id"]], by_section[sec_of.get(a["table_id"], "-")]) + (
                (by_shift[shift],) if shift else ()):
            b[field] += 1

    def fmt(name_key, name, b):
        return {name_key: name, "parties": b["parties"],
                "avg_first_visit_min": round(avg(b["waits"]) / 60, 1),
                "avg_clean_min": round(avg(b["cleans"]) / 60, 1),
                "service_alerts": b["svc_alerts"], "cleaning_alerts": b["clean_alerts"]}

    service = {
        "by_table": [fmt("table", t, by_table[t]) for t in table_ids],
        "by_section": [fmt("section", k, v) for k, v in sorted(by_section.items())],
        "by_shift": [fmt("shift", n, by_shift[n]) for n in shifts],
    }

    total_guests = sum(d["guests"] for d in daily)
    total_parties = sum(d["parties"] for d in daily)
    return {
        "range": {"from": days[0].date().isoformat(), "to": days[-1].date().isoformat(), "tz": tz_name},
        "kpis": {
            "total_guests": total_guests,
            "total_parties": total_parties,
            "avg_party_size": round(total_guests / total_parties, 1) if total_parties else 0,
            "avg_dwell_min": avg(dwell_all),
            "turns_per_table_per_day": round(total_parties / max(1, len(table_ids)) / n_days_with_data, 1),
            "avg_first_visit_wait_min": round(avg(first_visit_waits) / 60, 1),
            "avg_clean_turnaround_min": round(avg(turnarounds) / 60, 1),
            "peak_hour": peak["label"] if peak["guests"] else "-",
            "busiest_day": best_day["label"] if best_day["guests"] else "-",
        },
        "hourly": hourly,
        "daily": daily,
        "heatmap": {
            "hours": list(range(24)),
            "rows": [{"date": k, "label": f"{DOW[datetime.fromisoformat(k).weekday()]} {int(k[-2:])}", "values": v}
                     for k, v in heat.items()],
        },
        "per_table": [
            {"table": t, "turns": per_table[t]["turns"], "guests": per_table[t]["guests"],
             "avg_dwell_min": avg(per_table[t]["dwell"])}
            for t in table_ids
        ],
        "alerts": {"total": len(alerts), "by_kind": dict(kinds)},
        "service": service,
    }
