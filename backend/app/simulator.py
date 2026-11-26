"""Synthetic restaurant: renders an overhead 'CCTV' view and emits ground-truth detections.

Lets the whole system (state machine, alerts, dashboard) run with no camera and no model.
Guests walk in, sit, (usually) get visited by a waiter, leave, and a bus person resets the table.
Some visits/cleanings are deliberately late so the 5-minute and uncleaned-table alerts fire.
"""
from __future__ import annotations

import random
import time

import cv2
import numpy as np

from .detector import Detection

W, H = 960, 540
AISLE_Y = 285
ENTRANCE = (-30.0, float(AISLE_Y))
STAFF_HOMES = [(35.0, 235.0), (35.0, 335.0)]
SEAT_OFFSETS = [(-55, -48), (55, -48), (-55, 48), (55, 48)]
GUEST_COLORS = [(170, 120, 80), (110, 140, 90), (150, 100, 150), (90, 120, 170), (120, 150, 150)]
STAFF_COLOR = (40, 140, 255)  # BGR orange -> matches default STAFF_HSV range


class Actor:
    def __init__(self, pos, role: str, color, speed: float = 110.0, active_from: float = 0.0):
        self.pos = np.array(pos, dtype=float)
        self.role = role
        self.color = color
        self.speed = speed
        self.path: list[tuple[float, float]] = []
        self.active_from = active_from
        self.gone = False

    def step(self, dt: float, now: float) -> None:
        if now < self.active_from:
            return
        while self.path and dt > 1e-6:
            tgt = np.array(self.path[0], dtype=float)
            d = tgt - self.pos
            dist = float(np.hypot(*d))
            move = self.speed * dt
            if dist <= move:
                self.pos = tgt
                self.path.pop(0)
                dt -= dist / self.speed if self.speed else dt
            else:
                self.pos = self.pos + d / dist * move
                dt = 0

    @property
    def idle(self) -> bool:
        return not self.path

    def active(self, now: float) -> bool:
        return now >= self.active_from and not self.gone


class SimTable:
    def __init__(self, zone: dict, sim: "Simulator"):
        self.id = zone["id"]
        x1, y1, x2, y2 = zone["table_bbox"]
        self.cx, self.cy = (x1 + x2) / 2, (y1 + y2) / 2
        self.bbox = zone["table_bbox"]
        self.top_row = self.cy < AISLE_Y
        self.sim = sim
        self.phase = "idle"
        self.guests: list[Actor] = []
        self.dirty = False
        self.seated_until = 0.0
        self.next_arrival = time.time() + random.uniform(2, 8) * sim.scale
        self.seat_points: list[tuple[float, float]] = []

    @property
    def approach(self) -> tuple[float, float]:
        return (self.cx, self.cy + 68) if self.top_row else (self.cx, self.cy - 68)

    def spawn_party(self, now: float, size: int | None = None, seated: bool = False) -> None:
        size = size or random.choices([1, 2, 3, 4], [0.12, 0.4, 0.28, 0.2])[0]
        slots = random.sample(range(4), size)
        self.guests = []
        self.seat_points = []
        for i, s in enumerate(slots):
            dx, dy = SEAT_OFFSETS[s]
            seat = (self.cx + dx, self.cy + dy)
            self.seat_points.append(seat)
            color = random.choice(GUEST_COLORS)
            if seated:
                a = Actor(seat, "guest", color)
            else:
                a = Actor(ENTRANCE, "guest", color, active_from=now + i * 0.7)
                a.path = [(self.cx + random.uniform(-20, 20), AISLE_Y), seat]
            self.guests.append(a)
        if seated:
            self._on_seated(now)
        else:
            self.phase = "arriving"

    def _on_seated(self, now: float) -> None:
        T = self.sim.th_wait
        self.phase = "seated"
        self.seated_until = now + random.uniform(1.8, 3.4) * T
        due = now + (random.uniform(0.2, 0.8) if random.random() < 0.7 else random.uniform(1.15, 1.6)) * T
        self.sim.add_task("visit", self, due, dwell=3.0)
        self.sim.add_task("visit", self, due + random.uniform(0.5, 0.9) * T, dwell=3.0)

    def update(self, now: float) -> None:
        if self.phase == "idle":
            if now >= self.next_arrival:
                self.spawn_party(now)
        elif self.phase == "arriving":
            if all(g.idle and g.active(now) for g in self.guests):
                self._on_seated(now)
        elif self.phase == "seated":
            if now >= self.seated_until:
                self.phase = "leaving"
                for g, seat in zip(self.guests, self.seat_points):
                    g.path = [(seat[0], AISLE_Y), (ENTRANCE[0], AISLE_Y)]
        elif self.phase == "leaving":
            for g in self.guests:
                if g.idle:
                    g.gone = True
            if all(g.gone for g in self.guests):
                self.guests = []
                self.dirty = True
                self.phase = "dirty"
                C = self.sim.th_clean
                delay = random.uniform(0.2, 0.7) * C if random.random() < 0.65 else random.uniform(1.2, 2.0) * C
                self.sim.add_task("bus", self, now + delay, dwell=4.0)

    def on_cleaned(self, now: float) -> None:
        self.dirty = False
        self.phase = "idle"
        self.next_arrival = now + random.uniform(3, 15) * self.sim.scale


class Staff(Actor):
    def __init__(self, home):
        super().__init__(home, "staff", STAFF_COLOR, speed=170.0)
        self.home = home
        self.task: dict | None = None
        self.mode = "home"  # home | going | dwelling | returning
        self.dwell_left = 0.0
        self.dwell_total = 0.0

    def assign(self, task: dict) -> None:
        self.task = task
        t: SimTable = task["table"]
        ax, ay = t.approach
        self.path = [(self.home[0], AISLE_Y), (t.cx, AISLE_Y), (ax, ay)]
        self.mode = "going"

    def tick(self, dt: float, now: float) -> None:
        self.step(dt, now)
        if self.mode == "going" and self.idle:
            self.mode = "dwelling"
            self.dwell_left = self.dwell_total = self.task["dwell"]
        elif self.mode == "dwelling":
            self.dwell_left -= dt
            t: SimTable = self.task["table"]
            if self.task["kind"] == "bus" and t.dirty and self.dwell_total - self.dwell_left >= 2.5:
                t.dirty = False  # visually cleared
            if self.dwell_left <= 0:
                if self.task["kind"] == "bus":
                    t.on_cleaned(now)
                t_ = self.task["table"]
                self.path = [(t_.cx, AISLE_Y), (self.home[0], AISLE_Y), self.home]
                self.mode = "returning"
                self.task = None
        elif self.mode == "returning" and self.idle:
            self.mode = "home"


class Simulator:
    def __init__(self, zones: dict, wait_alert_sec: float, clean_alert_sec: float,
                 dropout: float = 0.02, seed: int | None = None):
        if seed is not None:
            random.seed(seed)
        self.th_wait = wait_alert_sec
        self.th_clean = clean_alert_sec
        self.scale = max(0.2, wait_alert_sec / 30.0)
        self.dropout = dropout
        self.tables = [SimTable(z, self) for z in zones["tables"]]
        self.staff = [Staff(h) for h in STAFF_HOMES]
        self.tasks: list[dict] = []
        self.last = time.time()
        self._bg = self._build_background()
        # start with two occupied tables so the first screen is not empty
        now = time.time()
        for tid, n in (("T02", 2), ("T04", 3)):
            t = next(x for x in self.tables if x.id == tid)
            t.spawn_party(now, size=n, seated=True)

    # ---------------------------------------------------------------- logic
    def add_task(self, kind: str, table: SimTable, due: float, dwell: float) -> None:
        self.tasks.append({"kind": kind, "table": table, "due": due, "dwell": dwell})

    def _assign_tasks(self, now: float) -> None:
        for task in sorted(self.tasks, key=lambda t: t["due"]):
            if task["due"] > now:
                break
            t: SimTable = task["table"]
            if task["kind"] == "visit" and t.phase != "seated":
                self.tasks.remove(task)
                continue
            if task["kind"] == "bus" and t.phase != "dirty":
                self.tasks.remove(task)
                continue
            free = [s for s in self.staff if s.mode == "home"]
            if not free:
                break
            s = min(free, key=lambda s: abs(s.home[1] - t.cy))
            self.tasks.remove(task)
            s.assign(task)

    def update(self) -> float:
        now = time.time()
        dt = min(0.25, now - self.last)
        self.last = now
        for t in self.tables:
            t.update(now)
            for g in t.guests:
                g.step(dt, now)
        self._assign_tasks(now)
        for s in self.staff:
            s.tick(dt, now)
        return now

    # --------------------------------------------------------- detections
    def detections(self, now: float) -> list[Detection]:
        out: list[Detection] = []
        actors = [g for t in self.tables for g in t.guests if g.active(now)] + list(self.staff)
        for a in actors:
            if random.random() < self.dropout:
                continue
            x, y = a.pos + np.random.uniform(-1.5, 1.5, 2)
            out.append(Detection(x - 22, y - 22, x + 22, y + 22, random.uniform(0.8, 0.97),
                                 is_staff=(a.role == "staff")))
        for t in self.tables:           # left-over tableware on a dirty table (ground truth for the sim)
            if t.dirty:
                for dx in (-14, 14):
                    out.append(Detection(t.cx + dx - 7, t.cy - 7, t.cx + dx + 7, t.cy + 7, 0.8, cls="item"))
        return out

    # ------------------------------------------------------------ render
    def _build_background(self) -> np.ndarray:
        img = np.full((H, W, 3), (88, 118, 150), np.uint8)
        for x in range(0, W, 36):
            cv2.line(img, (x, 0), (x, H), (80, 108, 138), 1)
        cv2.rectangle(img, (0, 0), (W - 1, H - 1), (40, 50, 60), 6)
        cv2.rectangle(img, (0, 205), (18, 365), (60, 70, 80), -1)  # entrance doorway
        cv2.putText(img, "ENTRANCE", (22, 290), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (235, 235, 235), 1, cv2.LINE_AA)
        cv2.putText(img, "KITCHEN", (6, 224), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (235, 235, 235), 1, cv2.LINE_AA)
        for t in self.tables:
            x1, y1, x2, y2 = t.bbox
            for dx, dy in SEAT_OFFSETS:  # chairs
                cx, cy = int(t.cx + dx), int(t.cy + dy)
                cv2.rectangle(img, (cx - 13, cy - 13), (cx + 13, cy + 13), (52, 64, 84), -1)
            cv2.rectangle(img, (x1, y1), (x2, y2), (215, 228, 240), -1)
            cv2.rectangle(img, (x1, y1), (x2, y2), (140, 160, 180), 2)
        return img

    def render(self, now: float) -> np.ndarray:
        img = self._bg.copy()
        for t in self.tables:
            if t.phase in ("seated", "leaving", "dirty") and t.dirty or t.phase in ("seated", "leaving"):
                for (sx, sy) in (t.seat_points or []):
                    px = int(t.cx + (sx - t.cx) * 0.45)
                    py = int(t.cy + (sy - t.cy) * 0.45)
                    cv2.circle(img, (px, py), 9, (245, 245, 245), -1)
                    cv2.circle(img, (px, py), 9, (170, 180, 190), 1)
            if t.dirty:
                for ox in (-28, 0, 26):
                    cv2.circle(img, (int(t.cx + ox), int(t.cy)), 7, (235, 235, 235), -1)
                    cv2.circle(img, (int(t.cx + ox), int(t.cy)), 3, (60, 90, 150), -1)
        actors = [g for t in self.tables for g in t.guests if g.active(now)] + list(self.staff)
        for a in actors:
            x, y = int(a.pos[0]), int(a.pos[1])
            cv2.ellipse(img, (x, y + 3), (19, 12), 0, 0, 360, a.color, -1)
            cv2.circle(img, (x, y - 2), 8, (160, 190, 230), -1)
            cv2.circle(img, (x, y - 2), 8, (60, 70, 90), 1)
        return img

    def read(self):
        now = self.update()
        return self.render(now), self.detections(now)
