#!/usr/bin/env bash
# Run the dashboard on a REAL video file or RTSP stream (YOLO, no simulator, no fake data).
#   ./run_real.sh samples/my_restaurant.mp4         # test with a video (loops)
#   ./run_real.sh "rtsp://user:pass@192.168.1.64:554/Streaming/Channels/102"
# Optional:  WAIT_ALERT_SEC=30 CLEAN_ALERT_SEC=20 ./run_real.sh clip.mp4   # shorter alerts for short clips (default 5 min / 2 min)
set -e
cd "$(dirname "$0")"
SRC="${1:?usage: ./run_real.sh <video-file-or-rtsp-url>}"
python3 -m venv backend/venv 2>/dev/null || true
source backend/venv/bin/activate
pip install -q -r backend/requirements.txt
python -c "import ultralytics" 2>/dev/null || {
  echo ">>> installing PyTorch (CPU) + ultralytics (first time, ~1 GB)"
  pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
  pip install -q -r backend/requirements-yolo.txt
}
[ -d frontend/dist ] || ( cd frontend && npm install --no-audit --no-fund && npm run build )
cd backend
export VIDEO_SOURCE="$SRC"
echo ">>> Open http://localhost:8000  ->  Settings: draw table zones, click a waiter's shirt (uniform colour)"
uvicorn app.main:app --host 0.0.0.0 --port 8000
