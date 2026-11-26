# How the AI understands your restaurant — and how to train it

## 1. What the camera "sees" (pipeline)

```
CCTV frame (960x540)
   │
   ▼  YOLOv8 object detector  ->  boxes: person, cup/plate/fork/knife/bowl/glass/bottle
   │                              (custom model: customer, staff, table_clean, table_dirty)
   ▼  tracker                 ->  every person keeps a stable #id between frames
   ▼  staff inference         ->  staff or customer?   (uniform colour vote + roaming + custom class)
   ▼  zone mapping            ->  which table zone is each person / item inside?
   ▼  table vision            ->  items on table, difference vs "clean reference" photo
   ▼  state machine           ->  FREE → OCCUPIED → NEEDS CLEANING → FREE  + alerts
   ▼  dashboard / phone alerts / reports
```

### Tables
A table is **not detected by AI** — you define it once: the *Zone editor* (Settings) lets you draw a polygon per table
(T01…T06) on a real camera frame, with seats, section and camera. Why: a fixed polygon is far more reliable than detecting
tables every frame, and it also tells the system *where guests of this table sit*. Optional `table_bbox` = the table top, used for
the clean/dirty check.

### Persons
YOLOv8 finds every person (box + confidence). A person belongs to the table whose polygon contains the person's anchor
point (`ANCHOR=center` for overhead cameras, `foot` for angled cameras). Per table the count is smoothed with a median over
a few frames, so flicker or one missed detection does not change the guest count.

### Customer or staff
| Cue | Idea |
|---|---|
| Uniform colour (HSV) | Upper body pixels in the uniform colour range -> staff. Voted over ~25 frames. Calibrate by clicking a waiter: `GET /api/calibrate/uniform?x=&y=` |
| Roaming | A track that stops at 2+ different tables is serving, not dining -> staff (sticky) |
| Custom `staff` class | After training in the Model Studio the detector itself outputs customer / staff (most accurate) |

### Table state
| State | Becomes true when |
|---|---|
| **OCCUPIED** | >= 1 customer in the zone for `OCCUPY_CONFIRM_SEC`. Timer starts; guest count = smoothed number of customers |
| **Waiter visit** | a staff person stays in/near the zone >= `WAITER_VISIT_SEC` -> visit counted, 5-min no-service alert cleared |
| **NEEDS CLEANING** | customers gone for `LEAVE_CONFIRM_SEC`; or table-ware seen on an empty table; or appearance differs from the clean reference; or `table_dirty` detected |
| **FREE ("Clean Table")** | staff wiped it (dwell `CLEAN_CONFIRM_SEC`), or table matches the clean reference, or `table_clean` detected, or manual button |
| Alerts | `service_wait` (guests, no waiter for `WAIT_ALERT_SEC`), `uncleaned_table` (`CLEAN_ALERT_SEC`), `camera_offline` |

## 2. Why train a custom model?
The stock YOLO model only knows "person" and everyday objects. It does not know *your* uniforms, *your* tables, *your*
camera angle or what "dirty" looks like in your restaurant. Training teaches it exactly that from your own footage.
Expect clearly better staff/customer separation and direct dirty/clean detection.

## 3. How training works (what the Model Studio does for you)
1. **Footage** → upload MP4s from the DVR, or capture frames from the live camera. Frames are resized to the camera resolution and
   near-duplicates are skipped.
2. **Auto-label** → the current model pre-draws boxes: persons (staff by uniform colour) and one box per table (dirty if
   cups/plates are seen). This does ~70-80% of the work.
3. **Label (you)** → in the browser, fix the boxes: 4 classes `customer, staff, table_clean, table_dirty`. Keys 1-4, drag to draw,
   ← → to move on. A realistic first target: **300-500 images**, **>= 50 examples of every class** (especially `table_dirty`).
4. **Train** → the server splits 80/20 train/validation and fine-tunes YOLOv8 (transfer learning from COCO, so it needs far fewer
   images than training from scratch). Progress, mAP and loss are shown live. CPU is slow (hours); a GPU PC / Colab takes ~10-30 min →
   use **Export dataset (.zip)**, train there, then **Import .pt**.
5. **Evaluate** → mAP50 per class on the validation images: >= 0.75 good, 0.5-0.75 usable (watch closely), < 0.5 label more data.
6. **Activate** → one click hot-swaps the model on every camera (no restart). **Roll back to stock** is one click too.
7. **Improve (the loop)** → keep capturing frames where the AI was wrong, label them, retrain (every few weeks). That is how it gets
   production-grade. Keep old models; compare on the Live tab before deleting.

### Tips for good data
* Same camera angle as production; include day, night, rush hour, empty restaurant.
* A table in a frame is either clean or dirty — never both. Box only the table top.
* Include "hard" frames: waiters carrying plates, guests standing, people partly hidden by pillars.
* If one class is rare (dirty tables), capture extra frames right after busy services.

## 4. YOLO setup in production
* **Docker (recommended)**: `INSTALL_YOLO=1` (default in compose) bakes PyTorch + ultralytics + `yolov8n/s` weights into the image, so it runs offline.
  CPU: `docker compose up -d --build`. GPU: `TORCH_INDEX=https://download.pytorch.org/whl/cu121 docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build`.
* **Sizing**: 1-2 cameras @ 5-10 fps → mini PC i5/16 GB with `yolov8n`. 3+ cameras or `yolov8s/m` → NVIDIA GPU (e.g. RTX 3050+) / Jetson Orin.
* **Check**: Model Studio header shows YOLO version, CPU/GPU and ms per frame per camera.
* **Tuning**: `YOLO_CONF` (0.35), `YOLO_IMGSZ` (640; 960 for small/far people), `FPS` (5-10 is enough), `ANCHOR`, `USE_BYTETRACK=1`.
