#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# Start the Perplexity Web API server (used by both OpenCode bot and The Doctor)
# Only starts if one isn't already running on the target port.
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

PERPLEXITY_API_DIR="$HOME/Documents/Development/perplexity-stack/perplexity-web-wrapper"
PERPLEXITY_API_PORT=8001
LOG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/logs"
mkdir -p "$LOG_DIR"

# Check if something is already listening on the target port
if lsof -iTCP:"$PERPLEXITY_API_PORT" -sTCP:LISTEN -P -n 2>/dev/null | grep -q .; then
    echo "Perplexity API server already running on port $PERPLEXITY_API_PORT — skipping start."
    exit 0
fi

cd "$PERPLEXITY_API_DIR"

nohup .venv/bin/uvicorn api.main:app \
    --host 127.0.0.1 \
    --port "$PERPLEXITY_API_PORT" \
    --log-level warning \
    > "$LOG_DIR/perplexity-api.log" 2>&1 &

PID=$!
echo "$PID"
echo "Perplexity API server started on port $PERPLEXITY_API_PORT (PID $PID)"
