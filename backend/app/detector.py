"""Person detection. YOLOv8 for real footage; staff are told apart by uniform colour."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float = 0.9
    is_staff: bool = False
    track_id: int | None = None
    cls: str = "person"          # person | item | table_clean | table_dirty

    def anchor(self, mode: str = "center") -> tuple[float, float]:
        cx = (self.x1 + self.x2) / 2
        if mode == "foot":
            return cx, self.y2
        return cx, (self.y1 + self.y2) / 2


# COCO table-ware: bottle, wine glass, cup, fork, knife, spoon, bowl
ITEM_CLASSES = [39, 40, 41, 42, 43, 44, 45]


class YoloDetector:
    """Wraps ultralytics YOLOv8 (class 0 = person). Imported lazily so sim mode needs no torch."""

    def __init__(self, model_path: str, conf: float, imgsz: int, device: str,
                 hsv_low, hsv_high, staff_ratio: float, use_bytetrack: bool = False):
        try:
            from ultralytics import YOLO
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "ultralytics is not installed. Run: pip install -r requirements-yolo.txt "
                "or use VIDEO_SOURCE=sim"
            ) from e
        self.model = YOLO(model_path)
        self.conf = conf
        self.imgsz = imgsz
        self.device = device or None
        self.set_uniform(hsv_low, hsv_high)
        self.staff_ratio = staff_ratio
        self.use_bytetrack = use_bytetrack
        # Custom-trained model support. Class names are mapped by name:
        #   staff/waiter -> staff person | customer/person/guest -> customer person
        #   table_clean/clean_table -> "Clean Table" signal | table_dirty/dirty_table -> uncleaned signal
        # Without such classes we fall back to COCO class 0 (= person) + uniform colour for staff.
        names = {i: str(n).lower() for i, n in getattr(self.model, "names", {}).items()}
        self.roles: dict[int, tuple[str, bool]] = {}
        for i, n in names.items():
            if n in ("staff", "waiter"):
                self.roles[i] = ("person", True)
            elif n in ("customer", "person", "guest"):
                self.roles[i] = ("person", False)
            elif n in ("plate", "cup", "glass", "bottle", "dish", "bowl", "item", "tableware"):
                self.roles[i] = ("item", False)
            elif n in ("table_clean", "clean_table", "clean table"):
                self.roles[i] = ("table_clean", False)
            elif n in ("table_dirty", "dirty_table", "uncleaned", "table_uncleaned"):
                self.roles[i] = ("table_dirty", False)
        self.custom = any(v[1] or v[0].startswith("table") for v in self.roles.values())

    def set_uniform(self, low, high) -> None:
        """Uniform colour range (OpenCV HSV). None = colour cue disabled (roaming / custom class only)."""
        if low is None or high is None:
            self.hsv_low = self.hsv_high = None
        else:
            self.hsv_low, self.hsv_high = np.array(low, dtype=np.uint8), np.array(high, dtype=np.uint8)

    def _is_staff(self, frame: np.ndarray, box: tuple[int, int, int, int]) -> bool:
        if self.hsv_low is None:
            return False
        x1, y1, x2, y2 = box
        h = y2 - y1
        crop = frame[max(0, y1): max(0, y1 + int(h * 0.6)), max(0, x1): max(0, x2)]  # upper body
        if crop.size == 0:
            return False
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.hsv_low, self.hsv_high)
        return float(mask.mean() / 255.0) >= self.staff_ratio

    def detect(self, frame: np.ndarray) -> list[Detection]:
        classes = list(self.roles) if self.custom else [0] + ITEM_CLASSES
        kw = dict(classes=classes, conf=min(self.conf, 0.25), imgsz=self.imgsz, device=self.device, verbose=False)
        if self.use_bytetrack:
            res = self.model.track(frame, persist=True, tracker="bytetrack.yaml", **kw)[0]
        else:
            res = self.model.predict(frame, **kw)[0]
        out: list[Detection] = []
        for b in res.boxes:
            x1, y1, x2, y2 = (int(v) for v in b.xyxy[0].tolist())
            if self.custom:
                kind, staff = self.roles.get(int(b.cls[0]), ("person", False))
            elif int(b.cls[0]) in ITEM_CLASSES:
                kind, staff = "item", False
            else:
                kind, staff = "person", self._is_staff(frame, (x1, y1, x2, y2))
            if kind == "person" and float(b.conf[0]) < self.conf:
                continue
            tid = int(b.id[0]) if (self.use_bytetrack and getattr(b, "id", None) is not None) else None
            out.append(Detection(x1, y1, x2, y2, float(b.conf[0]), staff, tid, kind))
        return out
