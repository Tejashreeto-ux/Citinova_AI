@echo off
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
  echo Create the environment first: py -m venv venv
  pause
  exit /b 1
)
call venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python backend\app.py
pause
