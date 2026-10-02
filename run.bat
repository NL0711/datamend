@echo off
title SkyGuard AI — Full System Launcher
color 0A

echo ============================================================
echo    SKYGUARD AI — Intelligent Anomaly Detection Platform
echo    Starting Full System (Backend + Frontend)
echo ============================================================
echo.

:: Get the directory where this script lives
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

:: ──────────────────────────────────────────────
:: 1. Check Python
:: ──────────────────────────────────────────────
echo [1/5] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo        Found: %%i
echo.

:: ──────────────────────────────────────────────
:: 2. Check Node.js
:: ──────────────────────────────────────────────
echo [2/5] Checking Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH.
    echo         Install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version 2^>^&1') do echo        Found: Node.js %%i
echo.

:: ──────────────────────────────────────────────
:: 3. Install Python dependencies (if needed)
:: ──────────────────────────────────────────────
echo [3/5] Checking Python dependencies...
python -c "import fastapi; import uvicorn; import torch; import sklearn" >nul 2>&1
if %errorlevel% neq 0 (
    echo        Installing Python dependencies...
    pip install -r requirements.txt --quiet
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install Python dependencies.
        pause
        exit /b 1
    )
    echo        Dependencies installed successfully.
) else (
    echo        All Python dependencies are already installed.
)
echo.

:: ──────────────────────────────────────────────
:: 4. Install Frontend dependencies (if needed)
:: ──────────────────────────────────────────────
echo [4/5] Checking frontend dependencies...
if not exist "frontend\node_modules" (
    echo        Installing frontend dependencies...
    cd frontend
    npm install --silent
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install frontend dependencies.
        pause
        exit /b 1
    )
    cd ..
    echo        Frontend dependencies installed successfully.
) else (
    echo        Frontend dependencies are already installed.
)
echo.

:: ──────────────────────────────────────────────
:: 5. Launch Backend + Frontend
:: ──────────────────────────────────────────────
echo [5/5] Launching SkyGuard AI...
echo.
echo        Backend:  http://localhost:8899
echo        API Docs: http://localhost:8899/docs
echo        Frontend: http://localhost:5199
echo.
echo ============================================================
echo    Press Ctrl+C in either window to stop that service.
echo    Close this window to stop BOTH services.
echo ============================================================
echo.

:: Start backend in a new window
start "SkyGuard Backend (port 8899)" cmd /k "cd /d "%PROJECT_DIR%" && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8899 --reload"

:: Small delay to let backend start first
timeout /t 3 /nobreak >nul

:: Start frontend in a new window
start "SkyGuard Frontend (port 5199)" cmd /k "cd /d "%PROJECT_DIR%\frontend" && npm run dev"

:: Wait a moment then open browser
timeout /t 5 /nobreak >nul
echo Opening dashboard in browser...
start http://localhost:5199

echo.
echo SkyGuard AI is running!
echo.
echo   Backend:  http://localhost:8899      (API Docs: http://localhost:8899/docs)
echo   Frontend: http://localhost:5199
echo.
echo To stop: close the Backend and Frontend command windows.
echo.
pause
