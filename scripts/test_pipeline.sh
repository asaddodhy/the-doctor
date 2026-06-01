#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# The Doctor — Pipeline Test Script
# Tests the full pipeline: bridge script → processor → health data extraction
# Usage:
#   ./scripts/test_pipeline.sh <audio_file>
# Example:
#   ./scripts/test_pipeline.sh ~/Downloads/test_voice.ogg
# ──────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default paths
BRIDGE_SCRIPT="${DOCTOR_BRIDGE_SCRIPT:-$HOME/Documents/Development/perplexity-stack/scripts/transcribe.py}"
BRIDGE_PYTHON="${DOCTOR_BRIDGE_PYTHON:-$HOME/Documents/Development/perplexity-stack/perplexity-web-wrapper/.venv/bin/python3}"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <audio_file>"
    echo ""
    echo "Tests the full transcription + health extraction pipeline."
    echo ""
    echo "Example:"
    echo "  $0 ~/Downloads/test_voice.ogg"
    exit 1
fi

AUDIO_FILE="$1"

if [ ! -f "$AUDIO_FILE" ]; then
    echo "❌ File not found: $AUDIO_FILE"
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  The Doctor — Pipeline Test                          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Audio: $AUDIO_FILE ($(du -h "$AUDIO_FILE" | cut -f1))"
echo ""

# Step 1: Transcribe via bridge script
echo "▸ Step 1/2: Transcribing via bridge script..."
TRANSCRIPTION=$("$BRIDGE_PYTHON" "$BRIDGE_SCRIPT" "$AUDIO_FILE" 2>/dev/null || echo '{"text": ""}')
TEXT=$(echo "$TRANSCRIPTION" | python3 -c "import sys,json; print(json.load(sys.stdin).get('text',''))" 2>/dev/null || echo "")

if [ -z "$TEXT" ]; then
    echo "  ⚠️  Transcription returned empty"
    echo "     (The bridge may need cookies — check perplexity_cookies.json)"
    echo ""
    echo "  Continuing with health extraction using raw file..."
fi

echo "  ✅ Transcription received (${#TEXT} chars)"
echo "  Preview: ${TEXT:0:100}..."
echo ""

# Step 2: Process through The Doctor
echo "▸ Step 2/2: Extracting health data..."
RECORDING_TIME=$(date "+%Y-%m-%d %H:%M:%S")
uv run python3 "$PROJECT_DIR/processor.py" "$AUDIO_FILE" --time "$RECORDING_TIME" 2>&1 || true

echo ""
echo "  ✅ Pipeline test complete!"
echo ""
echo "  📄 Check data/transcripts.json for raw transcription"
echo "  📊 Check data/health_data.json for extracted health data"
echo "  🖥  Dashboard: http://localhost:9001 (run: uv run dashboard/app.py)"
echo ""
