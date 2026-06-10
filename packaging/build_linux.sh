#!/usr/bin/env bash
# Build Smart BI for Linux
#
# Prerequisites:
#   - Python 3.10+
#   - Node.js 18+
#   - webkit2gtk-4.0 / 4.1 (for PyWebView)
#       Ubuntu/Debian: sudo apt install libwebkit2gtk-4.0-dev
#
# Output: dist/SmartBI (single-file executable)
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "==> [1/5] Checking system deps"
if ! pkg-config --exists webkit2gtk-4.0 webkit2gtk-4.1 2>/dev/null; then
    if ! pkg-config --exists webkit2gtk-4.1; then
        echo "WARNING: webkit2gtk not detected. PyWebView may not work."
        echo "Install with: sudo apt install libwebkit2gtk-4.1-dev"
    fi
fi

echo "==> [2/5] Installing Python deps"
pip install -e ".[dev]"

echo "==> [3/5] Building frontend"
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run build
cd "$ROOT"

echo "==> [4/5] Verifying frontend"
if [ ! -f "backend/static/index.html" ]; then
    echo "ERROR: backend/static/index.html missing." >&2
    exit 1
fi

echo "==> [5/5] Running PyInstaller"
rm -rf dist build
pyinstaller packaging/pyinstaller.spec --noconfirm

echo ""
echo "✓ Done. Executable at: $ROOT/dist/SmartBI"
echo ""
echo "Optional: build an AppImage"
echo "  wget https://github.com/AppImageCommunity/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
echo "  mkdir -p SmartBI.AppDir/usr/bin"
echo "  cp dist/SmartBI SmartBI.AppDir/usr/bin/"
echo "  cp packaging/icons/icon.png SmartBI.AppDir/"
echo "  ./appimagetool-x86_64.AppImage SmartBI.AppDir SmartBI-x86_64.AppImage"
