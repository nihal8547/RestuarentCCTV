"""Is the table clean / dirty? Works without any custom training.

Two cues (combined in Pipeline._table_signals):
  * items      - COCO objects on the table (cup, bowl, fork, knife, spoon, wine glass, bottle) inside the
                 table's zone while nobody is sitting there  -> dirty.
  * appearance - the table-top is compared with a *reference photo of the clean empty table*
                 (capture it once from the dashboard: table drawer -> "Set as clean reference").
                 Lighting-normalised difference above `diff_thr` -> dirty, below `diff_thr*0.6` -> clean.
Both only evaluate when no person is standing in the zone (people occlude the table).
"""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("tablevision")
SZ = 48


def _norm(gray: np.ndarray) -> np.ndarray:
    g = cv2.GaussianBlur(gray.astype(np.float32), (5, 5), 0)
    return (g - g.mean()) / max(float(g.std()), 8.0)


def crop_gray(frame: np.ndarray, bbox, pad: float = 0.1) -> np.ndarray | None:
    x1, y1, x2, y2 = bbox
    w, h = x2 - x1, y2 - y1
    x1, x2 = int(max(0, x1 - w * pad)), int(min(frame.shape[1], x2 + w * pad))
    y1, y2 = int(max(0, y1 - h * pad)), int(min(frame.shape[0], y2 + h * pad))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    return cv2.resize(cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY), (SZ, SZ))


class TableVision:
    def __init__(self, ref_dir: str | Path, diff_thr: float = 0.45, item_min: int = 2, every_sec: float = 1.0):
        self.dir = Path(ref_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.diff_thr, self.item_min, self.every = diff_thr, item_min, every_sec
        self.refs: dict[str, np.ndarray] = {}
        self._last: dict[str, float] = {}
        self.score: dict[str, float | None] = {}
        for p in self.dir.glob("*.png"):
            img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                self.refs[p.stem] = _norm(img)

    def has_ref(self, tid: str) -> bool:
        return tid in self.refs

    def set_reference(self, tid: str, frame: np.ndarray, bbox) -> bool:
        g = crop_gray(frame, bbox)
        if g is None:
            return False
        cv2.imwrite(str(self.dir / f"{tid}.png"), g)
        self.refs[tid] = _norm(g)
        self.score[tid] = 0.0
        return True

    def clear_reference(self, tid: str) -> None:
        self.refs.pop(tid, None)
        self.score.pop(tid, None)
        (self.dir / f"{tid}.png").unlink(missing_ok=True)

    def measure(self, tid: str, frame: np.ndarray, bbox, now: float) -> float | None:
        """Appearance difference vs reference (throttled). None if no reference / cannot compute."""
        if tid not in self.refs:
            return None
        if now - self._last.get(tid, 0) < self.every and tid in self.score:
            return self.score[tid]
        g = crop_gray(frame, bbox)
        if g is None:
            return self.score.get(tid)
        self._last[tid] = now
        self.score[tid] = round(float(np.mean(np.abs(_norm(g) - self.refs[tid]))), 3)
        return self.score[tid]

    def decide(self, items: int, score: float | None) -> str | None:
        """-> 'dirty' | 'clean' | None for an UNOCCUPIED, person-free table."""
        if self.item_min > 0 and items >= self.item_min:     # ITEM_MIN=0 disables the item cue
            return "dirty"
        if score is not None:
            if score > self.diff_thr:
                return "dirty"
            if score <= self.diff_thr * 0.6 and items == 0:
                return "clean"
        return None
