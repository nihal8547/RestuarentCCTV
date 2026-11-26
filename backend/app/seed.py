"""Seeds 7 days of plausible history so the Weekly Analytics tab is populated on first run.
Rows are flagged is_demo=1. Disable with SEED_DEMO_DATA=0 (production)."""
from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .db import Database

# relative demand by hour (lunch + dinner peaks, Gulf-style late evening)
HOUR_WEIGHT = {11: .3, 12: .8, 13: 1.0, 14: .6, 15: .2, 16: .15, 17: .25, 18: .5,
               19: .8, 20: 1.0, 21: .95, 22: .6, 23: .25}
DAY_FACTOR = {0: .8, 1: .75, 2: .85, 3: .95, 4: 1.25, 5: 1.2, 6: 1.0}  # Fri/Sat busiest


def seed_history(db: Database, tz_name: str, table_ids: list[str]) -> None:
    if db.count_sessions() > 0:
        return
    rnd = random.Random(42)
    tz = ZoneInfo(tz_name)
    today = datetime.fromtimestamp(time.time(), tz).replace(hour=0, minute=0, second=0, microsecond=0)
    rows, alerts = [], []
    for back in range(7, 0, -1):
        day = today - timedelta(days=back)
        factor = DAY_FACTOR[day.weekday()]
        busy_until = {t: 0.0 for t in table_ids}
        for hour, w in HOUR_WEIGHT.items():
            n_parties = int(rnd.gauss(len(table_ids) * 1.3 * w * factor, 0.6))
            for _ in range(max(0, n_parties)):
                start = day.replace(hour=hour, minute=rnd.randint(0, 59), second=rnd.randint(0, 59)).timestamp()
                free = [t for t in table_ids if busy_until[t] <= start]
                if not free:
                    continue
                t = rnd.choice(free)
                guests = rnd.choices([1, 2, 3, 4], [.1, .42, .25, .23])[0]
                dwell = rnd.gauss(52, 14) * 60
                dwell = max(20 * 60, min(95 * 60, dwell))
                end = start + dwell
                busy_until[t] = end + 5 * 60
                first_visit = start + rnd.choice([rnd.uniform(40, 200), rnd.uniform(40, 200), rnd.uniform(310, 480)])
                cleaned = end + rnd.choice([rnd.uniform(25, 90), rnd.uniform(25, 90), rnd.uniform(130, 260)])
                rows.append((t, start, end, guests, first_visit, 2, cleaned, 1))
                if first_visit - start > 300:
                    alerts.append((first_visit - 1, "service_wait", t, "warning",
                                   f"Table {int(t[1:]):02d}: guests waited 05:00 with no waiter visit", first_visit, 1, 1))
                if cleaned - end > 120:
                    alerts.append((end + 120, "uncleaned_table", t, "warning",
                                   f"Table {int(t[1:]):02d} left uncleaned for 02:00 - bussing needed", cleaned, 1, 1))
    db.executemany(
        "INSERT INTO sessions(table_id,start_ts,end_ts,guests,first_visit_ts,visits,cleaned_ts,is_demo) "
        "VALUES (?,?,?,?,?,?,?,?)", rows)
    db.executemany(
        "INSERT INTO alerts(ts,kind,table_id,severity,message,resolved_ts,acked,is_demo) VALUES (?,?,?,?,?,?,?,?)",
        alerts)
