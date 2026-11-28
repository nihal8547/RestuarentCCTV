"""Dataset validation, leak-free train/val split and the model regression guard (no YOLO needed)."""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.training import Studio


class FakeDB:
    def __init__(self):
        self.s = {}

    def get_settings(self):
        return self.s

    def set_setting(self, k, v):
        self.s[k] = v


@pytest.fixture()
def studio():
    d = Path(tempfile.mkdtemp())
    st = Studio(SimpleNamespace(db_path=str(d / "x.db")), FakeDB(), SimpleNamespace(reload_models=lambda: None))
    return st


def _add(st, stem, rows):
    (st.root / "images" / f"{stem}.jpg").write_bytes(b"x")
    (st.root / "labels" / f"{stem}.txt").write_text("\n".join(rows))


def test_check_blocks_empty_and_bad_labels(studio):
    chk = studio.dataset_check()
    assert not chk["ok"] and "at least 8" in chk["errors"][0]
    for i in range(10):
        _add(studio, f"a-{i:04d}", ["0 0.5 0.5 0.2 0.3", "5 0.5 0.5 0.2 0.3"])      # class 5 does not exist
    chk = studio.dataset_check()
    assert not chk["ok"] and any("invalid" in e for e in chk["errors"])


def test_check_warns_but_allows(studio):
    for i in range(20):
        _add(studio, f"lunch-{i:04d}", ["0 0.5 0.5 0.2 0.3"])
    chk = studio.dataset_check()
    assert chk["ok"]
    text = " ".join(chk["warnings"])
    assert "staff" in text and "one video" in text and "small" in text


def test_split_holds_out_whole_time_blocks_not_random_frames(studio):
    for i in range(240):
        _add(studio, f"clip-{i:04d}", ["0 0.5 0.5 0.2 0.3"])
    pairs = [(p, studio.root / "labels" / (p.stem + ".txt")) for p in sorted((studio.root / "images").glob("*.jpg"))]
    val = studio._split(pairs, 0.2)
    assert 0.1 * 240 <= len(val) <= 0.3 * 240
    idx = sorted(int(n[5:9]) for n in val)
    runs = 1 + sum(1 for a, b in zip(idx, idx[1:]) if b != a + 1)
    assert runs <= len(idx) / 8          # contiguous blocks (>=8 frames per run on average), i.e. no frame-level leakage


def test_regression_guard(studio):
    def model(name, map50, src="trained"):
        d = studio.root / "models" / name
        d.mkdir(parents=True)
        (d / "best.pt").write_bytes(b"x")
        (d / "meta.json").write_text(json.dumps({"source": src, "map50": map50, "usable": True}))
    model("good", 0.80)
    model("worse", 0.60)
    model("weak", 0.10)
    studio.db.set_setting("active_model", "good")
    with pytest.raises(ValueError, match="worse"):
        studio._regression_guard("worse", False)
    with pytest.raises(ValueError, match="not ready"):
        studio._regression_guard("weak", False)
    studio._regression_guard("worse", True)          # force


def test_evaluate_against_truth(tmp_path):
    from app.evaluation import evaluate, load_truth
    f = tmp_path / "t.csv"
    f.write_text("start_sec,end_sec,table,state,guests\n0,100,T01,FREE,0\n100,400,T01,OCCUPIED,3\n400,500,T01,NEEDS_CLEANING,0\n")
    samples = []
    for t in range(0, 500, 2):
        st, g = ("FREE", 0) if t < 108 else ("OCCUPIED", 2) if t < 405 else ("NEEDS_CLEANING", 0)   # 8 s late, 1 guest short
        samples.append((t, {"T01": (st, g)}))
    m = evaluate(samples, load_truth(str(f)), grace=10)
    assert m["state_accuracy"] == 1.0 and m["guest_count_mae"] == 1.0
    assert m["seat_detect_delay_sec"]["mean"] == 8.0 and m["seat_detect_delay_sec"]["missed_parties"] == 0
    bad = [(t, {"T01": ("FREE", 0)}) for t in range(0, 500, 2)]            # never sees the party
    assert evaluate(bad, load_truth(str(f)), 10)["seat_detect_delay_sec"]["missed_parties"] == 1
