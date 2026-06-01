#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# The Doctor — Install launchd services for auto-start on boot
#
# Usage:
#   ./launchd/install.sh          # Install and load all services
#   ./launchd/install.sh unload   # Unload and remove
#   ./launchd/install.sh status   # Check if loaded
# ──────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_SRC="$SCRIPT_DIR/com.thedoctor.start-all.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.thedoctor.start-all.plist"

# Fix PATH in plist to match current shell
CURRENT_PATH=$(echo "$PATH" | sed 's/\//\\\//g')
sed -i '' "s/__PATH_REPLACE__/$CURRENT_PATH/g" "$PLIST_SRC"

case "${1:-install}" in
    install)
        echo "📦 Installing launchd service..."

        # Copy plist to user's LaunchAgents
        mkdir -p "$HOME/Library/LaunchAgents"
        cp "$PLIST_SRC" "$PLIST_DST"
        echo "  ✅ Plist copied to $PLIST_DST"

        # Load the service
        launchctl load "$PLIST_DST"
        echo "  ✅ Service loaded (will auto-start on boot)"

        echo ""
        echo "  To verify: launchctl list | grep thedoctor"
        echo "  To stop now: launchctl unload $PLIST_DST"
        echo "  To remove: $0 unload"
        ;;

    unload)
        echo "🗑️  Removing launchd service..."
        if [ -f "$PLIST_DST" ]; then
            launchctl unload "$PLIST_DST" 2>/dev/null || true
            rm -f "$PLIST_DST"
            echo "  ✅ Service unloaded and removed"
        else
            echo "  ⚠️  No plist found at $PLIST_DST"
        fi
        ;;

    status)
        echo "📊 Service Status:"
        echo ""
        if launchctl list | grep -q "thedoctor"; then
            launchctl list | grep thedoctor
        else
            echo "  ⚪ Not loaded"
        fi
        echo ""
        echo "  Check individual processes:"
        ./start-all.sh status
        ;;
esac
