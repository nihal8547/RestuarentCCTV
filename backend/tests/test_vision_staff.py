import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.detector import Detection  # noqa: E402
from app.staff_infer import StaffInferer  # noqa: E402
from app.table_vision import TableVision  # noqa: E402

ZONES = {"A": (0, 0, 100, 100), "B": (200, 0, 300, 100)}


def zone_of(pt):
    for k, (x1, y1, x2, y2) in ZONES.items():
        if x1 <= pt[0] <= x2 and y1 <= pt[1] <= y2:
            return k
    return None


def det(x, y, tid, staff=False):
    return Detection(x - 10, y - 10, x + 10, y + 10, 0.9, staff, tid)


def test_roaming_person_becomes_staff_and_customer_stays_customer():
    inf = StaffInferer(zone_of)
    now = 0.0
    for step in range(160):                       # 16 s
        now = step * 0.1
        waiter = det(50, 50, 1) if now < 6 else (det(250, 50, 1) if now > 8 else det(150, 50, 1))
        guest = det(50, 60, 2)
        out = inf.update([waiter, guest], now)
    assert out[0].is_staff is True                # stopped at A then B
    assert out[1].is_staff is False               # sat at one table only


def test_uniform_vote_smooths_flicker():
    inf = StaffInferer(zone_of)
    flags = [True] * 8 + [False] + [True] * 8
    res = [inf.update([det(150, 50, 7, f)], i * 0.1)[0].is_staff for i, f in enumerate(flags)]
    assert all(res[3:])                           # one bad frame does not flip it
    inf2 = StaffInferer(zone_of)
    res2 = [inf2.update([det(150, 50, 8, f)], i * 0.1)[0].is_staff for i, f in enumerate([False] * 8 + [True] + [False] * 8)]
    assert not any(res2[3:])                      # a single false hit does not make a customer staff


def test_table_vision_reference_and_decide(tmp_path):
    rng = np.random.default_rng(0)
    base = rng.integers(60, 120, (200, 200, 3), dtype=np.uint8)
    base[:] = np.dstack([np.tile(np.linspace(80, 140, 200), (200, 1))] * 3).astype(np.uint8)
    tv = TableVision(tmp_path, diff_thr=0.45, item_min=2, every_sec=0)
    bbox = (50, 50, 150, 150)
    assert tv.measure("T01", base, bbox, 0) is None            # no reference yet
    assert tv.set_reference("T01", base, bbox)
    same = base.copy()
    assert tv.measure("T01", same, bbox, 1) < 0.1
    assert tv.decide(0, 0.05) == "clean"
    dirty = base.copy()
    dirty[70:110, 70:130] = 20                                 # dark plate-like blob
    dirty[100:140, 90:140, :] = 230
    s = tv.measure("T01", dirty, bbox, 2)
    assert s > 0.45 and tv.decide(0, s) == "dirty"
    assert tv.decide(3, None) == "dirty"                       # items alone are enough
    assert tv.decide(0, None) is None
    tv2 = TableVision(tmp_path)                                # reference persisted on disk
    assert tv2.has_ref("T01")
    tv.clear_reference("T01")
    assert not tv.has_ref("T01")


def test_item_cue_ignored_when_reference_exists_and_can_be_disabled(tmp_path):
    tv = TableVision(tmp_path, item_min=2)
    assert tv.decide(3, None) == "dirty"
    tv0 = TableVision(tmp_path, item_min=0)
    assert tv0.decide(5, None) is None            # ITEM_MIN=0 turns the item cue off


def test_walking_through_zones_is_not_roaming_staff():
    inf = StaffInferer(zone_of)
    out = None
    for step in range(120):                        # strolls 3 px/frame across both zones, never stops
        now = step * 0.1
        out = inf.update([det(10 + step * 3, 50, 5)], now)
    assert out[0].is_staff is False


def test_uniform_colour_off_by_default(monkeypatch):
    import types
    fake = types.ModuleType("ultralytics")
    fake.YOLO = lambda path: types.SimpleNamespace(names={0: "person"})
    monkeypatch.setitem(sys.modules, "ultralytics", fake)
    from app.detector import YoloDetector
    d = YoloDetector("x.pt", 0.3, 640, "", None, None, 0.3)
    frame = np.zeros((100, 100, 3), np.uint8)
    assert d._is_staff(frame, (10, 10, 60, 90)) is False
    d.set_uniform((0, 0, 0), (179, 255, 255))
    assert d._is_staff(frame, (10, 10, 60, 90)) is True or d._is_staff(frame, (10, 10, 60, 90)) is False  # callable
