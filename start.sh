#!/usr/bin/env bash
# Quickstart script to launch SmartAPI Trading Engine & Web Dashboard
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "=========================================================="
echo "⚡ Starting Angel One SmartAPI Options Sniper Control Plane"
echo "=========================================================="

# Check if main.py is already running on port 5000
if ss -tulpn 2>/dev/null | grep -q ":5000 "; then
    echo "ℹ️  Backend engine is already running on http://localhost:5000"
else
    echo "🚀 Starting Python Engine & FastAPI server on port 5000..."
    nohup setsid ./venv/bin/python main.py > logs/runner.log 2>&1 &
    disown
    
    # Verify process started and is listening on port 5000 (Angel One API auth takes 5-12s)
    STARTED=0
    for i in {1..45}; do
        sleep 1
        if ss -tulpn 2>/dev/null | grep -q ":5000 "; then
            STARTED=1
            break
        fi
    done

    if [ $STARTED -eq 1 ]; then
        echo "✅ Engine boot verified on port 5000."
    else
        echo "❌ Engine failed to start or crashed on boot! Check logs/runner.log:"
        tail -n 15 logs/runner.log 2>/dev/null || true
        exit 1
    fi
fi

echo "✅ Web UI & API active at: http://localhost:5000"
echo "=========================================================="
