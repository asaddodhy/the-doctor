#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# The Doctor — Start All Services
# Launches the dashboard, WhatsApp listener, and Telegram listener.
#
# Usage:
#   ./start-all.sh          # Start all services
#   ./start-all.sh --logs   # Tail logs after starting
#   ./start-all.sh stop     # Stop all services
#   ./start-all.sh status   # Check which services are running
# ──────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

SERVICES=(
    "dashboard:uv run python3 dashboard/app.py:logs/dashboard.log:9001"
    "whatsapp:node whatsapp/listener.mjs:logs/whatsapp.log:whatsapp"
    "telegram:uv run python3 telegram_listener.py:logs/telegram.log:telegram"
)

stop_all() {
    echo "🛑 Stopping all services..."
    for entry in "${SERVICES[@]}"; do
        name="${entry%%:*}"
        pid_file="$LOG_DIR/${name}.pid"
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file" 2>/dev/null)
            if kill "$pid" 2>/dev/null; then
                echo "  ✅ $name stopped"
            else
                echo "  ⚠️  $name not running"
            fi
            rm -f "$pid_file"
        fi
    done
    # Also kill any leftover Chrome for Testing processes
    pkill -f "Google Chrome for Testing" 2>/dev/null || true
    echo "  ✅ All services stopped"
}

status_all() {
    echo "📊 Service Status:"
    echo ""
    for entry in "${SERVICES[@]}"; do
        name="${entry%%:*}"
        pid_file="$LOG_DIR/${name}.pid"
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file" 2>/dev/null)
            if kill -0 "$pid" 2>/dev/null; then
                echo "  ✅ $name running (PID $pid)"
            else
                echo "  ❌ $name pid file exists but process dead"
                rm -f "$pid_file"
            fi
        else
            echo "  ⚪ $name not running"
        fi
    done
}

start_all() {
    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║  The Doctor — Starting All Services                  ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""

    cd "$SCRIPT_DIR"

    for entry in "${SERVICES[@]}"; do
        IFS=: read -r name cmd log_file port <<< "$entry"
        pid_file="$LOG_DIR/${name}.pid"

        # Check if already running
        if [ -f "$pid_file" ]; then
            old_pid=$(cat "$pid_file" 2>/dev/null)
            if kill -0 "$old_pid" 2>/dev/null; then
                echo "  ⚠️  $name already running (PID $old_pid)"
                continue
            fi
            rm -f "$pid_file"
        fi

        echo "  🚀 Starting $name..."
        echo "     Log: $log_file"

        # Start in background with nohup
        nohup $cmd > "$log_file" 2>&1 &
        pid=$!
        echo "$pid" > "$pid_file"
        echo "     PID: $pid"

        # Brief pause between starts
        sleep 2
    done

    echo ""
    echo "  ✅ All services started!"
    echo ""
    echo "  📊 Dashboard: http://localhost:9001"
    echo "  📋 Logs: $LOG_DIR/"
    echo ""
    echo "  To view logs:"
    echo "    tail -f $LOG_DIR/*.log"
    echo ""
    echo "  To stop:"
    echo "    $0 stop"
}

# ── Main ────────────────────────────────────────────────────────────────

case "${1:-start}" in
    start)
        start_all
        if [ "${2:-}" = "--logs" ]; then
            echo "Tailing logs... (Ctrl+C to stop)"
            tail -f "$LOG_DIR"/*.log
        fi
        ;;
    stop)
        stop_all
        ;;
    status)
        status_all
        ;;
    restart)
        stop_all
        sleep 2
        start_all
        ;;
    *)
        echo "Usage: $0 [start|stop|status|restart] [--logs]"
        exit 1
        ;;
esac
