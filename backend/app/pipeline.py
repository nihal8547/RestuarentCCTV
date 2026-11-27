"""Core engine.

CameraWorker (1 thread / camera): frame source -> detections -> tracker -> Pipeline.process()
Pipeline (monitor thread): owns table state machines, alerts, DB writes, snapshots, camera-offline watchdog.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque

from pathlib import Path

import cv2
import numpy as np

from .annotator import annotate
from .config import Settings
from .db import Database
from .detector import Detection, YoloDetector
from .notifier import Notifier
from .simulator import Simulator
from .state_machine import TableTracker, Thresholds
from .staff_infer import StaffInferer
from .table_vision import TableVision
from .tracker import SimpleTracker
from .training import active_model_path

log = logging.getLogger("pipeline")


class VideoSource:
    """MP4 file (looped) or RTSP/HTTP stream with auto-reconnect."""

    def __init__(self, source: str, size: tuple[int, int]):
        self.source, self.size = source, size
        self.is_file = not source.lower().startswith(("rtsp://", "rtmp://", "http://", "https://"))
        self.cap: cv2.VideoCapture | None = None
        self._t0 = time.time()
        self._pos = 0
        self._open()

    def _open(self) -> None:
        self.cap = cv2.VideoCapture(self.source)
        if not self.is_file:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            self.native_fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
            if not 1 <= self.native_fps <= 120:
                self.native_fps = 25.0
            self._t0, self._pos = time.time(), 0

    def read(self) -> np.ndarray | None:
        if self.cap is None or not self.cap.isOpened():
            time.sleep(2)
            self._open()
            return None
        if self.is_file:   # play in real time: if analysis is slower than the video, skip frames instead of slow-motion
            target = int((time.time() - self._t0) * self.native_fps)
            while self._pos < target - 1 and self.cap.grab():
                self._pos += 1
        ok, frame = self.cap.read()
        self._pos += 1
        if not ok:
            if self.is_file:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self._t0, self._pos = time.time(), 0
            else:
                log.warning("stream lost, reconnecting...")
                self.cap.release()
                time.sleep(2)
                self._open()
            return None
        return cv2.resize(frame, self.size)


class CameraWorker(threading.Thread):
    def __init__(self, pipe: "Pipeline", cam_id: str, spec: str):
        super().__init__(daemon=True, name=f"cam-{cam_id}")
        self.pipe, self.cam_id, self.spec = pipe, cam_id, spec
        self.is_sim = spec == "sim"
        self.tracker = SimpleTracker()
        self.cond = threading.Condition()
        self.jpeg = b""
        self.frame_id = 0
        self.started_ts = time.time()
        self.last_frame_ts = 0.0
        self.fps = 0.0
        self.last_raw: np.ndarray | None = None
        self.last_dets: list | None = None
        self.detect_ms = 0.0
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def online(self, now: float) -> bool:
        ref = self.last_frame_ts or self.started_ts
        if self.last_frame_ts == 0.0:  # never produced a frame: allow a startup grace period
            return now - ref < max(30.0, self.pipe.s.camera_offline_sec * 3)
        return now - ref < self.pipe.s.camera_offline_sec

    def _publish(self, img: np.ndarray) -> None:
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), self.pipe.s.jpeg_quality])
        if ok:
            with self.cond:
                self.jpeg = buf.tobytes()
                self.frame_id += 1
                self.cond.notify_all()

    def _placeholder(self) -> np.ndarray:
        w, h = self.pipe.size
        img = np.full((h, w, 3), (30, 30, 36), np.uint8)
        cv2.putText(img, "CAMERA OFFLINE", (w // 2 - 190, h // 2 - 5), cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                    (60, 60, 230), 3, cv2.LINE_AA)
        cv2.putText(img, f"{self.cam_id} - AI monitoring paused", (w // 2 - 170, h // 2 + 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (170, 170, 170), 1, cv2.LINE_AA)
        return img

    def _make_detector(self) -> YoloDetector:
        s = self.pipe.s
        lo, hi = self.pipe.uniform()
        return YoloDetector(self.pipe.model_path(), s.yolo_conf, s.yolo_imgsz, s.yolo_device,
                            lo, hi, s.staff_pixel_ratio, s.use_bytetrack)

    def run(self) -> None:
        s = self.pipe.s
        gen = ugen = 0
        try:
            if self.is_sim:
                source, detector = Simulator(self.pipe.zones, s.wait_alert_sec, s.clean_alert_sec), None
            else:
                source = VideoSource(self.spec, self.pipe.size)
                detector = self._make_detector()
                gen = self.pipe.model_gen
        except Exception:
            log.exception("camera %s could not start", self.cam_id)
            while not self._stop.is_set():  # keep showing the offline placeholder
                self._publish(self._placeholder())
                time.sleep(1)
            return
        period = 1.0 / max(1.0, s.fps)
        ticks: deque[float] = deque(maxlen=30)
        while not self._stop.is_set():
            t0 = time.time()
            try:
                if self.is_sim:
                    frame, dets = source.read()
                else:
                    frame = source.read()
                    if frame is None:
                        if time.time() - (self.last_frame_ts or self.started_ts) > s.camera_offline_sec:
                            self._publish(self._placeholder())
                            time.sleep(0.5)
                        continue
                    if detector is not None and gen != self.pipe.model_gen:
                        try:
                            detector, gen = self._make_detector(), self.pipe.model_gen
                            self.tracker = SimpleTracker()
                            log.info("camera %s: model reloaded (%s)", self.cam_id, self.pipe.model_path())
                        except Exception:
                            log.exception("model reload failed - keeping previous model")
                            gen = self.pipe.model_gen
                    if detector is not None and ugen != self.pipe.uniform_gen:
                        detector.set_uniform(*self.pipe.uniform())
                        ugen = self.pipe.uniform_gen
                    t_det = time.time()
                    dets = detector.detect(frame)
                    self.detect_ms = 0.8 * self.detect_ms + 0.2 * (time.time() - t_det) * 1000
                now = time.time()
                self.last_frame_ts = now
                self.last_raw = frame
                self.last_dets = dets
                if not (detector and detector.use_bytetrack):
                    dets = self.tracker.update(dets)
                if s.staff_infer and not self.is_sim:
                    dets = self.pipe.infer_staff(self.cam_id, dets, now)
                self.pipe.process(self.cam_id, dets, now, frame)
                ticks.append(now)
                if len(ticks) > 1:
                    self.fps = (len(ticks) - 1) / max(1e-6, ticks[-1] - ticks[0])
                tables = [t for t in self.pipe.get_snapshot().get("tables", []) if t["camera"] == self.cam_id]
                self._publish(annotate(frame, tables, dets, "sim" if self.is_sim else "yolo", s.anchor, self.fps))
            except Exception:
                log.exception("camera %s iteration failed", self.cam_id)
                time.sleep(0.5)
            rest = period - (time.time() - t0)
            if rest > 0:
                time.sleep(rest)


class Pipeline(threading.Thread):
    def __init__(self, settings: Settings, db: Database):
        super().__init__(daemon=True, name="pipeline")
        self.s, self.db = settings, db
        self.zones = self._initial_zones()
        self.size = (self.zones["frame"]["width"], self.zones["frame"]["height"])
        self.th = Thresholds(
            wait_alert_sec=settings.wait_alert_sec, clean_alert_sec=settings.clean_alert_sec,
            occupy_confirm_sec=settings.occupy_confirm_sec, leave_confirm_sec=settings.leave_confirm_sec,
            waiter_visit_sec=settings.waiter_visit_sec, clean_confirm_sec=settings.clean_confirm_sec,
            count_window=settings.count_window)
        for cid, spec in (db.get_settings().get("camera_sources") or {}).items():   # sources chosen in the UI
            if cid in settings.cameras:
                settings.cameras[cid] = spec
        self.mode = "sim" if all(v == "sim" for v in settings.cameras.values()) else "yolo"
        self.cam_ids = list(settings.cameras)
        self.model_gen = 0
        self.uniform_gen = 0
        self.trackers: list[TableTracker] = []
        self.vision = TableVision(Path(settings.db_path).parent / "table_refs", settings.table_diff_thr, settings.item_min)
        self._vis_info: dict[str, dict] = {}
        self._inferers: dict[str, StaffInferer] = {}
        self.polys: dict[str, np.ndarray] = {}
        self.geometry: dict[str, dict] = {}
        self._proc_lock = threading.RLock()
        self._lock = threading.Lock()
        self._build_tables(self.zones)
        self.workers = {cid: CameraWorker(self, cid, spec) for cid, spec in settings.cameras.items()}
        self._stop_ev = threading.Event()
        self._snapshot: dict = {}
        self._dirty = True
        self._active_alerts: dict[tuple[str, str], int] = {}
        self.alert_feed: deque[dict] = deque(maxlen=60)
        self.notifier = Notifier(name_fn=lambda: self.s.restaurant_name)
        self._load_recent_alerts()

    # ------------------------------------------------------------- zones
    def _initial_zones(self) -> dict:
        override = self.db.get_settings().get("zones")
        return override if override else self.s.load_zones()

    def _build_tables(self, zones: dict) -> None:
        old = {t.id: t for t in self.trackers}
        trackers, polys, geom = [], {}, {}
        for z in zones["tables"]:
            t = old.get(z["id"]) or TableTracker(z["id"], z["number"], z["seats"], z["section"], self.th)
            t.number, t.seats, t.section = z["number"], z["seats"], z["section"]
            trackers.append(t)
            polys[z["id"]] = np.array(z["polygon"], dtype=np.float32).reshape(-1, 1, 2)
            xs, ys = [p[0] for p in z["polygon"]], [p[1] for p in z["polygon"]]
            geom[z["id"]] = {
                "zone": [min(xs), min(ys), max(xs), max(ys)], "polygon": z["polygon"],
                "bbox": z.get("table_bbox") or [(min(xs) + max(xs)) // 2 - 45, (min(ys) + max(ys)) // 2 - 35,
                                                (min(xs) + max(xs)) // 2 + 45, (min(ys) + max(ys)) // 2 + 35],
                "shape": z.get("shape", "rect"),
                "camera": z.get("camera") if z.get("camera") in self.cam_ids else self.cam_ids[0],
            }
        self.trackers, self.polys, self.geometry, self.zones = trackers, polys, geom, zones

    # ---------------------------------------------- fit zones to the real video
    def _probe_frame(self, spec: str):
        cap = cv2.VideoCapture(spec)
        try:
            for _ in range(5):
                ok, fr = cap.read()
                if ok:
                    return fr
        finally:
            cap.release()
        return None

    def _auto_zones(self, frame: np.ndarray, size: tuple[int, int], old: dict) -> dict:
        """Table zones for a new video: YOLO 'dining table' boxes if available, else an editable 3x2 grid."""
        w, h = size
        boxes: list[list[int]] = []
        try:
            from ultralytics import YOLO
            res = YOLO(self.model_path())(cv2.resize(frame, size), conf=0.15, imgsz=self.s.yolo_imgsz, verbose=False)[0]
            names = res.names
            for b in res.boxes:
                if names[int(b.cls)] in ("dining table", "table_clean", "table_dirty"):
                    boxes.append([int(v) for v in b.xyxy[0].tolist()])
        except Exception:
            log.info("auto table detection unavailable - using a grid")
        boxes = sorted(boxes, key=lambda b: (b[1] // max(1, h // 3), b[0]))[:12]
        if not boxes:                                   # fallback: 3 columns x 2 rows
            cw, ch = w // 3, h // 2
            boxes = [[c * cw + 30, r * ch + 30, (c + 1) * cw - 30, (r + 1) * ch - 30] for r in range(2) for c in range(3)]
        tables = []
        for i, (x1, y1, x2, y2) in enumerate(boxes, 1):
            px, py = int((x2 - x1) * 0.35), int((y2 - y1) * 0.35)      # margin so people sitting around count
            x1, y1, x2, y2 = max(0, x1 - px), max(0, y1 - py), min(w, x2 + px), min(h, y2 + py)
            tables.append({"id": f"T{i:02d}", "number": i, "seats": 4, "section": "A", "shape": "rect",
                           "camera": self.cam_ids[0], "polygon": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
                           "table_bbox": None})
        return {"frame": {"width": w, "height": h}, "sections": [{"id": "A", "name": "Section A"}], "tables": tables}

    def _fit_to_source(self, spec: str) -> None:
        """Real video: use its aspect ratio and fresh table zones (the default zones would not match). sim: restore the default zones."""
        if spec == "sim":
            zones = self.s.load_zones()
            self.size = (zones["frame"]["width"], zones["frame"]["height"])
            self.db.set_setting("zones", None)
        else:
            fr = self._probe_frame(spec)
            if fr is None:
                return
            fh, fw = fr.shape[:2]
            self.size = (960, max(240, int(round(960 * fh / fw / 2)) * 2))
            zones = self._auto_zones(fr, self.size, self.zones)
            self.db.set_setting("zones", zones)
        with self._proc_lock:
            self._build_tables(zones)
            self.trackers = [TableTracker(t.id, t.number, t.seats, t.section, self.th) for t in self.trackers]

    def set_source(self, cam: str, spec: str) -> None:
        """Switch a camera to another source at runtime (sim / video file / RTSP) and persist it."""
        if cam not in self.workers:
            raise KeyError(cam)
        self.workers[cam].stop()
        if len(self.cam_ids) == 1:
            self._fit_to_source(spec)
        w = CameraWorker(self, cam, spec)
        self.workers[cam] = w
        self.s.cameras[cam] = spec
        self.mode = "sim" if all(v == "sim" for v in self.s.cameras.values()) else "yolo"
        self._inferers.pop(cam, None)
        with self._proc_lock:                       # fresh table state for this camera's tables
            self.trackers = [TableTracker(t.id, t.number, t.seats, t.section, self.th)
                             if self.geometry[t.id]["camera"] == cam else t for t in self.trackers]
        for (ref, kind) in list(self._active_alerts):
            if self.geometry.get(ref, {}).get("camera") == cam or ref == cam:
                self._resolve_alert(time.time(), kind, ref, "video source changed")
        src = dict(self.db.get_settings().get("camera_sources") or {})
        src[cam] = spec
        self.db.set_setting("camera_sources", src)
        if self.is_alive():
            w.start()
        self._dirty = True

    def uniform(self):
        u = self.db.get_settings().get("uniform_hsv")
        if u:
            return tuple(u["low"]), tuple(u["high"])
        return self.s.staff_hsv_low, self.s.staff_hsv_high

    def set_uniform(self, low, high) -> None:
        self.db.set_setting("uniform_hsv", {"low": list(low), "high": list(high)} if low else None)
        self.uniform_gen += 1

    def model_path(self) -> str:
        return active_model_path(self.s, self.db)

    def reload_models(self) -> None:
        self.model_gen += 1

    def reload_zones(self, zones: dict) -> None:
        with self._proc_lock:
            self._build_tables(zones)
            self._dirty = True

    def apply_settings(self) -> None:
        """Push runtime-editable settings into the live thresholds."""
        for k in ("wait_alert_sec", "clean_alert_sec", "occupy_confirm_sec", "leave_confirm_sec",
                  "waiter_visit_sec", "clean_confirm_sec"):
            setattr(self.th, k, float(getattr(self.s, k)))
        self._dirty = True

    # ------------------------------------------------------------ public
    def start(self) -> None:  # type: ignore[override]
        super().start()
        for w in self.workers.values():
            w.start()

    def stop(self) -> None:
        self._stop_ev.set()
        for w in self.workers.values():
            w.stop()

    def get_snapshot(self) -> dict:
        with self._lock:
            return self._snapshot

    def wait_frame(self, last_id: int, timeout: float = 1.0, cam: str | None = None) -> tuple[int, bytes]:
        w = self.workers.get(cam or self.cam_ids[0]) or self.workers[self.cam_ids[0]]
        with w.cond:
            w.cond.wait_for(lambda: w.frame_id != last_id, timeout=timeout)
            return w.frame_id, w.jpeg

    def raw_jpeg(self, cam: str | None = None) -> bytes:
        """Un-annotated frame (used by the zone editor)."""
        w = self.workers.get(cam or self.cam_ids[0]) or self.workers[self.cam_ids[0]]
        if w.last_raw is None:
            return b""
        ok, buf = cv2.imencode(".jpg", w.last_raw, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return buf.tobytes() if ok else b""

    def ack_alert(self, alert_id: int, by: str | None = None) -> bool:
        self.db.ack_alert(alert_id, by)
        with self._lock:
            for a in self.alert_feed:
                if a["id"] == alert_id:
                    a["acked"], a["ack_by"] = True, by or a.get("ack_by")
                    self._dirty = True
                    return True
        return False

    def _load_recent_alerts(self) -> None:
        now = time.time()
        self.db.close_open_alerts(now)
        for r in reversed(self.db.alerts_since(now - 2 * 3600, 30)):
            self.alert_feed.append(self._alert_dict(r))

    @staticmethod
    def _alert_dict(r: dict) -> dict:
        try:
            params = json.loads(r.get("params") or "{}")
        except Exception:
            params = {}
        return {"id": r["id"], "ts": r["ts"], "kind": r["kind"], "table": r["table_id"],
                "severity": r["severity"], "message": r["message"], "params": params,
                "resolved": r["resolved_ts"] is not None, "acked": bool(r["acked"]), "ack_by": r.get("ack_by")}

    def _zone_counts(self, cam_id: str, dets: list[Detection]) -> dict[str, tuple[int, bool]]:
        res: dict[str, list] = {t.id: [0, False] for t in self.trackers if self.geometry[t.id]["camera"] == cam_id}
        for d in dets:
            if d.cls != "person":
                continue
            pt = d.anchor(self.s.anchor)
            # seated people are often partly hidden and sit at the table edge: test the box centre, the feet and a
            # point slightly above centre, and give each customer to ONE table (the one they are deepest inside)
            cx, h = (d.x1 + d.x2) / 2, d.y2 - d.y1
            pts = [pt, (cx, d.y2), (cx, d.y1 + h * 0.4)]
            if d.is_staff:
                for tid in res:
                    if cv2.pointPolygonTest(self.polys[tid], pt, True) >= -self.s.staff_margin_px:
                        res[tid][1] = True
                continue
            best, best_d = None, 0.0
            for tid in res:
                dist = max(cv2.pointPolygonTest(self.polys[tid], q, True) for q in pts)
                if dist >= -4 and (best is None or dist > best_d):
                    best, best_d = tid, dist
            if best:
                res[best][0] += 1
        return {k: (v[0], v[1]) for k, v in res.items()}

    def _zone_of(self, cam_id: str):
        def f(pt):
            for t in self.trackers:
                if self.geometry[t.id]["camera"] == cam_id and cv2.pointPolygonTest(self.polys[t.id], pt, False) >= 0:
                    return t.id
            return None
        return f

    def infer_staff(self, cam_id: str, dets: list[Detection], now: float) -> list[Detection]:
        inf = self._inferers.get(cam_id)
        if inf is None:
            inf = self._inferers[cam_id] = StaffInferer(self._zone_of(cam_id), self.s.anchor)
        return inf.update(dets, now)

    def set_table_reference(self, table_id: str, clear: bool = False) -> dict:
        g = self.geometry.get(table_id)
        if not g:
            return {"ok": False, "error": "unknown table"}
        if clear:
            self.vision.clear_reference(table_id)
            return {"ok": True}
        w = self.workers.get(g["camera"])
        if w is None or w.last_raw is None:
            return {"ok": False, "error": "no camera frame yet"}
        if not self.vision.set_reference(table_id, w.last_raw, g["bbox"]):
            return {"ok": False, "error": "table_bbox outside the frame"}
        return {"ok": True}

    def _table_signals(self, cam_id: str, dets: list[Detection], counts: dict | None = None,
                       frame=None, now: float = 0.0) -> dict[str, str]:
        """table_clean / table_dirty detections -> 'clean' | 'dirty' per table (dirty wins)."""
        out: dict[str, str] = {}
        for d in dets:
            if d.cls not in ("table_clean", "table_dirty"):
                continue
            pt = ((d.x1 + d.x2) / 2, (d.y1 + d.y2) / 2)
            for t in self.trackers:
                if self.geometry[t.id]["camera"] != cam_id:
                    continue
                if cv2.pointPolygonTest(self.polys[t.id], pt, False) >= 0:
                    kind = "dirty" if d.cls == "table_dirty" else "clean"
                    if out.get(t.id) != "dirty":
                        out[t.id] = kind
        # table-ware items + appearance vs clean reference (only where nobody stands in the zone)
        items: dict[str, int] = {}
        for d in dets:
            if d.cls == "item":
                pt = ((d.x1 + d.x2) / 2, (d.y1 + d.y2) / 2)
                for t in self.trackers:
                    if self.geometry[t.id]["camera"] == cam_id and cv2.pointPolygonTest(self.polys[t.id], pt, False) >= 0:
                        items[t.id] = items.get(t.id, 0) + 1
        for t in self.trackers:
            g = self.geometry[t.id]
            if g["camera"] != cam_id:
                continue
            n_people, staff_here = (counts or {}).get(t.id, (0, False))
            score = None
            if frame is not None and not n_people and not staff_here:
                score = self.vision.measure(t.id, frame, g["bbox"], now)
            self._vis_info[t.id] = {"items": items.get(t.id, 0), "appearance": score, "has_ref": self.vision.has_ref(t.id)}
            if t.id in out or n_people or staff_here:
                continue
            # with a clean reference the appearance cue decides (table settings/glasses are part of the reference)
            sig = self.vision.decide(0 if self.vision.has_ref(t.id) else items.get(t.id, 0), score)
            if sig:
                out[t.id] = sig
        return out

    def manual_action(self, table_id: str, action: str, by: str, now: float) -> dict:
        with self._proc_lock:
            t = next((x for x in self.trackers if x.id == table_id), None)
            if t is None:
                return {"ok": False, "error": "unknown table"}
            ev: list[dict] = []
            if action == "mark_clean":
                ev = t.manual_clean(now)
            elif action == "waiter_visit":
                ev = t.manual_visit(now)
            elif action in ("reserve", "unreserve"):
                ok = t.set_reserved(action == "reserve", by)
                if not ok:
                    return {"ok": False, "error": "table is occupied"}
                self.db.log_event(now, action, t.id, {"by": by})
                self._dirty = True
                return {"ok": True}
            else:
                return {"ok": False, "error": "unknown action"}
            if not ev:
                return {"ok": False, "error": "action not applicable in current state"}
            for e in ev:
                e["by"] = by
            self._dirty = True
            self._handle_events(ev, t, now)
        return {"ok": True}

    def process(self, cam_id: str, dets: list[Detection], now: float, frame=None) -> None:
        with self._proc_lock:
            counts = self._zone_counts(cam_id, dets)
            signals = self._table_signals(cam_id, dets, counts, frame, now)
            for t in self.trackers:
                if t.id not in counts:
                    continue
                n, staff = counts[t.id]
                ev = t.update(now, n, staff, signals.get(t.id))
                if ev:
                    self._dirty = True
                    self._handle_events(ev, t, now)

    def _raise_alert(self, now: float, kind: str, ref_id: str, severity: str, message: str, params: dict) -> None:
        aid = self.db.add_alert(now, kind, ref_id, severity, message, params)
        self._active_alerts[(ref_id, kind)] = aid
        with self._lock:
            self.alert_feed.append({"id": aid, "ts": now, "kind": kind, "table": ref_id, "severity": severity,
                                    "message": message, "params": params, "resolved": False, "acked": False,
                                    "ack_by": None})
        self.notifier.send("alert", {"id": aid, "kind": kind, "table": ref_id, "message": message, "ts": now})
        self._dirty = True
        log.info("ALERT %s %s", ref_id, message)

    def _resolve_alert(self, now: float, kind: str, ref_id: str, reason: str = "") -> None:
        aid = self._active_alerts.pop((ref_id, kind), None)
        if not aid:
            return
        self.db.resolve_alert(aid, now)
        with self._lock:
            for a in self.alert_feed:
                if a["id"] == aid:
                    a["resolved"] = True
        self.notifier.send("resolved", {"id": aid, "kind": kind, "table": ref_id, "message": reason, "ts": now})
        self._dirty = True

    def _handle_events(self, events: list[dict], t: TableTracker, now: float) -> None:
        for e in events:
            typ = e["type"]
            self.db.log_event(now, typ, t.id, {k: v for k, v in e.items() if k not in ("type", "table")})
            if typ == "seated":
                t.session_id = self.db.start_session(t.id, t.seated_since or now, e["guests"])
            elif typ == "waiter_visit":
                self.db.update_session(t.session_id, visits=t.visits, first_visit_ts=t.first_visit)
            elif typ == "departed":
                self.db.update_session(t.session_id, end_ts=e["end_ts"], guests=e["guests"],
                                       visits=e["visits"], first_visit_ts=e["first_visit"])
            elif typ == "cleaned":
                self.db.update_session(t.session_id, cleaned_ts=e["ts_clean"])
                t.session_id = None          # a later clean/dirty cycle must not touch this finished session
            elif typ == "alert":
                self._raise_alert(now, e["kind"], t.id, e["severity"], e["message"], e.get("params", {}))
            elif typ == "alert_resolved":
                self._resolve_alert(now, e["kind"], t.id, e.get("reason", ""))

    def _watch_cameras(self, now: float) -> None:
        for cid, w in self.workers.items():
            online = w.online(now)
            key = (cid, "camera_offline")
            if not online and key not in self._active_alerts:
                secs = int(now - (w.last_frame_ts or w.started_ts))
                self.db.log_event(now, "camera_offline", cid, {})
                self._raise_alert(now, "camera_offline", cid, "critical",
                                  f"Camera {cid} is offline - AI monitoring paused for its tables",
                                  {"camera": cid, "secs": secs})
            elif online and key in self._active_alerts:
                self.db.log_event(now, "camera_online", cid, {})
                self._resolve_alert(now, "camera_offline", cid, "camera back online")

    def _build_snapshot(self, now: float) -> dict:
        cams = {cid: w.online(now) for cid, w in self.workers.items()}
        tables = []
        with self._proc_lock:
            for t in self.trackers:
                d = t.to_dict(now)
                g = self.geometry[t.id]
                d.update(g)
                d.update(self._vis_info.get(t.id, {"items": 0, "appearance": None, "has_ref": self.vision.has_ref(t.id)}))
                d["camera_online"] = cams.get(g["camera"], True)
                tables.append(d)
        occ = [t for t in tables if t["state"] == "OCCUPIED"]
        seat_cap = sum(t["seats"] for t in tables)
        guests = sum(t["guests"] for t in occ)
        sections = []
        for sec in self.zones.get("sections", []):
            ts = [t for t in tables if t["section"] == sec["id"]]
            g = sum(t["guests"] for t in ts if t["state"] == "OCCUPIED")
            cap = sum(t["seats"] for t in ts)
            sections.append({
                "id": sec["id"], "name": sec["name"], "tables": [t["id"] for t in ts], "guests": g, "seats": cap,
                "load_pct": round(100 * g / cap) if cap else 0,
                "occupied_tables": sum(1 for t in ts if t["state"] == "OCCUPIED"),
                "free_tables": sum(1 for t in ts if t["state"] == "FREE" and not t["reserved"])})
        rec = None
        cands = [s for s in sections if s["free_tables"] > 0]
        if cands:
            best = min(cands, key=lambda s: (s["load_pct"], s["occupied_tables"]))
            rec = {"table": next(t["id"] for t in tables if t["section"] == best["id"] and t["state"] == "FREE" and not t["reserved"]),
                   "section": best["id"]}
        with self._lock:
            alerts = sorted(self.alert_feed, key=lambda a: a["ts"], reverse=True)[:30]
        return {
            "ts": now, "mode": self.mode, "restaurant_name": self.s.restaurant_name,
            "fps": round(max([w.fps for w in self.workers.values()] or [0]), 1),
            "cameras": [{"id": cid, "online": cams[cid], "fps": round(w.fps, 1), "sim": w.is_sim,
                         "detect_ms": round(w.detect_ms, 1)}
                        for cid, w in self.workers.items()],
            "restaurant": {
                "capacity_pct": round(100 * guests / seat_cap) if seat_cap else 0,
                "tables_occupied": len(occ), "tables_total": len(tables), "seated_guests": guests,
                "seat_capacity": seat_cap,
                "needs_cleaning": sum(1 for t in tables if t["state"] == "NEEDS_CLEANING")},
            "tables": tables, "sections": sections, "recommendation": rec, "alerts": alerts,
            "thresholds": {"wait_alert_sec": self.th.wait_alert_sec, "clean_alert_sec": self.th.clean_alert_sec}}

    # ---------------------------------------------------------------- loop
    def run(self) -> None:
        last_snap = 0.0
        while not self._stop_ev.is_set():
            try:
                now = time.time()
                self._watch_cameras(now)
                if self._dirty or now - last_snap >= 0.5:
                    self._dirty = False
                    last_snap = now
                    snap = self._build_snapshot(now)
                    with self._lock:
                        self._snapshot = snap
            except Exception:
                log.exception("monitor iteration failed")
            time.sleep(0.2)
