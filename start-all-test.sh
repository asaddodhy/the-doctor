#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# The Doctor — Start All Services (TEST MODE)
#
# Launches dashboard, WhatsApp listener, and Telegram listener in test mode.
# Uses .env.test for configuration and data/test_*.json for storage.
# Dashboard runs on port 9002 so it can run alongside production.
#
# Usage:
#   ./start-all-test.sh          # Start all services in test mode
#   ./start-all-test.sh --logs   # Tail logs after starting
#   ./start-all-test.sh stop     # Stop all services
#   ./start-all-test.sh status   # Check which services are running
# ──────────────────────────────────────────────────────────────────────────

export DOCTOR_ENV=test
export DOCTOR_DASHBOARD_PORT=9002

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🧪 TEST MODE"
echo "   Config: .env.test"
echo "   Dashboard: http://localhost:9002"
echo "   Data: data/test_*.json"
echo ""

exec "$SCRIPT_DIR/start-all.sh" "$@"
