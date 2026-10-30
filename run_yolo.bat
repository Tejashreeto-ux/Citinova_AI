@echo off
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
  echo Create the environment first: py -m venv venv
  pause
  exit /b 1
)
call venv\Scripts\activate.bat
python backend\vehicle_detection.py
pause
