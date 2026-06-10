# Build Smart BI for Windows
#
# Prerequisites:
#   - Python 3.10+ (with PATH set)
#   - Node.js 18+ (with PATH set)
#   - Run from PowerShell
#
# Output: dist\SmartBI.exe
$ErrorActionPreference = "Stop"

$ROOT = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ROOT

Write-Host "==> [1/4] Installing Python deps"
pip install -e ".[dev]"

Write-Host "==> [2/4] Building frontend"
Set-Location (Join-Path $ROOT "frontend")
if (-not (Test-Path "node_modules")) {
    npm install
}
npm run build
Set-Location $ROOT

Write-Host "==> [3/4] Verifying frontend"
if (-not (Test-Path "backend/static/index.html")) {
    Write-Error "backend/static/index.html missing. Frontend build failed?"
    exit 1
}

Write-Host "==> [4/4] Running PyInstaller"
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
pyinstaller packaging/pyinstaller.spec --noconfirm

Write-Host ""
Write-Host "Done. Executable at: $ROOT\dist\SmartBI.exe"
Write-Host "For distribution, sign with signtool:"
Write-Host "  signtool sign /fd SHA256 /a dist\SmartBI.exe"
