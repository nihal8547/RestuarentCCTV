# ---------- stage 1: build the React dashboard ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- stage 2: Python backend (serves API + built dashboard) ----------
FROM python:3.12-slim
# INSTALL_YOLO=1 adds PyTorch + ultralytics (needed for real CCTV / video files and the Model Studio).
# TORCH_INDEX picks the PyTorch wheels: CPU (default, ~200 MB) or GPU e.g. https://download.pytorch.org/whl/cu121
ARG INSTALL_YOLO=0
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY backend/requirements.txt backend/requirements-yolo.txt ./
RUN pip install -r requirements.txt && \
    if [ "$INSTALL_YOLO" = "1" ]; then \
      pip install torch torchvision --index-url "$TORCH_INDEX" && pip install -r requirements-yolo.txt \
      && python -c "from ultralytics import YOLO; YOLO('yolov8n.pt'); YOLO('yolov8s.pt')"; \
    fi
COPY backend/ ./
# weights downloaded above live in the cwd (/app/backend) -> available offline
COPY --from=web /web/dist /app/frontend/dist
ENV FRONTEND_DIST=/app/frontend/dist DB_PATH=/data/restaurant.db YOLO_CONFIG_DIR=/data/ultralytics
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
