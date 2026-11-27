"""Lightweight multi-object tracker (IoU + centroid matching) giving each person a stable ID.

Used for every detector so the overlay can show `#id`, and so a person briefly missed by the
detector keeps the same identity. (With YOLO you can alternatively enable ultralytics' ByteTrack
via USE_BYTETRACK=1 — IDs then come from the detector and this tracker is skipped.)
"""
from __future__ import annotations

from .detector import Detection


def _iou(a: Detection, b: Detection) -> float:
    ix1, iy1 = max(a.x1, b.x1), max(a.y1, b.y1)
    ix2, iy2 = min(a.x2, b.x2), min(a.y2, b.y2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter
    return inter / ua if ua > 0 else 0.0


class _Track:
    __slots__ = ("id", "det", "missed", "hits")

    def __init__(self, tid: int, det: Detection):
        self.id, self.det, self.missed, self.hits = tid, det, 0, 1


class SimpleTracker:
    def __init__(self, max_missed: int = 20, iou_min: float = 0.1, max_dist: float = 90.0,
                 ghost_frames: int = 10, ghost_min_hits: int = 4):
        self.max_missed, self.iou_min, self.max_dist = max_missed, iou_min, max_dist
        self.ghost_frames, self.ghost_min_hits = ghost_frames, ghost_min_hits
        self.tracks: list[_Track] = []
        self._next = 1

    def update(self, dets: list[Detection]) -> list[Detection]:
        unmatched = list(range(len(dets)))
        pairs = []
        for ti, t in enumerate(self.tracks):
            for di in unmatched:
                d = dets[di]
                iou = _iou(t.det, d)
                (tx, ty), (dx, dy) = t.det.anchor(), d.anchor()
                dist = ((tx - dx) ** 2 + (ty - dy) ** 2) ** 0.5
                if iou >= self.iou_min or dist <= self.max_dist:
                    pairs.append((-(iou + max(0.0, 1 - dist / self.max_dist)), ti, di))
        used_t, used_d = set(), set()
        for _, ti, di in sorted(pairs):
            if ti in used_t or di in used_d:
                continue
            used_t.add(ti)
            used_d.add(di)
            t = self.tracks[ti]
            t.det, t.missed = dets[di], 0
            t.hits += 1
            dets[di].track_id = t.id
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t.missed += 1
        self.tracks = [t for t in self.tracks if t.missed <= self.max_missed]
        for di, d in enumerate(dets):
            if di not in used_d:
                d.track_id = self._next
                self.tracks.append(_Track(self._next, d))
                self._next += 1
        # A person the detector misses for a few frames (occlusion by a neighbour, chair, glare) is kept alive:
        # re-emit the last known box so table counts do not flicker or drop.
        ghosts = [Detection(t.det.x1, t.det.y1, t.det.x2, t.det.y2, t.det.conf * 0.8, t.det.is_staff, t.id, "person")
                  for t in self.tracks
                  if t.det.cls == "person" and 0 < t.missed <= self.ghost_frames and t.hits >= self.ghost_min_hits]
        return dets + ghosts
