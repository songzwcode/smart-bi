#!/usr/bin/env bash
# Launch the locally-built SmartBI.app, stripping any macOS Gatekeeper
# quarantine / xattr flags that may have been added when the app was
# copied or downloaded.
#
# Background: a pyinstaller-bundled .app produced without a paid Apple
# Developer ID is signed ad-hoc only. spctl / Gatekeeper will reject it
# on double-click ("from an unidentified developer" or "app is damaged").
# Running this script once clears those attributes so the .app can launch
# normally via Finder or `open`.
#
# Usage:
#   ./scripts/launch-macos.sh                # launches ./dist/SmartBI.app
#   ./scripts/launch-macos.sh /path/to/app   # launches a different .app
set -euo pipefail

APP="${1:-$(dirname "$0")/../dist/SmartBI.app}"

if [ ! -d "$APP" ]; then
  echo "ERROR: $APP not found. Run packaging/build_macos.sh first." >&2
  exit 1
fi

echo "==> Stripping quarantine / xattr from $APP"
xattr -cr "$APP"

echo "==> Re-signing with ad-hoc identity (deep, replaces nested sigs)"
codesign --force --deep --sign - "$APP"

echo "==> Verifying signature"
codesign -dv "$APP" 2>&1 | head -3

echo "==> Launching"
open "$APP"
echo "    Tip: if the window doesn't appear, check the Dock for the Smart BI icon."
