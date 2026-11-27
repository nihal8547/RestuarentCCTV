@echo off
REM One-click run for Windows: builds the dashboard and starts the backend with the realistic restaurant simulator.
REM Requires Python 3.10+ and Node 18+ on PATH.
setlocal
cd /d "%~dp0"

if not exist backend\venv (
  python -m venv backend\venv || (echo Python not found & exit /b 1)
)
call backend\venv\Scripts\activate.bat
python -m pip install -q -r backend\requirements.txt || exit /b 1

if not exist frontend\dist (
  pushd frontend
  call npm install --no-audit --no-fund || exit /b 1
  call npm run build || exit /b 1
  popd
)

cd backend
echo.
echo ^>^>^> Open http://localhost:8000   (login password is printed below on first run)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
endlocal
