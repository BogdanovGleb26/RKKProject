@echo off
chcp 65001 >nul
title RKK Inventory
cd /d "%~dp0"

REM --- Убить старый Streamlit на 8501 (с ретраями) ---
echo [INFO] Checking port 8501...
set /a ATTEMPTS=0

:KillLoop
set "FOUND=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8501 ^| findstr LISTENING') do (
    echo [INFO] Found PID %%a on port 8501, killing...
    taskkill /F /T /PID %%a
    set "FOUND=1"
)

if "%FOUND%"=="1" (
    timeout /t 2 /nobreak >nul
    set /a ATTEMPTS+=1
    if %ATTEMPTS% LSS 3 goto KillLoop
)

REM --- Проверить, что порт свободен ---
netstat -ano | findstr :8501 | findstr LISTENING >nul
if not errorlevel 1 (
    echo [ERROR] Port 8501 is still in use. Close the app manually.
    netstat -ano | findstr :8501
    pause
    exit /b 1
)

echo [OK] Port 8501 is free.

REM Проверка venv
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv not found
    pause
    exit /b 1
)

call "venv\Scripts\activate.bat"

where streamlit >nul 2>nul
if errorlevel 1 (
    echo [ERROR] streamlit not found
    pause
    exit /b 1
)

echo [INFO] Starting Streamlit on http://localhost:8501
streamlit run main.py

echo.
echo Streamlit stopped.
pause >nul