#!/usr/bin/env bash
# Download NotoSansSC CJK fonts for PDF export.
# Run from any directory — fonts are saved next to this script.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_URL="https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/SubsetOTF/SC"

echo "Downloading NotoSansSC fonts..."
curl -sL -o "$SCRIPT_DIR/NotoSansSC-Regular.ttf" "$BASE_URL/NotoSansSC-Regular.otf"
curl -sL -o "$SCRIPT_DIR/NotoSansSC-Bold.ttf" "$BASE_URL/NotoSansSC-Bold.otf"
echo "Done. Fonts saved to $SCRIPT_DIR"
ls -lh "$SCRIPT_DIR"/*.ttf
