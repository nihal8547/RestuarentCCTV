import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.state_machine import State, TableTracker, Thresholds  # noqa: E402


def make(**kw):
    th = Thresholds(wait_alert_sec=300, clean_alert_sec=120, count_window=3, **kw)
    return TableTracker("T02", 2, 4, "B", th)


def run(t, start, end, customers, staff=False, step=0.1):
    """Feed constant input from start..end; return all events."""
    out, now = [], start
    while now < end:
        out += t.update(now, customers, staff)
        now += step
    return out


def types(events):
    return [e["type"] for e in events]


def test_free_to_occupied_counts_guests_and_timer():
    t = make()
    ev = run(t, 0, 5, customers=2)
    assert t.state == State.OCCUPIED and t.guests == 2
    assert "seated" in types(ev)
    assert 3 <= t.timer_seconds(5) <= 5.1


def test_brief_presence_does_not_occupy():
    t = make()
    run(t, 0, 1.0, customers=1)  # walking past < occupy_confirm
    run(t, 1.0, 4, customers=0)
    assert t.state == State.FREE


def test_wait_alert_after_5_min_without_waiter():
    t = make()
    ev = run(t, 0, 299, customers=3)
    assert "alert" not in types(ev)
    ev = run(t, 299, 305, customers=3)
    alerts = [e for e in ev if e["type"] == "alert"]
    assert len(alerts) == 1 and alerts[0]["kind"] == "service_wait"


def test_waiter_visit_prevents_and_resolves_alert():
    t = make()
    run(t, 0, 200, customers=2)
    ev = run(t, 200, 202, customers=2, staff=True)  # waiter stands at table 2 s
    assert "waiter_visit" in types(ev)
    ev = run(t, 202, 480, customers=2)  # < 300s since the visit
    assert "alert" not in types(ev)
    ev = run(t, 480, 510, customers=2)  # >300s since the visit -> alert again
    assert "alert" in types(ev)
    ev = run(t, 510, 512, customers=2, staff=True)
    assert "alert_resolved" in types(ev)


def test_departure_then_cleaning_alert_then_cleaned():
    t = make()
    run(t, 0, 20, customers=2)
    ev = run(t, 20, 30, customers=0)
    assert "departed" in types(ev) and t.state == State.NEEDS_CLEANING
    ev = run(t, 30, 160, customers=0)
    assert [e["kind"] for e in ev if e["type"] == "alert"] == ["uncleaned_table"]
    ev = run(t, 160, 164, customers=0, staff=True)
    assert "cleaned" in types(ev) and t.state == State.FREE
    assert "alert_resolved" in types(ev)


def test_reseat_on_uncleaned_table():
    t = make()
    run(t, 0, 20, customers=2)
    run(t, 20, 30, customers=0)
    ev = run(t, 30, 36, customers=2)
    seated = [e for e in ev if e["type"] == "seated"]
    assert seated and seated[0]["uncleaned"] is True


def test_single_frame_dropout_is_smoothed():
    t = make()
    run(t, 0, 5, customers=2)
    t.update(5.0, 0, False)  # one missed detection frame
    t.update(5.1, 2, False)
    assert t.state == State.OCCUPIED and t.guests == 2


# ---- v3: manual actions + table-state detector signals --------------------------------
def test_manual_clean_and_visit():
    t = make()
    assert t.manual_clean(1) == []                      # not applicable when FREE
    run(t, 0, 5, customers=2)
    assert types(t.manual_visit(5)) == ["waiter_visit"] and t.visits == 1
    run(t, 5, 12, customers=0)
    assert t.state == State.NEEDS_CLEANING
    ev = t.manual_clean(12.5)
    assert ev[0]["type"] == "cleaned" and ev[0]["source"] == "manual" and t.state == State.FREE


def test_reserved_flag_cleared_when_seated():
    t = make()
    assert t.set_reserved(True, "host") and t.to_dict(0)["reserved"] is True
    run(t, 0, 5, customers=2)
    assert t.state == State.OCCUPIED and t.reserved is False
    assert t.set_reserved(True) is False                # cannot reserve an occupied table


def test_dirty_signal_moves_free_to_needs_cleaning_and_clean_signal_resets():
    t = make()
    out, now = [], 0.0
    while now < 5:
        out += t.update(now, 0, False, "dirty")
        now += 0.1
    assert t.state == State.NEEDS_CLEANING and "dirty_detected" in types(out)
    out, now = [], 5.0
    while now < 10:
        out += t.update(now, 0, False, "clean")
        now += 0.1
    assert t.state == State.FREE and "cleaned" in types(out)


def test_short_dirty_flicker_ignored():
    t = make()
    run(t, 0, 2, customers=0)
    t.update(2.0, 0, False, "dirty")
    t.update(2.5, 0, False, None)
    run(t, 3, 8, customers=0)
    assert t.state == State.FREE


def test_no_dirty_ping_pong_right_after_cleaning():
    t = make()
    t.manual_clean(0) if t.state == State.NEEDS_CLEANING else None
    run(t, 0, 5, customers=2)
    run(t, 5, 12, customers=0)
    assert t.state == State.NEEDS_CLEANING
    t.manual_clean(12)
    out, now = [], 12.0
    while now < 18:                                   # plates still visible for a few seconds
        out += t.update(now, 0, False, "dirty")
        now += 0.1
    assert t.state == State.FREE and "dirty_detected" not in types(out)
    while now < 30:                                   # but a persistent dirty signal is honoured later
        out += t.update(now, 0, False, "dirty")
        now += 0.1
    assert t.state == State.NEEDS_CLEANING
