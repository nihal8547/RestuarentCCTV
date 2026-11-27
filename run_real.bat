@echo off
REM Run on a REAL video file or RTSP URL:  run_real.bat samples\my_restaurant.mp4
setlocal
cd /d "%~dp0"
if "%~1"=="" (echo usage: run_real.bat ^<video-file-or-rtsp-url^> & exit /b 1)
if not exist backend\venv python -m venv backend\venv
call backend\venv\Scripts\activate.bat
python -m pip install -q -r backend\requirements.txt || exit /b 1
python -c "import ultralytics" 2>nul || (
  echo Installing PyTorch CPU + ultralytics, first time only...
  python -m pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
  python -m pip install -q -r backend\requirements-yolo.txt
)
if not exist frontend\dist (pushd frontend & call npm install --no-audit --no-fund & call npm run build & popd)
cd backend
set VIDEO_SOURCE=%~1
echo Open http://localhost:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
endlocal
