"""Multi-restaurant hub.

Edge (each restaurant): set HUB_URL + HUB_KEY -> HubPusher posts a small summary every few seconds
(counts, table states, active alerts, camera health). No video ever leaves the restaurant.
Hub (central server): set HUB_ENABLED=1 -> /api/hub/* endpoints store venues and their latest summary.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
import time
import urllib.request

log = logging.getLogger("hub")


def make_api_key() -> str:
    return "vk_" + secrets.token_urlsafe(24)


def summarize(snapshot: dict, kpis: dict | None = None) -> dict:
    r = snapshot.get("restaurant", {})
    alerts = [a for a in snapshot.get("alerts", []) if not a["resolved"]]
    return {
        "restaurant": r,
        "tables": [{"id": t["id"], "state": t["state"], "guests": t["guests"], "timer": t["timer"]}
                   for t in snapshot.get("tables", [])],
        "active_alerts": [{"kind": a["kind"], "table": a["table"], "message": a["message"], "ts": a["ts"]}
                          for a in alerts][:10],
        "cameras": snapshot.get("cameras", []),
        "kpis": kpis or {},
    }


class HubPusher(threading.Thread):
    def __init__(self, settings, pipeline, kpi_fn):
        super().__init__(daemon=True, name="hub-pusher")
        self.s, self.pipe, self.kpi_fn = settings, pipeline, kpi_fn
        self._stop_ev = threading.Event()

    def stop(self):
        self._stop_ev.set()

    def run(self):
        last_kpi, kpis = 0.0, {}
        while not self._stop_ev.wait(5):
            try:
                snap = self.pipe.get_snapshot()
                if not snap:
                    continue
                if time.time() - last_kpi > 300:
                    kpis, last_kpi = self.kpi_fn(), time.time()
                body = json.dumps(summarize(snap, kpis)).encode()
                req = urllib.request.Request(f"{self.s.hub_url}/api/hub/ingest", data=body, method="POST",
                                             headers={"Content-Type": "application/json", "X-Venue-Key": self.s.hub_key})
                urllib.request.urlopen(req, timeout=8).read()
            except Exception as e:
                log.warning("hub push failed: %s", e)
