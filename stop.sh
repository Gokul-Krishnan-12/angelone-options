#!/usr/bin/env bash
# Quickstart script to stop SmartAPI Trading Engine & Web Dashboard
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "=========================================================="
echo "🛑 Stopping Angel One SmartAPI Options Sniper Engine..."
echo "=========================================================="

STOPPED=0

# 1. Try graceful shutdown via process pattern matching
PIDS=$(pgrep -f "python main.py" || true)

if [ -n "$PIDS" ]; then
    echo "Found running engine process (PIDs: $PIDS). Sending graceful termination signal..."
    kill -15 $PIDS 2>/dev/null || true
    sleep 2
    STOPPED=1
fi

# 2. Check if port 5000 is still held, and terminate if lingering
if ss -tulpn 2>/dev/null | grep -q ":5000 "; then
    echo "Releasing port 5000..."
    fuser -k 5000/tcp 2>/dev/null || true
    sleep 1
    STOPPED=1
fi

if [ $STOPPED -eq 1 ]; then
    echo "✅ SmartAPI Trading Engine stopped successfully. Port 5000 is free."
else
    echo "ℹ️  No running SmartAPI engine found on port 5000."
fi
echo "=========================================================="
