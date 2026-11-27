"""Run the REAL AI pipeline over a video file as fast as possible and report what it understood.

  python scripts/analyze_video.py my_restaurant.mp4 --out report/ [--zones config/zones.json] [--model yolov8n.pt]
                                  [--step 3] [--max-seconds 600] [--no-video]

* Uses a synthetic clock (video time), so a 30-minute clip with the real 5-min / 2-min alert thresholds is
  analysed in a few minutes instead of 30.
* Writes  report/summary.json, report/summary.txt and report/annotated.mp4 (same overlay as the live dashboard).
* Use it to (1) check the zones fit, (2) see guest counts / staff detection / alerts on YOUR footage before going live.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="report")
    ap.add_argument("--zones", default=str(ROOT / "config" / "zones.json"))
    ap.add_argument("--model", default=os.getenv("YOLO_MODEL", "yolov8n.pt"))
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--step", type=int, default=3, help="analyse every Nth frame (video fps 25 -> ~8 fps)")
    ap.add_argument("--max-seconds", type=float, default=0, help="stop after this much video time (0 = whole video)")
    ap.add_argument("--demo-thresholds", action="store_true", help="30s/20s alerts instead of 300s/120s")
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args()

    os.environ.update({"DB_PATH": str(Path(tempfile.mkdtemp()) / "an.db"), "ZONES_FILE": a.zones,
                       "VIDEO_SOURCE": a.video, **({"WAIT_ALERT_SEC": "30", "CLEAN_ALERT_SEC": "20"} if a.demo_thresholds else {}),
                       "AUTH_ENABLED": "0"})
    from app.annotator import annotate
    from app.config import load_settings
    from app.db import Database
    from app.detector import YoloDetector
    from app.pipeline import Pipeline
    from app.tracker import SimpleTracker

    s = load_settings()
    db = Database(s.db_path)
    pipe = Pipeline(s, db)
    cam = pipe.cam_ids[0]
    worker = pipe.workers[cam]
    det = YoloDetector(a.model, s.yolo_conf, a.imgsz, s.yolo_device, *pipe.uniform(), s.staff_pixel_ratio, False)
    tracker = SimpleTracker()

    cap = cv2.VideoCapture(a.video)
    if not cap.isOpened():
        sys.exit(f"cannot open {a.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    W, H = pipe.size
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    writer = None if a.no_video else cv2.VideoWriter(str(out / "annotated.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                                                     max(1.0, fps / a.step), (W, H))
    t0 = 1_700_000_000.0
    occ_sec: dict[str, float] = defaultdict(float)
    max_guests: dict[str, int] = defaultdict(int)
    n_people = n_staff = frames = 0
    staff_tracks: set[int] = set()
    cust_tracks: set[int] = set()
    timeline = []
    started, i, last_now = time.time(), 0, t0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        i += 1
        if (i - 1) % a.step:
            continue
        vt = (i - 1) / fps
        if a.max_seconds and vt > a.max_seconds:
            break
        now = t0 + vt
        frame = cv2.resize(frame, (W, H))
        worker.last_frame_ts, worker.last_raw = now, frame
        dets = tracker.update(det.detect(frame))
        dets = pipe.infer_staff(cam, dets, now)
        pipe.process(cam, dets, now, frame)
        snap = pipe._build_snapshot(now)
        dt = now - last_now
        last_now = now
        for t in snap["tables"]:
            if t["state"] == "OCCUPIED":
                occ_sec[t["id"]] += dt
                max_guests[t["id"]] = max(max_guests[t["id"]], t["guests"])
        for d in dets:
            if d.cls == "person":
                n_people += 1
                if d.is_staff:
                    n_staff += 1
                    staff_tracks.add(d.track_id)
                elif d.track_id is not None:
                    cust_tracks.add(d.track_id)
        if frames % 10 == 0:
            timeline.append({"t": round(vt, 1), **{t["id"]: t["state"] for t in snap["tables"]}})
        frames += 1
        if writer is not None:
            writer.write(annotate(frame, snap["tables"], dets, "yolo", s.anchor, fps / a.step))
        if frames % 50 == 0:
            print(f"\r{vt:6.0f}s / {total / fps:.0f}s  frames={frames}", end="", flush=True)
    cap.release()
    if writer is not None:
        writer.release()
    wall = time.time() - started
    events = db.recent_events(10_000)
    ev_count: dict[str, int] = defaultdict(int)
    for e in events:
        ev_count[e["type"]] += 1
    alerts = [a_ for a_ in db.alerts_since(0, 1000)]
    summary = {
        "video": a.video, "video_seconds": round(last_now - t0, 1), "analysed_frames": frames,
        "wall_seconds": round(wall, 1), "analysis_fps": round(frames / max(wall, 1e-6), 1),
        "thresholds": {"wait_alert_sec": pipe.th.wait_alert_sec, "clean_alert_sec": pipe.th.clean_alert_sec},
        "person_detections": n_people, "staff_detections": n_staff,
        "distinct_tracks": {"customer": len(cust_tracks), "staff": len(staff_tracks)},
        "tables": {tid: {"occupied_seconds": round(occ_sec[tid]), "max_guests": max_guests[tid]} for tid in sorted(pipe.geometry)},
        "events": dict(ev_count),
        "alerts": [{"kind": x["kind"], "table": x["table_id"], "message": x["message"]} for x in alerts],
        "timeline_sample": timeline[:200],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    lines = [f"Video: {a.video} ({summary['video_seconds']} s analysed in {summary['wall_seconds']} s, "
             f"{summary['analysis_fps']} fps)",
             f"People detections: {n_people} (staff {n_staff}); distinct tracks: {len(cust_tracks)} customer / {len(staff_tracks)} staff",
             "Per table:"]
    lines += [f"  {tid}: occupied {v['occupied_seconds']} s, max guests {v['max_guests']}" for tid, v in summary["tables"].items()]
    lines += [f"Events: {dict(ev_count)}", f"Alerts: {len(alerts)}"] + [f"  - {x['message']}" for x in alerts[:15]]
    (out / "summary.txt").write_text("\n".join(lines))
    print("\n" + "\n".join(lines))
    print(f"\nWrote {out}/summary.json, summary.txt" + ("" if a.no_video else ", annotated.mp4"))


if __name__ == "__main__":
    main()
