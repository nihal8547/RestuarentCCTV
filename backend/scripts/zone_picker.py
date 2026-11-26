"""Click table zones on a real camera frame and write config/zones.json.

Usage:  python scripts/zone_picker.py rtsp://user:pass@ip/stream   (or video.mp4 / image.jpg)
Keys :  left-click = add polygon point | ENTER = finish table | u = undo point | s = save & quit | q = quit
Run on a computer with a screen (needs OpenCV GUI: pip install opencv-python).
"""
import json
import sys
from pathlib import Path

import cv2

W, H = 960, 540
OUT = Path(__file__).resolve().parents[1] / "config" / "zones.json"


def grab(src):
    if src.lower().endswith((".jpg", ".jpeg", ".png")):
        return cv2.imread(src)
    cap = cv2.VideoCapture(src)
    for _ in range(5):
        ok, f = cap.read()
    cap.release()
    if not ok:
        sys.exit("could not read a frame from the source")
    return f


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    img = cv2.resize(grab(sys.argv[1]), (W, H))
    tables, pts = [], []

    def redraw():
        v = img.copy()
        for t in tables:
            cv2.polylines(v, [__import__("numpy").array(t["polygon"])], True, (0, 220, 0), 2)
            cv2.putText(v, t["id"], tuple(t["polygon"][0]), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        for p in pts:
            cv2.circle(v, tuple(p), 4, (0, 0, 255), -1)
        if len(pts) > 1:
            cv2.polylines(v, [__import__("numpy").array(pts)], False, (0, 0, 255), 1)
        cv2.imshow("zones", v)

    def on_mouse(ev, x, y, *_):
        if ev == cv2.EVENT_LBUTTONDOWN:
            pts.append([x, y])
            redraw()

    cv2.namedWindow("zones")
    cv2.setMouseCallback("zones", on_mouse)
    redraw()
    while True:
        k = cv2.waitKey(50) & 0xFF
        if k == 13 and len(pts) >= 3:  # ENTER
            n = len(tables) + 1
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            cx, cy = (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2
            tables.append({
                "id": f"T{n:02d}", "number": n, "seats": 4, "section": "A", "shape": "rect",
                "polygon": pts[:], "table_bbox": [cx - 45, cy - 35, cx + 45, cy + 35],
            })
            pts.clear()
            redraw()
        elif k == ord("u") and pts:
            pts.pop()
            redraw()
        elif k == ord("s"):
            cfg = json.loads(OUT.read_text()) if OUT.exists() else {"sections": [{"id": "A", "name": "Section A"}]}
            cfg["frame"] = {"width": W, "height": H}
            cfg["tables"] = tables
            OUT.write_text(json.dumps(cfg, indent=2))
            print("saved", OUT, "- now edit seats / section / table_bbox per table")
            break
        elif k == ord("q"):
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
