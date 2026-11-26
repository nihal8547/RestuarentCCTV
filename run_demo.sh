#!/usr/bin/env bash
# One command demo: builds the dashboard, starts the backend in simulator mode.
set -e
cd "$(dirname "$0")"
python3 -m venv backend/venv 2>/dev/null || true
source backend/venv/bin/activate
pip install -q -r backend/requirements.txt
( cd frontend && npm install --no-audit --no-fund && npm run build )
cd backend
echo ">>> Open http://localhost:8000"
uvicorn app.main:app --host 0.0.0.0 --port 8000
