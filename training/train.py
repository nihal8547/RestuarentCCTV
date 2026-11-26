"""Fine-tune YOLOv8 on your restaurant's own footage.

  python training/train.py --data training/data.yaml --epochs 60 --model yolov8s.pt
  -> best weights: runs/restaurant/weights/best.pt  -> copy to backend/models/restaurant.pt
  -> set in .env:  YOLO_MODEL=models/restaurant.pt   (class names customer/staff/table_clean/table_dirty are auto-detected)
"""
import argparse
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="training/data.yaml")
ap.add_argument("--model", default="yolov8s.pt", help="start weights (yolov8n/s/m.pt)")
ap.add_argument("--epochs", type=int, default=60)
ap.add_argument("--imgsz", type=int, default=960)
ap.add_argument("--batch", type=int, default=8)
ap.add_argument("--device", default="", help="'' = auto, '0' = first GPU, 'cpu'")
a = ap.parse_args()

from ultralytics import YOLO  # noqa: E402

data = Path(a.data).resolve()
model = YOLO(a.model)
model.train(data=str(data), epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, device=a.device or None,
            project="runs", name="restaurant", exist_ok=True, patience=20,
            fliplr=0.5, hsv_h=0.015, hsv_s=0.5, hsv_v=0.4, mosaic=1.0)
metrics = model.val()
print("mAP50:", metrics.box.map50, " mAP50-95:", metrics.box.map)
print("best weights: runs/restaurant/weights/best.pt")
