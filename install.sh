#!/usr/bin/env bash
set -euo pipefail

# Session Archive System — install / deploy script
# Usage: ./install.sh [targetDir]
#   targetDir  - Hermes home directory (default: ~/.hermes)
#   Copies archive_tool.py to hermes-agent/tools/
#   Syncs project to targetDir/archive (if not already there)

TARGET_DIR="${1:-$HOME/.hermes}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Archive Install ==="
echo "Target:  $TARGET_DIR"
echo "Project: $PROJECT_DIR"
echo ""

# 1. Install archive_tool.py to hermes-agent/tools/
TOOLS_DIR="$TARGET_DIR/hermes-agent/tools"
mkdir -p "$TOOLS_DIR"
cp "$PROJECT_DIR/src/archive_tool.py" "$TOOLS_DIR/archive_tool.py"
echo "[1/2] archive_tool.py → $TOOLS_DIR/archive_tool.py"

# 2. Sync project to targetDir/archive (if not already there)
TARGET_ARCHIVE="$TARGET_DIR/archive"
if [ "$PROJECT_DIR" != "$TARGET_ARCHIVE" ]; then
    mkdir -p "$TARGET_ARCHIVE"
    rsync -a --delete \
        --exclude='.git/' \
        --exclude='__pycache__/' \
        --exclude='data/groups/' \
        "$PROJECT_DIR/" "$TARGET_ARCHIVE/"
    echo "[2/2] Project synced → $TARGET_ARCHIVE"
else
    echo "[2/2] Already at target, skipping copy"
fi

echo ""
echo "=== Done ==="
