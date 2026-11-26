"""Pre-label images with the stock YOLOv8 model so you only have to FIX labels, not draw them.

  python scripts/auto_label.py ../training/images --out ../training/labels --zones config/zones.json

* people  -> class 0 (customer) by default; people standing inside a table's zone whose box colour
  matches the uniform (--staff-hsv) are written as class 1 (staff). Review these in your labelling tool!
* table_clean / table_dirty (classes 2/3) can NOT be guessed automatically: each table zone gets a
  *suggested* box (table_bbox from zones.json) labelled with --table-default (clean). You then flip the
  wrong ones to table_dirty in the labelling tool. Use --no-tables to skip.

Output: YOLO txt files (class cx cy w h, normalised) next to the same file stems.
Class order: 0 customer, 1 staff, 2 table_clean, 3 table_dirty   (must match training/data.yaml)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

CLASSES = ["customer", "staff", "table_clean", "table_dirty"]


def yolo_line(cls: int, x1: float, y1: float, x2: float, y2: float, w: int, h: int) -> str:
    return f"{cls} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("images")
    ap.add_argument("--out", default="../training/labels")
    ap.add_argument("--model", default="yolov8n.pt")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--zones", default="config/zones.json")
    ap.add_argument("--no-tables", action="store_true")
    ap.add_argument("--table-default", choices=["clean", "dirty"], default="clean")
    ap.add_argument("--staff-hsv", default="", help="'h1,s1,v1,h2,s2,v2' HSV range of the uniform (optional)")
    a = ap.parse_args()

    from ultralytics import YOLO  # imported late so --help works without it

    model = YOLO(a.model)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    zones = json.loads(Path(a.zones).read_text()) if Path(a.zones).exists() else {"tables": []}
    hsv = [int(v) for v in a.staff_hsv.split(",")] if a.staff_hsv else None
    imgs = sorted(p for p in Path(a.images).iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    for p in imgs:
        frame = cv2.imread(str(p))
        if frame is None:
            continue
        h, w = frame.shape[:2]
        lines = []
        for r in model.predict(frame, classes=[0], conf=a.conf, verbose=False):
            for b in r.boxes:
                x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                cls = 0
                if hsv:
                    roi = cv2.cvtColor(frame[int(y1):int(y2), int(x1):int(x2)], cv2.COLOR_BGR2HSV)
                    if roi.size:
                        m = cv2.inRange(roi, tuple(hsv[:3]), tuple(hsv[3:]))
                        if m.mean() / 255 > 0.15:
                            cls = 1
                lines.append(yolo_line(cls, x1, y1, x2, y2, w, h))
        if not a.no_tables:
            sx, sy = w / 960, h / 540   # zones.json is defined on a 960x540 frame
            cls = 2 if a.table_default == "clean" else 3
            for t in zones.get("tables", []):
                bx = t.get("table_bbox")
                if bx:
                    lines.append(yolo_line(cls, bx[0] * sx, bx[1] * sy, bx[2] * sx, bx[3] * sy, w, h))
        (out / f"{p.stem}.txt").write_text("\n".join(lines))
    print(f"labelled {len(imgs)} images -> {out}")
    print("NEXT: open images+labels in Roboflow / CVAT / Label Studio, fix wrong boxes, flip dirty tables to table_dirty.")


if __name__ == "__main__":
    main()
