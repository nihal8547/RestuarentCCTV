"""Decide who is staff vs customer, robustly (works with the stock YOLO model).

Three independent cues are combined; any of them marks a *track* as staff, and staff status is sticky:
  1. detector flag     - uniform colour (HSV) or a custom `staff` class, smoothed by majority vote over
                         the last frames so a single bad frame cannot flip someone.
  2. roaming behaviour - a person who makes stops (>= stop_sec) at >= min_stops DIFFERENT tables is serving,
                         not dining (guests sit at one table).
  3. manual/uniform calibration happens outside (see /api/calibrate/uniform).
"""
from __future__ import annotations

from collections import deque
from typing import Callable

from .detector import Detection


class StaffInferer:
    def __init__(self, zone_of: Callable[[tuple[float, float]], str | None], anchor: str = "center",
                 vote_frames: int = 25, vote_ratio: float = 0.5, min_stops: int = 2,
                 stop_sec: float = 1.5, forget_sec: float = 30.0, still_px: float = 25.0):
        self.zone_of, self.anchor = zone_of, anchor
        self.vote_frames, self.vote_ratio = vote_frames, vote_ratio
        self.min_stops, self.stop_sec, self.forget_sec = min_stops, stop_sec, forget_sec
        self.still_px = still_px
        self.tracks: dict[int, dict] = {}

    def update(self, dets: list[Detection], now: float) -> list[Detection]:
        for d in dets:
            if d.cls != "person" or d.track_id is None:
                continue
            st = self.tracks.get(d.track_id)
            if st is None:
                st = self.tracks[d.track_id] = {"votes": deque(maxlen=self.vote_frames), "zone": None,
                                                "since": now, "pos0": None, "stops": set(), "sticky": False, "seen": now}
            st["seen"] = now
            st["votes"].append(bool(d.is_staff))
            pt = d.anchor(self.anchor)
            zone = self.zone_of(pt)
            moved = st["pos0"] is not None and ((pt[0] - st["pos0"][0]) ** 2 + (pt[1] - st["pos0"][1]) ** 2) ** 0.5 > self.still_px
            if zone != st["zone"] or moved or st["pos0"] is None:
                st["zone"], st["since"], st["pos0"] = zone, now, pt      # walking past does not count as a stop
            elif zone is not None and now - st["since"] >= self.stop_sec:
                st["stops"].add(zone)
            if len(st["stops"]) >= self.min_stops:
                st["sticky"] = True
            votes = st["votes"]
            voted = len(votes) >= 3 and sum(votes) / len(votes) >= self.vote_ratio
            d.is_staff = st["sticky"] or voted or (len(votes) < 3 and d.is_staff)
        if len(self.tracks) > 200 or int(now) % 10 == 0:
            self.tracks = {k: v for k, v in self.tracks.items() if now - v["seen"] < self.forget_sec}
        return dets
