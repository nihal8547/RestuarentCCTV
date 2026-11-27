# Smart Restaurant Table Management — CCTV AI (MVP)

Real-time table occupancy, staff alerts and weekly analytics, built on a restaurant's **existing CCTV cameras** (no new hardware).

![live](docs/live.png)

## 1. What it does

| Feature | How |
|---|---|
| Table states `T01–T06` | Free (green) · Occupied (red, guest count + `MM:SS` timer) · Needs cleaning (amber) |
| Annotated CCTV feed | Zone boxes, `Customer`, `Staff`, `table`, `occupied`, `Clean Table` labels |
| 5-minute service alert | Guests seated, no waiter inside the zone for `WAIT_ALERT_SEC` |
| Uncleaned table alert | Guests left, table not reset within `CLEAN_ALERT_SEC` |
| Live host floor | 2D floor plan synced over WebSocket, section balance, "next party → seat at Tx" |
| Weekly analytics | Peak hours, footfall heatmap, daily guests, table turns, avg table time, clean turnaround |

## 2. Architecture

```
CCTV RTSP / MP4 / Simulator
        │
        ▼
 pipeline.py (thread)  ── YOLOv8 person detection (detector.py)
        │                 staff vs customer by uniform colour (HSV)
        ▼
 zones.json polygons ──► count customers / detect staff per table
        ▼
 state_machine.py  FREE ─► OCCUPIED ─► NEEDS_CLEANING ─► FREE
        │  events: seated, waiter_visit, departed, cleaned, alert, alert_resolved
        ▼
 SQLite (events, sessions, alerts)        annotator.py → JPEG
        ▼                                         ▼
 FastAPI  /ws (state, 2 Hz)  /api/*  /video_feed (MJPEG)
        ▼
 React + Tailwind dashboard
```

### Folder structure
```
restaurant-ai/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI: REST, WebSocket, MJPEG, serves built UI
│   │   ├── pipeline.py        frame loop: detect → zones → state machine → DB → JPEG/snapshot
│   │   ├── state_machine.py   per-table logic + alerts (pure, unit-tested)
│   │   ├── detector.py        YOLOv8 wrapper + staff colour classifier
│   │   ├── simulator.py       realistic restaurant simulator (no camera needed)
│   │   ├── annotator.py       draws boxes / labels / timers
│   │   ├── analytics.py       weekly report queries
│   │   ├── db.py              SQLite layer
│   │   └── config.py          env-driven settings
│   ├── config/zones.json      table polygons, seats, sections
│   ├── scripts/zone_picker.py click tool to draw zones on a real camera frame
│   └── tests/test_state_machine.py
├── frontend/                  Vite + React + Tailwind + Recharts
│   └── src/components/        OccupancyHeader, LiveFeed, FloorPlan, AlertPanel, Analytics
├── deploy/                    Caddyfile (HTTPS + auth), systemd unit
├── Dockerfile · docker-compose.yml · .env.example · run_simulator.sh
```

## 3. Run with the simulator (no camera, no model)

Requirements: Python 3.10+, Node 18+.

**One command (Linux/macOS):**
```bash
./run_simulator.sh            # then open http://localhost:8000
```
**Windows:** double-click `run_simulator.bat`.

**Manual / dev mode (hot reload):**
```bash
# terminal 1 – backend
cd backend
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# terminal 2 – frontend
cd frontend
npm install
npm run dev                                           # http://localhost:5173
```

The simulator seats guests, sends waiters, and deliberately makes some visits/cleanings late so both alert types fire.
Thresholds are the real ones (5 min no waiter / 2 min uncleaned); the simulator runs at matching real-life pace. Shorten with `WAIT_ALERT_SEC` / `CLEAN_ALERT_SEC` or in Settings.

Tests: `cd backend && python -m pytest -q` (37 tests: state machine, tracker, auth/roles, settings, zones, camera-offline, reports, hub)

First login when `ADMIN_PASSWORD` is set: user `ADMIN_USER` (default `manager`). If auth is enabled without a password, an `admin` owner is created and its password is printed once in the server log.

## 4. Connect the existing CCTV

1. **Get the RTSP URL** (enable RTSP on the DVR/NVR, create a read-only user, use the *sub-stream* ~720p):
   - Hikvision `rtsp://user:pass@IP:554/Streaming/Channels/102`
   - Dahua / CP Plus `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=1`
2. Test it in VLC first (Media → Open Network Stream).
3. Install the detector: `pip install -r backend/requirements-yolo.txt`
4. Draw zones: `python backend/scripts/zone_picker.py "rtsp://..."` (click each table, ENTER, then `s`), then edit `seats`, `section`, `table_bbox` in `config/zones.json`.
5. Run:
   ```bash
   VIDEO_SOURCE="rtsp://user:pass@192.168.1.64:554/Streaming/Channels/102" \
   ANCHOR=foot \
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   `ANCHOR=center` suits overhead cameras, `foot` suits angled cameras (uses the person's feet to decide which table they are at).
6. Set the waiter uniform colour range with `STAFF_HSV_LOW/HIGH` (OpenCV HSV) so staff are not counted as guests.

Camera placement tips: overhead or high-angle, tables not hidden behind pillars, good lighting, 720p+.

## 5. Honest limitations (MVP) and the roadmap

* YOLOv8 (COCO) detects **people only**. `Clean Table` / `occupied` are derived by the state machine (guests present, staff dwell). For higher accuracy on real footage, **train a custom YOLO model** with classes `customer, staff, table_clean, table_dirty` on ~500–1000 labelled frames from the restaurant, and swap it in `detector.py`.
* Staff recognition relies on a uniform colour. Without a distinct uniform, add a staff classifier or an ID-badge colour.
* Overlapping people in busy scenes can undercount; the median smoothing handles flicker, not long occlusion.
* Login/roles are built in, but for internet exposure also put it behind HTTPS (Caddy) and set `AUTH_SECRET`.
* Still to do for scale: PostgreSQL for the hub, per-tenant users on the hub, retry queue for failed notifications, camera-calibrated seat detection.
* Legal: get written consent from the restaurant owner, display CCTV/AI signage, follow Qatar data-protection rules (the system stores counts and timestamps only, never video or faces).

## 6. Deployment

### A. On-premise at the restaurant (recommended)
RTSP lives on the restaurant LAN, so run the CV there. A mini PC (Intel NUC / i5, 16 GB) handles 1–2 cameras at 5–10 fps with `yolov8n`. For more cameras use a small NVIDIA GPU or Jetson Orin.
```bash
cp .env.example .env              # edit VIDEO_SOURCE
INSTALL_YOLO=1 docker compose up -d --build
# dashboard: http://<mini-pc-ip>:8000  (open it on the manager's phone/tablet on the same Wi-Fi)
```
No Docker: use `deploy/restaurant-ai.service` (systemd) with a Python venv.

### B. Hybrid (agency scale)
Edge box at each restaurant does detection and pushes events/alerts to a central VPS (Hetzner / DigitalOcean / AWS Bahrain-Middle East region) with PostgreSQL + a multi-tenant dashboard. Send only events, never video.

### C. Cloud GPU
Only if streams can be sent upstream (bandwidth + privacy cost). Same Docker image on a GPU instance with `YOLO_DEVICE=0`.

### Public access with HTTPS
Enable the `caddy` service in `docker-compose.yml`, set your domain and a password hash in `deploy/Caddyfile`. Open ports 80/443 only.

## 6b. v2 features (all built in)

| Feature | Where / how |
|---|---|
| **Login + roles** | `staff` (live ops, acknowledge alerts) < `manager` (+ analytics, reports, settings view) < `owner` (+ edit settings/zones, users, hub). Enable with `ADMIN_PASSWORD` (creates first owner). Users managed in **Settings → Users**. Passwords hashed with scrypt, signed 12 h tokens. |
| **Multi-camera** | `CAMERAS='{"cam1":"rtsp://…","cam2":"rtsp://…"}'`. Each table zone is assigned to a camera (Settings → Table zones). One worker thread per camera; camera switcher on the live feed. |
| **Camera-offline alert** | No frames for `CAMERA_OFFLINE_SEC` → critical alert (dashboard + phone push), tables of that camera turn grey, feed shows "CAMERA OFFLINE", auto-resolves on recovery. |
| **Person tracking** | Every person gets a stable `#id` (built-in IoU tracker). With YOLO you can switch to ultralytics ByteTrack: `USE_BYTETRACK=1`. |
| **Settings UI** | Thresholds, report schedule, restaurant name editable at runtime (stored in SQLite, no restart). |
| **Zone editor** | Settings → Table zones: draw/drag polygons on the live camera frame, set seats / section / camera, Save → applied instantly (persisted). |
| **Weekly report** | PDF + text. Auto-sent every `REPORT_WEEKDAY` at `REPORT_HOUR` (restaurant time) to the webhook (PDF as base64) and Telegram (PDF attached). Manual: Analytics → *Download PDF* / *Send report now*. |
| **Service performance** | Avg time to first waiter visit, table reset time, alert counts — by shift (lunch/evening/dinner), section and table. |
| **Multi-restaurant hub** | Central server with `HUB_ENABLED=1` → **All Venues** tab. Each restaurant sets `HUB_URL` + `HUB_KEY` and pushes counts/alerts every 5 s (never video). Add venues in the UI to get their key. |
| **Arabic + RTL** | EN/AR toggle in the header (remembered). Alert sentences are localised from structured data. *Have a native speaker review the Arabic copy before shipping to clients.* |
| **Staff mobile PWA** | `/#/staff` — big **I'm on it** buttons (records who acknowledged), live table grid, beep + vibrate + system notification on new alerts. Installable via *Add to Home Screen* (works on HTTPS or localhost). |
| **Staff alerts to phones** | `ALERT_WEBHOOK_URL` (n8n → WhatsApp/SMS/Slack) or `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`. |
| **Custom YOLO model** | `YOLO_MODEL=/path/best.pt`; a `staff`/`waiter` class replaces the uniform-colour heuristic. |

### Per-person staff metrics?
The service report is per shift / section / table. Per-*person* metrics would need staff identification (badge colour, face or ID recognition) — a privacy/legal decision to make with each restaurant, so it is intentionally not included.

### Hub quick start
```bash
# central server (.env)           HUB_ENABLED=1  ADMIN_PASSWORD=...
# owner: All Venues → Add venue   → copy HUB_URL / HUB_KEY
# each restaurant PC (.env)       HUB_URL=https://hub.example.com  HUB_KEY=vk_...
```

## 6c. v3 features

* **Clickable floor plan + manual override** - tap any table on *Live Host Floor*: see state, guests, timer, visits and the
  last events; staff can press **Mark cleaned** (NEEDS CLEANING), **Waiter visited** (OCCUPIED) or **Reserve / Remove
  reservation** (FREE). Reserved tables are excluded from the "next party" recommendation and free counts, and the
  reservation clears itself when guests sit. Every action is logged in `events` with the user's name.
* **Table-state detector** - with a custom model that has `table_clean` / `table_dirty` classes the camera itself flags a
  dirty table (FREE -> NEEDS CLEANING) and a wiped one (-> FREE) after 3 s of stable detection. Optional; see `training/README.md`.
* **Training toolkit** - `backend/scripts/extract_frames.py`, `auto_label.py`, `training/split_dataset.py`, `training/train.py`,
  `training/data.yaml` (classes: customer, staff, table_clean, table_dirty).
* **Windows** - double-click `run_simulator.bat` (needs Python 3.10+ and Node 18+).
* **Tested with real YOLOv8n** on a video file (CPU, ~13 fps) - persons detected, zones mapped, annotated feed OK.

## 6d. How the AI tells things apart (and how to tune it)

| Question | How it is decided | Tune with |
|---|---|---|
| **Person?** | YOLOv8 class `person` | `YOLO_CONF`, bigger model `yolov8s/m` |
| **Customer or staff?** | 1) uniform colour (HSV) smoothed by a majority vote over ~25 frames, 2) **roaming**: someone who stops at 2+ different tables is serving, not dining (sticky per track), 3) custom `staff` class if you trained one | Click a waiter's shirt: `GET /api/calibrate/uniform?x=..&y=..` returns `STAFF_HSV_LOW/HIGH` for `.env`; `STAFF_INFER=0` disables roaming |
| **Who is at which table / how many guests?** | person anchor point inside the table polygon (`ANCHOR=center/foot`), median-smoothed | Zone editor, `OCCUPY_CONFIRM_SEC`, `LEAVE_CONFIRM_SEC` |
| **Waiter visited?** | a staff track stays in/near the zone for `WAITER_VISIT_SEC` | `STAFF_MARGIN_PX` |
| **Table FREE?** | no customer in zone for `LEAVE_CONFIRM_SEC` and no dirty signal | - |
| **Table needs cleaning?** | guests left (always), or table-ware (cup/plate/fork/knife/bowl/glass/bottle >= `ITEM_MIN`) seen on an empty table, or appearance differs from the clean reference, or custom `table_dirty` class | `ITEM_MIN`, `TABLE_DIFF_THR` |
| **Table clean again?** | staff dwell for `CLEAN_CONFIRM_SEC`, or appearance matches the clean reference (needs reference), or custom `table_clean`, or manual button | table drawer -> **Set as clean reference** |

**Setup checklist on a real camera (15 min):** 1) draw zones; 2) click each table in the drawer while it is empty and clean ->
*Set as clean reference* (managers); 3) click a waiter's shirt in `/api/calibrate/uniform` and put the result in `.env`;
4) watch the drawer's *Camera vision* block (items count and difference score) on a dirty table and adjust `TABLE_DIFF_THR`.
Only trust the appearance/item cues after you have seen them on your own footage - they are heuristics, not a trained model.

## 6e. Model Studio - train the AI on your own CCTV (owner tab)

**Model Studio** tab: `1 Dataset` (upload MP4 from the DVR or capture from the live camera, auto-label, export zip) ->
`2 Label` (browser box editor, keys 1-4) -> `3 Train` (live progress / mAP chart, runs in the background) -> `4 Models`
(accuracy per class, **Activate** = hot-swap on all cameras, **Roll back to stock**, import a `.pt` trained on a GPU PC/Colab).
Models are versioned under `<data>/studio/models/<name>/`. Full explanation: [`docs/HOW_IT_WORKS.md`](docs/HOW_IT_WORKS.md).

**YOLO setup**: Docker build bakes PyTorch + ultralytics + `yolov8n/s` weights (`INSTALL_YOLO=1`, default in compose; image ~3 GB).
GPU: `TORCH_INDEX=https://download.pytorch.org/whl/cu121 docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build`.
The Studio header shows YOLO version, CPU/GPU and ms/frame per camera.

## 6f. Real restaurant video (no simulator)

Upload an MP4 in **Settings -> Video source** (or `./run_real.sh clip.mp4`, or the offline `backend/scripts/analyze_video.py`) and
the real YOLO AI runs on it. Real mode defaults: production thresholds (5 min / 2 min), no fake history, 960 px inference,
staff colour cue OFF until you click a waiter's shirt (Settings -> Staff uniform colour). Step-by-step: [`docs/REAL_VIDEO_TEST.md`](docs/REAL_VIDEO_TEST.md).

## 7. API

| Endpoint | Purpose |
|---|---|
| `GET /video_feed` | MJPEG annotated stream |
| `WS /ws` | live state JSON (2 Hz) |
| `GET/POST /api/source` · `POST /api/source/upload` | switch camera between simulator / video file / RTSP at runtime |
| `/api/studio/*` (owner): `overview`, `upload`, `capture`, `images`, `labels/{name}`, `autolabel`, `export`, `train`, `models`, `models/activate`, `models/import` | Model Studio |
| `POST /api/tables/{id}/reference` (manager) · `GET /api/calibrate/uniform` | clean-table reference photo, uniform colour calibration |
| `POST /api/tables/{id}/action` (`mark_clean`, `waiter_visit`, `reserve`, `unreserve`) · `GET /api/tables/{id}` | manual override + table history (staff) |
| `GET /api/state` · `/api/zones` · `/api/alerts` · `/api/events` | snapshots & logs |
| `POST /api/auth/login` · `GET /api/me` · `/api/config` | auth (Bearer token, or `?token=` for video/WS) |
| `PUT /api/zones` · `GET/PUT /api/settings` · `/api/users` | owner-level configuration |
| `GET /api/reports/weekly.pdf` · `.txt` · `POST /api/reports/send` | weekly report |
| `GET /api/snapshot.jpg?cam=&raw=1` | latest frame (raw = no overlay) |
| `POST /api/hub/ingest` · `GET/POST/DELETE /api/hub/venues` | multi-restaurant hub |
| `POST /api/alerts/{id}/ack` | acknowledge an alert |
| `GET /api/analytics/weekly` | weekly report |
| `GET /api/health` | health check |

## 8. Key settings (`.env`)

`VIDEO_SOURCE` · `WAIT_ALERT_SEC` · `CLEAN_ALERT_SEC` · `OCCUPY_CONFIRM_SEC` · `LEAVE_CONFIRM_SEC` · `ANCHOR` · `YOLO_MODEL` · `YOLO_CONF` · `YOLO_DEVICE` · `STAFF_HSV_LOW/HIGH` · `RESTAURANT_TZ` · `SEED_DEMO_DATA`
