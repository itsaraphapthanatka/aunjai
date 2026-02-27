#!/bin/bash

export PYTHONIOENCODING=utf-8

echo "==================================================="
echo "    Nong Unjai - Stop Background Process"
echo "==================================================="
echo ""

# Find all processes running process_channel.py
PIDS=$(pgrep -f "process_channel.py")

if [ -z "$PIDS" ]; then
    echo "✅ No background channel processing found."
    exit 0
fi

echo "⚠️ Found running process(es): $PIDS"
echo "Stopping them now..."

# Kill the processes
kill -9 $PIDS

echo "✅ All background channel processes have been stopped!"
