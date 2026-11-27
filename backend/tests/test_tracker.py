import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.detector import Detection  # noqa: E402
from app.tracker import SimpleTracker  # noqa: E402


def box(x, y):
    return Detection(x - 20, y - 20, x + 20, y + 20)


def test_ids_stable_while_moving():
    tr = SimpleTracker()
    a, b = tr.update([box(100, 100), box(400, 300)])
    ida, idb = a.track_id, b.track_id
    assert ida != idb
    for step in range(1, 20):
        out = tr.update([box(100 + step * 4, 100), box(400, 300 + step * 3)])
    assert out[0].track_id == ida and out[1].track_id == idb


def test_survives_short_dropout_and_new_person_gets_new_id():
    tr = SimpleTracker(max_missed=5)
    first = tr.update([box(100, 100)])[0].track_id
    for _ in range(3):
        tr.update([])  # detector missed the person
    again = tr.update([box(102, 101)])[0].track_id
    assert again == first
    third = tr.update([box(102, 101), box(600, 400)])
    assert third[1].track_id not in (first,)


def test_track_expires_after_long_absence():
    tr = SimpleTracker(max_missed=2)
    first = tr.update([box(100, 100)])[0].track_id
    for _ in range(5):
        tr.update([])
    assert tr.update([box(100, 100)])[0].track_id != first


def test_missed_person_is_kept_alive_for_a_few_frames():
    from app.detector import Detection
    from app.tracker import SimpleTracker
    tr = SimpleTracker()
    for _ in range(5):
        out = tr.update([Detection(100, 100, 160, 220)])
    assert len(out) == 1
    for _ in range(3):                      # detector misses him for 3 frames
        out = tr.update([])
        assert len(out) == 1 and out[0].track_id == 1
    for _ in range(20):                     # truly gone -> no ghost forever
        out = tr.update([])
    assert out == []
