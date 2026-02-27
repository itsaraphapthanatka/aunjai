#!/bin/bash

echo "Starting API Server in background..."

# Navigate to the directory where the script is located
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    # Use Scripts/activate for Windows (Git Bash), bin/activate for Linux/Mac
    if [ -f ".venv/Scripts/activate" ]; then
        source .venv/Scripts/activate
    elif [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi
fi

# Run uvicorn in background using nohup
nohup uvicorn api_server:app --host 127.0.0.1 --port 8000 > api_server.log 2>&1 &

echo "Server is running in background! (PID: $!)"
echo "Logs will be saved to api_server.log"
