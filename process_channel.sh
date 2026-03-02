#!/bin/bash

export PYTHONIOENCODING=utf-8

if [ -z "$1" ]; then
    echo "❌ Usage: $0 <YOUTUBE_CHANNEL_URL>"
    echo "Example: $0 \"https://www.youtube.com/@FEBCChristianMedia\""
    exit 1
fi

CHANNEL_URL="$1"

echo "==================================================="
echo "    Nong Unjai - Background Channel Processor"
echo "==================================================="
echo ""
echo "⏳ Starting background processing for: $CHANNEL_URL"

# Navigate to script directory
cd "$(dirname "$0")"

# Find the Python binary inside the virtual environment directly
PYTHON_CMD=""
for VENV_DIR in venv .venv; do
    if [ -f "$VENV_DIR/bin/python3" ]; then
        PYTHON_CMD="$VENV_DIR/bin/python3"
        break
    elif [ -f "$VENV_DIR/bin/python" ]; then
        PYTHON_CMD="$VENV_DIR/bin/python"
        break
    elif [ -f "$VENV_DIR/Scripts/python.exe" ]; then
        PYTHON_CMD="$VENV_DIR/Scripts/python.exe"
        break
    fi
done

# Fallback to system python if no venv found
if [ -z "$PYTHON_CMD" ]; then
    PYTHON_CMD="python3"
fi

echo "🐍 Using Python: $PYTHON_CMD"

# Run python script in background using nohup
nohup $PYTHON_CMD process_channel.py "$CHANNEL_URL" --max 0 > channel_process.log 2>&1 &

echo "✅ Process started in background! PID is $!"
echo "👉 You can now safely close this terminal."
echo "👉 To check logs later, run: tail -f channel_process.log"
