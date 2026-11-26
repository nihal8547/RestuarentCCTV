> **Easier:** the dashboard now has a **Model Studio** tab that does all of this in the browser (upload video, label, train, activate).
> See `docs/HOW_IT_WORKS.md`. The scripts below are for training on a separate GPU machine.

# Training your own model (customer / staff / table_clean / table_dirty)

Stock YOLOv8 only knows "person". That is enough for the MVP (staff is guessed by uniform colour and
"Clean Table / occupied" is derived by the state machine). Train a custom model when:

* the uniform-colour trick confuses staff and customers, **or**
* you want the camera to *see* a table is dirty / clean (plates, glasses left behind) instead of relying on
  "guests left + nobody cleaned it".

## Classes (order matters - must match `data.yaml`)
| id | class | what to box |
|----|-------|-------------|
| 0 | customer | seated/standing guests |
| 1 | staff | waiters / bussers (anyone in uniform) |
| 2 | table_clean | an empty, wiped, laid table (box the table top) |
| 3 | table_dirty | table with leftover plates, glasses, napkins |

## Steps
1. **Record footage** - 2-3 days of real CCTV, lunch + dinner, empty and busy.  
   Put MP4s in `samples/`.
2. **Extract varied frames** (about 300-800 is a good first dataset):
   `python backend/scripts/extract_frames.py samples/*.mp4 --out training/images --every 3 --max 300`
3. **Pre-label with the stock model** (saves ~80% of the drawing work):
   `python backend/scripts/auto_label.py training/images --out training/labels --zones backend/config/zones.json`
   People get class 0 (add `--staff-hsv` to guess staff); each table gets a suggested `table_clean` box.
4. **Fix labels** in a labelling tool (all free): Roboflow, CVAT or Label Studio. Import images + YOLO txt,
   then: delete false boxes, relabel staff, change the table boxes that are really dirty to `table_dirty`.
   Aim for at least 100 `table_dirty` examples - this is the rare class.
5. **Split**: `python training/split_dataset.py`
6. **Train** (GPU strongly recommended; Colab free GPU works):
   `python training/train.py --model yolov8s.pt --epochs 60`
7. **Deploy**: copy `runs/restaurant/weights/best.pt` to `backend/models/restaurant.pt`, set
   `YOLO_MODEL=models/restaurant.pt` in `.env`, restart. The detector reads the class names, so no code change.

## How the app uses the two table classes
* `table_dirty` seen inside a FREE table's zone for >= 3 s -> state **NEEDS CLEANING** (+ cleaning timer/alert).
* `table_clean` seen inside a NEEDS-CLEANING table's zone for >= 3 s -> table reset to **FREE** (same as a waiter wiping it).
* Both signals are optional. Without them the system works exactly as before.
* Staff can always override from the dashboard (click a table -> Mark cleaned).

## Tips
* Label the *same camera angle* you will deploy on; a model trained on another venue generalises poorly.
* Include night / low-light and a few "lunch rush" frames.
* Re-train every few weeks with frames where the model was wrong (hard examples).
* Check `runs/restaurant/results.png`: mAP50 above ~0.8 for customer/staff and ~0.7 for the table classes is usable.
