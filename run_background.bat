@echo off
echo Starting API Server in background...

:: Navigate to script directory
cd /d "%~dp0"

:: Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

:: Run uvicorn in background without showing the window
start "" /b pythonw -m uvicorn api_server:app --host 127.0.0.1 --port 8000 > api_server.log 2>&1

echo Server is running in background!
echo Logs will be saved to api_server.log
