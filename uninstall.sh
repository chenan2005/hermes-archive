#!/usr/bin/env bash
set -euo pipefail

# Session Archive System — uninstall script
# Usage: ./uninstall.sh [hermesHome]
#   hermesHome  - Hermes home directory (default: ~/.hermes)
#   Removes archive_tool.py from hermes-agent/tools/
#   If project dir != hermesHome/archive, removes hermesHome/archive/

HERMES_HOME="${1:-$HOME/.hermes}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Archive Uninstall ==="
echo "Hermes home: $HERMES_HOME"
echo "Project dir: $PROJECT_DIR"
echo ""

# 1. Remove archive_tool.py from hermes-agent/tools/
TOOL_PATH="$HERMES_HOME/hermes-agent/tools/archive_tool.py"
if [ -f "$TOOL_PATH" ]; then
    rm -f "$TOOL_PATH"
    echo "[1/2] Removed $TOOL_PATH"
else
    echo "[1/2] archive_tool.py not found, skipping"
fi

# 2. Remove ~/.hermes/archive/ if project dir is elsewhere
TARGET_ARCHIVE="$HERMES_HOME/archive"
if [ "$PROJECT_DIR" != "$TARGET_ARCHIVE" ]; then
    if [ -d "$TARGET_ARCHIVE" ]; then
        rm -rf "$TARGET_ARCHIVE"
        echo "[2/2] Removed $TARGET_ARCHIVE"
    else
        echo "[2/2] $TARGET_ARCHIVE not found, skipping"
    fi
else
    echo "[2/2] Project dir is inside Hermes home, skipping removal"
fi

echo ""
echo "=== Done ==="
