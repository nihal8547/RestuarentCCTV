import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.detector import YoloDetector  # noqa: E402


def _make(names, monkeypatch):
    fake = types.ModuleType("ultralytics")
    fake.YOLO = lambda path: types.SimpleNamespace(names=names)
    monkeypatch.setitem(sys.modules, "ultralytics", fake)
    return YoloDetector("x.pt", 0.3, 640, "", (0, 0, 0), (0, 0, 0), 0.3)


def test_custom_classes_mapped(monkeypatch):
    d = _make({0: "customer", 1: "Staff", 2: "table_clean", 3: "table_dirty"}, monkeypatch)
    assert d.custom
    assert d.roles == {0: ("person", False), 1: ("person", True), 2: ("table_clean", False), 3: ("table_dirty", False)}


def test_stock_coco_not_custom(monkeypatch):
    d = _make({0: "person", 1: "bicycle"}, monkeypatch)
    assert not d.custom
