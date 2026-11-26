"""Per-table state machine.

FREE ──(guests present ≥ occupy_confirm)──▶ OCCUPIED
OCCUPIED ──(no guests ≥ leave_confirm)──▶ NEEDS_CLEANING
NEEDS_CLEANING ──(staff dwell ≥ clean_confirm)──▶ FREE   ("Clean Table")

Alerts
  service_wait    : OCCUPIED and no waiter visit for `wait_alert_sec`
  uncleaned_table : NEEDS_CLEANING for `clean_alert_sec`

The class is pure logic (no OpenCV / threads / clock), so it is trivially unit-testable:
call `update(now, customers, staff_present)` once per frame and handle the returned events.
"""
from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass
from enum import Enum


class State(str, Enum):
    FREE = "FREE"
    OCCUPIED = "OCCUPIED"
    NEEDS_CLEANING = "NEEDS_CLEANING"


@dataclass
class Thresholds:
    wait_alert_sec: float = 300.0
    clean_alert_sec: float = 120.0
    occupy_confirm_sec: float = 1.5
    leave_confirm_sec: float = 3.0
    waiter_visit_sec: float = 1.0
    clean_confirm_sec: float = 2.0
    count_window: int = 15
    signal_confirm_sec: float = 3.0   # table_clean / table_dirty detector must persist this long


def mmss(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


class TableTracker:
    def __init__(self, table_id: str, number: int, seats: int, section: str, th: Thresholds):
        self.id = table_id
        self.number = number
        self.seats = seats
        self.section = section
        self.th = th
        self.state = State.FREE
        self.guests = 0
        self.peak_guests = 0
        self.session_id: int | None = None
        self.seated_since: float | None = None
        self.vacated_at: float | None = None
        self.last_visit: float | None = None
        self.first_visit: float | None = None
        self.visits = 0
        self.wait_alert_active = False
        self.clean_alert_active = False
        self._counts: deque[int] = deque(maxlen=max(1, th.count_window))
        self._occ_since: float | None = None
        self._free_since: float | None = None
        self._staff_since: float | None = None
        self._visit_counted = False
        self.reserved = False
        self.reserved_by: str | None = None
        self.cleaned_at = -1e9
        self._sig_since: float | None = None
        self._sig_kind: str | None = None

    # ------------------------------------------------------------------
    def _start_session(self, since: float, guests: int, uncleaned: bool) -> dict:
        self.state = State.OCCUPIED
        self.seated_since = since
        self.guests = guests
        self.peak_guests = guests
        self.visits = 0
        self.last_visit = None
        self.first_visit = None
        self.wait_alert_active = False
        self._free_since = None
        self._occ_since = None
        self._visit_counted = False
        self.reserved, self.reserved_by = False, None
        return {"type": "seated", "table": self.id, "guests": guests, "uncleaned": uncleaned}

    def update(self, now: float, customers: int, staff_present: bool, table_signal: str | None = None) -> list[dict]:
        th = self.th
        ev: list[dict] = []
        self._counts.append(int(customers))
        smooth = int(round(statistics.median(self._counts)))

        # staff dwell tracking (continuous presence in / next to the zone)
        if staff_present:
            if self._staff_since is None:
                self._staff_since = now
        else:
            self._staff_since = None
            self._visit_counted = False
        dwell = (now - self._staff_since) if self._staff_since is not None else 0.0
        # table-state detector (custom YOLO): 'clean' | 'dirty' | None, must persist signal_confirm_sec
        if table_signal != self._sig_kind:
            self._sig_kind, self._sig_since = table_signal, (now if table_signal else None)
        sig_dwell = (now - self._sig_since) if self._sig_since is not None else 0.0

        if self.state == State.FREE:
            if smooth > 0:
                if self._occ_since is None:
                    self._occ_since = now
                if now - self._occ_since >= th.occupy_confirm_sec:
                    ev.append(self._start_session(self._occ_since, smooth, uncleaned=False))
            else:
                self._occ_since = None
                if table_signal == "dirty" and sig_dwell >= th.signal_confirm_sec and now - self.cleaned_at >= 10:
                    self.state, self.vacated_at, self.guests = State.NEEDS_CLEANING, self._sig_since, 0
                    self.clean_alert_active = False
                    ev.append({"type": "dirty_detected", "table": self.id, "source": "detector"})

        elif self.state == State.OCCUPIED:
            if smooth > 0:
                self._free_since = None
                self.guests = smooth
                self.peak_guests = max(self.peak_guests, smooth)

                # waiter visit = staff stays in the zone long enough (once per dwell)
                if dwell >= th.waiter_visit_sec and not self._visit_counted:
                    self._visit_counted = True
                    ev += self._register_visit(now)

                ref = self.last_visit if self.last_visit is not None else self.seated_since
                if (not self.wait_alert_active and ref is not None
                        and now - ref >= th.wait_alert_sec):
                    self.wait_alert_active = True
                    waited = mmss(now - ref)
                    ev.append({
                        "type": "alert", "kind": "service_wait", "table": self.id,
                        "severity": "warning",
                        "message": f"Table {self.number:02d}: {self.guests} guest(s) waiting "
                                   f"{waited} with no waiter visit",
                        "params": {"number": self.number, "guests": self.guests, "secs": int(now - ref)},
                    })
            else:
                if self._free_since is None:
                    self._free_since = now
                if now - self._free_since >= th.leave_confirm_sec:
                    self.vacated_at = self._free_since
                    ev.append({
                        "type": "departed", "table": self.id, "guests": self.peak_guests,
                        "dwell_sec": self.vacated_at - (self.seated_since or self.vacated_at),
                        "visits": self.visits, "first_visit": self.first_visit,
                        "end_ts": self.vacated_at,
                    })
                    if self.wait_alert_active:
                        self.wait_alert_active = False
                        ev.append({"type": "alert_resolved", "table": self.id,
                                   "kind": "service_wait", "reason": "guests left"})
                    self.state = State.NEEDS_CLEANING
                    self.guests = 0
                    self._free_since = None
                    self._occ_since = None
                    self.clean_alert_active = False

        elif self.state == State.NEEDS_CLEANING:
            if smooth > 0:
                # new guests sat down before the table was reset
                if self._occ_since is None:
                    self._occ_since = now
                if now - self._occ_since >= th.occupy_confirm_sec:
                    if self.clean_alert_active:
                        self.clean_alert_active = False
                        ev.append({"type": "alert_resolved", "table": self.id,
                                   "kind": "uncleaned_table", "reason": "re-seated"})
                    ev.append(self._start_session(self._occ_since, smooth, uncleaned=True))
            else:
                self._occ_since = None
                by_detector = table_signal == "clean" and sig_dwell >= th.signal_confirm_sec
                if dwell >= th.clean_confirm_sec or by_detector:
                    turnaround = now - (self.vacated_at or now)
                    self.state = State.FREE
                    self.cleaned_at = now
                    ev.append({"type": "cleaned", "table": self.id, "turnaround_sec": turnaround,
                               "ts_clean": now, "source": "detector" if by_detector and dwell < th.clean_confirm_sec else "staff"})
                    if self.clean_alert_active:
                        self.clean_alert_active = False
                        ev.append({"type": "alert_resolved", "table": self.id,
                                   "kind": "uncleaned_table", "reason": "table cleaned"})
                elif (not self.clean_alert_active and self.vacated_at is not None
                      and now - self.vacated_at >= th.clean_alert_sec):
                    self.clean_alert_active = True
                    ev.append({
                        "type": "alert", "kind": "uncleaned_table", "table": self.id,
                        "severity": "warning",
                        "message": f"Table {self.number:02d} left uncleaned for "
                                   f"{mmss(now - self.vacated_at)} - bussing needed",
                        "params": {"number": self.number, "secs": int(now - self.vacated_at)},
                    })
        return ev

    # ---- shared / manual actions ------------------------------------------------------
    def _register_visit(self, now: float) -> list[dict]:
        ev = []
        self.visits += 1
        self.last_visit = now
        if self.first_visit is None:
            self.first_visit = now
        ev.append({"type": "waiter_visit", "table": self.id, "ts_visit": now})
        if self.wait_alert_active:
            self.wait_alert_active = False
            ev.append({"type": "alert_resolved", "table": self.id, "kind": "service_wait",
                       "reason": "waiter visited"})
        return ev

    def manual_visit(self, now: float) -> list[dict]:
        """Host/manager taps 'waiter visited' (e.g. the camera could not see the visit)."""
        if self.state != State.OCCUPIED:
            return []
        return self._register_visit(now)

    def manual_clean(self, now: float) -> list[dict]:
        """Busser taps 'mark cleaned' on a table that needs cleaning."""
        if self.state != State.NEEDS_CLEANING:
            return []
        ev = [{"type": "cleaned", "table": self.id, "turnaround_sec": now - (self.vacated_at or now),
               "ts_clean": now, "source": "manual"}]
        if self.clean_alert_active:
            self.clean_alert_active = False
            ev.append({"type": "alert_resolved", "table": self.id, "kind": "uncleaned_table",
                       "reason": "marked cleaned manually"})
        self.state = State.FREE
        self.cleaned_at = now
        self._occ_since = None
        return ev

    def set_reserved(self, flag: bool, by: str | None = None) -> bool:
        if flag and self.state == State.OCCUPIED:
            return False
        self.reserved, self.reserved_by = flag, (by if flag else None)
        return True

    # ------------------------------------------------------------------
    def timer_seconds(self, now: float) -> float:
        if self.state == State.OCCUPIED and self.seated_since is not None:
            return now - self.seated_since
        if self.state == State.NEEDS_CLEANING and self.vacated_at is not None:
            return now - self.vacated_at
        return 0.0

    def to_dict(self, now: float) -> dict:
        t = self.timer_seconds(now)
        return {
            "id": self.id,
            "number": self.number,
            "label": f"Table {self.number:02d}",
            "section": self.section,
            "seats": self.seats,
            "state": self.state.value,
            "guests": self.guests,
            "timer_sec": int(t),
            "timer": mmss(t),
            "visits": self.visits,
            "since_last_visit_sec": (
                int(now - (self.last_visit or self.seated_since))
                if self.state == State.OCCUPIED and (self.last_visit or self.seated_since) else None
            ),
            "reserved": self.reserved,
            "reserved_by": self.reserved_by,
            "wait_alert": self.wait_alert_active,
            "clean_alert": self.clean_alert_active,
        }
