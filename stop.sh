#!/usr/bin/env bash
# Quickstart script to stop SmartAPI Trading Engine & Web Dashboard
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "=========================================================="
echo "🛑 Stopping Angel One SmartAPI Options Sniper Engine..."
echo "=========================================================="

STOPPED=0

# 1. Stop systemd service if running to prevent auto-restart conflicts
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active --quiet smartapi_trader.service 2>/dev/null; then
        echo "Stopping systemd service smartapi_trader.service..."
        sudo systemctl stop smartapi_trader.service 2>/dev/null || true
        STOPPED=1
    fi
fi

# 2. Try graceful shutdown via process pattern matching
PIDS=$(pgrep -f "python.*main.py" || true)

if [ -n "$PIDS" ]; then
    echo "Found running engine process (PIDs: $PIDS). Sending graceful termination signal..."
    kill -15 $PIDS 2>/dev/null || true
    sleep 2
    # Force kill any stubborn/hanging threads if still lingering
    REMAINING=$(pgrep -f "python.*main.py" || true)
    if [ -n "$REMAINING" ]; then
        echo "Force terminating lingering processes: $REMAINING"
        kill -9 $REMAINING 2>/dev/null || true
    fi
    STOPPED=1
fi

# 3. Check if port 5000 is still held, and terminate if lingering
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
