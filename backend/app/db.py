"""SQLite persistence: event log, seating sessions, alerts, runtime settings, users, venues (hub)."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, type TEXT NOT NULL, table_id TEXT, payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id TEXT NOT NULL, start_ts REAL NOT NULL, end_ts REAL,
    guests INTEGER NOT NULL DEFAULT 0, first_visit_ts REAL,
    visits INTEGER NOT NULL DEFAULT 0, cleaned_ts REAL, is_demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_ts);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, kind TEXT NOT NULL, table_id TEXT,
    severity TEXT NOT NULL DEFAULT 'warning', message TEXT NOT NULL,
    resolved_ts REAL, acked INTEGER NOT NULL DEFAULT 0, ack_by TEXT,
    params TEXT, is_demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'staff', display_name TEXT, created_ts REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS venues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, city TEXT, api_key TEXT UNIQUE NOT NULL,
    created_ts REAL NOT NULL, last_seen REAL, summary TEXT
);
"""


class Database:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
            for col in ("ack_by TEXT", "params TEXT"):  # migrate DBs created by v1
                try:
                    self._conn.execute(f"ALTER TABLE alerts ADD COLUMN {col}")
                except sqlite3.OperationalError:
                    pass
            self._conn.commit()

    # -- helpers --------------------------------------------------------------
    def _exec(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    def _all(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, tuple(params)).fetchall()]

    def executemany(self, sql: str, rows: list[tuple]) -> None:
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    # -- events -----------------------------------------------------------------
    def log_event(self, ts: float, type_: str, table_id: str | None, payload: dict | None = None) -> None:
        self._exec("INSERT INTO events(ts,type,table_id,payload) VALUES (?,?,?,?)",
                   (ts, type_, table_id, json.dumps(payload or {}, default=str)))

    def recent_events(self, limit: int = 100) -> list[dict]:
        return self._all("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))

    # -- sessions -----------------------------------------------------------------
    def start_session(self, table_id: str, start_ts: float, guests: int) -> int:
        cur = self._exec("INSERT INTO sessions(table_id,start_ts,guests) VALUES (?,?,?)",
                         (table_id, start_ts, guests))
        return int(cur.lastrowid)

    def update_session(self, session_id: int | None, **fields: Any) -> None:
        if not session_id or not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE sessions SET {cols} WHERE id=?", (*fields.values(), session_id))

    def sessions_since(self, since_ts: float) -> list[dict]:
        return self._all("SELECT * FROM sessions WHERE start_ts>=? AND end_ts IS NOT NULL ORDER BY start_ts",
                         (since_ts,))

    def purge_demo(self) -> dict:
        with self._lock:
            a = self._conn.execute("DELETE FROM sessions WHERE is_demo=1").rowcount
            b = self._conn.execute("DELETE FROM alerts WHERE is_demo=1").rowcount
            self._conn.commit()
        return {"sessions": a, "alerts": b}

    def sessions_for_table(self, table_id: str, limit: int = 8) -> list[dict]:
        return self._all("SELECT * FROM sessions WHERE table_id=? ORDER BY start_ts DESC LIMIT ?", (table_id, limit))

    def events_for_table(self, table_id: str, limit: int = 15) -> list[dict]:
        return self._all("SELECT * FROM events WHERE table_id=? ORDER BY id DESC LIMIT ?", (table_id, limit))

    def count_sessions(self) -> int:
        return int(self._all("SELECT COUNT(*) AS c FROM sessions")[0]["c"])

    # -- alerts ---------------------------------------------------------------------
    def add_alert(self, ts: float, kind: str, table_id: str, severity: str, message: str,
                  params: dict | None = None) -> int:
        cur = self._exec(
            "INSERT INTO alerts(ts,kind,table_id,severity,message,params) VALUES (?,?,?,?,?,?)",
            (ts, kind, table_id, severity, message, json.dumps(params or {})))
        return int(cur.lastrowid)

    def resolve_alert(self, alert_id: int, ts: float) -> None:
        self._exec("UPDATE alerts SET resolved_ts=? WHERE id=? AND resolved_ts IS NULL", (ts, alert_id))

    def ack_alert(self, alert_id: int, by: str | None = None) -> None:
        self._exec("UPDATE alerts SET acked=1, ack_by=COALESCE(?, ack_by) WHERE id=?", (by, alert_id))

    def alerts_since(self, since_ts: float, limit: int = 100) -> list[dict]:
        return self._all("SELECT * FROM alerts WHERE ts>=? ORDER BY ts DESC LIMIT ?", (since_ts, limit))

    def close_open_alerts(self, ts: float) -> None:
        self._exec("UPDATE alerts SET resolved_ts=? WHERE resolved_ts IS NULL", (ts,))

    # -- runtime settings ----------------------------------------------------------------
    def get_settings(self) -> dict:
        return {r["key"]: json.loads(r["value"]) for r in self._all("SELECT * FROM settings")}

    def set_setting(self, key: str, value: Any) -> None:
        self._exec("INSERT INTO settings(key,value) VALUES (?,?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))

    # -- users -----------------------------------------------------------------------------
    def create_user(self, username: str, pw_hash: str, role: str, display_name: str | None, ts: float) -> int:
        cur = self._exec("INSERT INTO users(username,pw_hash,role,display_name,created_ts) VALUES (?,?,?,?,?)",
                         (username, pw_hash, role, display_name or username, ts))
        return int(cur.lastrowid)

    def get_user(self, username: str) -> dict | None:
        r = self._all("SELECT * FROM users WHERE username=?", (username,))
        return r[0] if r else None

    def list_users(self) -> list[dict]:
        return self._all("SELECT id,username,role,display_name,created_ts FROM users ORDER BY id")

    def delete_user(self, user_id: int) -> None:
        self._exec("DELETE FROM users WHERE id=?", (user_id,))

    def set_password(self, user_id: int, pw_hash: str) -> None:
        self._exec("UPDATE users SET pw_hash=? WHERE id=?", (pw_hash, user_id))

    def count_users(self) -> int:
        return int(self._all("SELECT COUNT(*) AS c FROM users")[0]["c"])

    # -- venues (hub) ------------------------------------------------------------------------
    def create_venue(self, name: str, city: str | None, api_key: str, ts: float) -> int:
        cur = self._exec("INSERT INTO venues(name,city,api_key,created_ts) VALUES (?,?,?,?)",
                         (name, city, api_key, ts))
        return int(cur.lastrowid)

    def venue_by_key(self, api_key: str) -> dict | None:
        r = self._all("SELECT * FROM venues WHERE api_key=?", (api_key,))
        return r[0] if r else None

    def update_venue_summary(self, venue_id: int, ts: float, summary: dict) -> None:
        self._exec("UPDATE venues SET last_seen=?, summary=? WHERE id=?", (ts, json.dumps(summary), venue_id))

    def list_venues(self) -> list[dict]:
        return self._all("SELECT id,name,city,created_ts,last_seen,summary FROM venues ORDER BY name")

    def delete_venue(self, venue_id: int) -> None:
        self._exec("DELETE FROM venues WHERE id=?", (venue_id,))
