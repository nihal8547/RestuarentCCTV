"""Extract frames from CCTV video(s) for labelling.

  python scripts/extract_frames.py video.mp4 [more.mp4 ...] --out ../training/images --every 2 --max 400

Takes one frame every N seconds (default 2) and skips near-duplicates, so you get varied images
(different times of day, empty / busy / dirty tables) instead of 400 copies of the same scene.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--out", default="../training/images")
    ap.add_argument("--every", type=float, default=2.0, help="seconds between candidate frames")
    ap.add_argument("--max", type=int, default=400, help="max frames per video")
    ap.add_argument("--min-diff", type=float, default=4.0, help="skip frames more similar than this (mean abs diff)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    for v in a.videos:
        cap = cv2.VideoCapture(v)
        if not cap.isOpened():
            print(f"cannot open {v}")
            continue
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        step = max(1, int(fps * a.every))
        stem, i, saved, prev = Path(v).stem, 0, 0, None
        while saved < a.max:
            ok, frame = cap.read()
            if not ok:
                break
            if i % step == 0:
                small = cv2.cvtColor(cv2.resize(frame, (64, 36)), cv2.COLOR_BGR2GRAY).astype(np.float32)
                if prev is None or float(np.mean(np.abs(small - prev))) >= a.min_diff:
                    cv2.imwrite(str(out / f"{stem}_{i:07d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    prev, saved = small, saved + 1
            i += 1
        cap.release()
        print(f"{v}: saved {saved} frames")
        total += saved
    print(f"done - {total} frames in {out}")


if __name__ == "__main__":
    main()
