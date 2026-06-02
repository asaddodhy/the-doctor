#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# The Doctor — Pipeline Test Script
# Tests the full pipeline: audio → bridge transcription → health extraction
#
# Usage:
#   ./scripts/test_pipeline.sh <audio_file>
#   ./scripts/test_pipeline.sh --no-extract <audio_file>
#
# Example:
#   ./scripts/test_pipeline.sh ~/Downloads/test_voice.ogg
#   ./scripts/test_pipeline.sh --no-extract ~/Downloads/test_voice.ogg
# ──────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ $# -lt 1 ]; then
    echo "Usage: $0 [--no-extract] <audio_file>"
    echo ""
    echo "Tests the full transcription + health extraction pipeline."
    echo ""
    echo "Options:"
    echo "  --no-extract    Skip health data extraction (transcription only)"
    echo ""
    echo "Example:"
    echo "  $0 ~/Downloads/test_voice.ogg"
    exit 1
fi

EXTRACT_FLAG=""
if [ "${1:-}" = "--no-extract" ]; then
    EXTRACT_FLAG="--no-extract"
    shift
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

# Run processor.py (handles transcription + optional health extraction)
echo "▸ Running processor.py..."
RECORDING_TIME=$(date "+%Y-%m-%d %H:%M:%S")
cd "$PROJECT_DIR"
uv run python3 processor.py "$AUDIO_FILE" --time "$RECORDING_TIME" $EXTRACT_FLAG 2>&1

echo ""
echo "  ✅ Pipeline test complete!"
echo ""
echo "  📄 Check data/transcripts.json for raw transcription"
echo "  📊 Check data/health_data.json for extracted health data"
echo "  🖥  Dashboard: http://localhost:9001 (run: uv run dashboard/app.py)"
echo ""
