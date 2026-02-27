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

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    if [ -f ".venv/Scripts/activate" ]; then
        source .venv/Scripts/activate
    elif [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi
fi

# Run python script in background using nohup
nohup python process_channel.py "$CHANNEL_URL" --max 0 > channel_process.log 2>&1 &

echo "✅ Process started in background! PID is $!"
echo "👉 You can now safely close this terminal."
echo "👉 To check logs later, run: tail -f channel_process.log"
