#!/usr/bin/env bash
# Build Smart BI for macOS
#
# Prerequisites:
#   - Python 3.10+ with pip
#   - Node.js 18+ with npm
#   - Frontend built: cd frontend && npm install && npm run build
#
# Output: dist/SmartBI.app
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "==> [1/4] Installing Python deps"
pip install -e ".[dev]"

echo "==> [2/4] Building frontend"
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run build
cd "$ROOT"

echo "==> [3/4] Verifying frontend artefacts"
if [ ! -f "backend/static/index.html" ]; then
    echo "ERROR: backend/static/index.html missing. Frontend build failed?" >&2
    exit 1
fi

echo "==> [4/4] Running PyInstaller"
rm -rf dist build
pyinstaller packaging/pyinstaller.spec --noconfirm

echo ""
echo "✓ Done. App at: $ROOT/dist/SmartBI.app"
echo "  To run: open dist/SmartBI.app"
echo ""
echo "  For distribution, consider codesigning:"
echo "    codesign --deep --force --sign \"Developer ID Application: Your Name\" dist/SmartBI.app"
echo "    xcrun notarytool submit dist/SmartBI.zip --keychain-profile <profile> --wait"
