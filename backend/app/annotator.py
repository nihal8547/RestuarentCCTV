"""Draws the AI overlay (zones, labels, timers, customers) onto a frame."""
from __future__ import annotations

import time

import cv2
import numpy as np

GREEN = (70, 200, 60)
RED = (50, 50, 235)
AMBER = (0, 165, 255)
BLUE = (235, 150, 50)
WHITE = (255, 255, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _label(img, text, x, y, color, scale=0.55, thick=1, fg=WHITE):
    (w, h), b = cv2.getTextSize(text, FONT, scale, thick)
    x = int(max(0, min(x, img.shape[1] - w - 8)))
    y = int(max(h + b + 4, y))
    cv2.rectangle(img, (x, y - h - b - 4), (x + w + 8, y + 2), color, -1)
    cv2.putText(img, text, (x + 4, y - b), FONT, scale, fg, thick, cv2.LINE_AA)


def annotate(frame: np.ndarray, tables: list[dict], detections: list, mode: str, anchor: str,
             fps: float) -> np.ndarray:
    """`tables` = list of {state dict from TableTracker.to_dict + 'bbox' + 'zone'}"""
    img = frame.copy()
    overlay = img.copy()
    for t in tables:
        color = {"FREE": GREEN, "OCCUPIED": RED, "NEEDS_CLEANING": AMBER}[t["state"]]
        x1, y1, x2, y2 = t["zone"]
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
    cv2.addWeighted(overlay, 0.12, img, 0.88, 0, img)

    for t in tables:
        color = {"FREE": GREEN, "OCCUPIED": RED, "NEEDS_CLEANING": AMBER}[t["state"]]
        x1, y1, x2, y2 = t["zone"]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        n = t["number"]
        if t["state"] == "FREE":
            head, tag = f"T{n:02d} FREE", "Clean Table"
        elif t["state"] == "OCCUPIED":
            g = t["guests"]
            head = f"TABLE {n:02d} / {g} Guest{'s' if g != 1 else ''} / {t['timer']}"
            tag = "occupied"
        else:
            head, tag = f"T{n:02d} NEEDS CLEANING / {t['timer']}", "uncleaned"
        _label(img, head, x1, y1 - 2, color, 0.55, 1)
        # table object box + state tag
        bx1, by1, bx2, by2 = t["bbox"]
        cv2.rectangle(img, (bx1, by1), (bx2, by2), color, 1)
        _label(img, "table", bx1, by1 - 1, color, 0.38, 1)
        _label(img, tag, bx1, by2 + 15, color, 0.38, 1)
        if t["wait_alert"]:
            _label(img, "! NO SERVICE", x1, y2 - 6, (0, 0, 200), 0.5, 1)
        if t["clean_alert"]:
            _label(img, "! BUSS TABLE", x1, y2 - 6, (0, 110, 230), 0.5, 1)

    for d in detections:
        if getattr(d, "cls", "person") == "item":
            cv2.rectangle(frame, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), (0, 180, 255), 1)
            cv2.putText(frame, "item", (int(d.x1), int(d.y1) - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                        (0, 180, 255), 1, cv2.LINE_AA)
            continue
        if getattr(d, "cls", "person") != "person":
            continue
        p1, p2 = (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2))
        if d.is_staff:
            cv2.rectangle(img, p1, p2, BLUE, 1)
            _label(img, f"Staff #{d.track_id}" if d.track_id else "Staff", p1[0], p1[1] - 1, BLUE, 0.36, 1)
        else:
            cv2.rectangle(img, p1, p2, (255, 255, 255), 1)
            _label(img, f"Customer #{d.track_id}" if d.track_id else "Customer", p1[0], p1[1] - 1, (90, 90, 90), 0.36, 1)

    # HUD
    cv2.circle(img, (22, 22), 6, (0, 0, 255), -1)
    cv2.putText(img, f"LIVE  {mode.upper()}  {fps:4.1f} fps  {time.strftime('%H:%M:%S')}",
                (36, 27), FONT, 0.5, WHITE, 1, cv2.LINE_AA)
    return img
