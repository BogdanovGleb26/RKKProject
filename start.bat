@echo off
chcp 65001 >nul
title RKK Inventory

REM Перейти в папку, где лежит этот .bat (не зависит от текущего каталога)
cd /d "%~dp0"

REM Проверить, что venv на месте
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv not found: %cd%\venv\Scripts\activate.bat
    pause
    exit /b 1
)

REM Активировать venv (для cmd — именно activate.bat, не .ps1)
call "venv\Scripts\activate.bat"
z
REM Проверить, что streamlit установлен
where streamlit >nul 2>nul
if errorlevel 1 (
    echo [ERROR] streamlit not found in venv. Run: pip install streamlit
    pause
    exit /b 1
)

echo Starting Streamlit on http://127.0.0.1:8501 ...
echo Press Ctrl+C to stop.
streamlit run main.py

REM Сюда попадём, когда Streamlit остановится (Ctrl+C или падение)
echo.
echo Streamlit stopped. Press any key to close.
pause >nul