# PyInstaller spec for Smart BI desktop app
#
# Build:
#   pyinstaller packaging/pyinstaller.spec
#
# Output:
#   macOS:   dist/SmartBI.app      (onedir bundle with Frameworks/ + Resources/)
#   Windows: dist/SmartBI.exe      (single-file executable)

import sys
from pathlib import Path

block_cipher = None

# Project root (parent of packaging/)
PROJECT_ROOT = Path(SPECPATH).resolve().parent
STATIC_DIR = PROJECT_ROOT / "backend" / "static"

# Optional: when frontend hasn't been built, skip static dir warning
if not STATIC_DIR.exists():
    print(f"[WARNING] {STATIC_DIR} does not exist. Build the frontend first:")
    print("          cd frontend && npm install && npm run build")
    sys.exit(1)

a = Analysis(
    [str(PROJECT_ROOT / "backend" / "app.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # Frontend build artefacts
        (str(STATIC_DIR), "backend/static"),
        # Prompts
        (str(PROJECT_ROOT / "backend" / "agent" / "prompts"), "backend/agent/prompts"),
        # Config
        (str(PROJECT_ROOT / "config.yaml"), "."),
    ],
    hiddenimports=[
        # SQLAlchemy dialects
        "sqlalchemy.dialects.sqlite",
        "sqlalchemy.dialects.mysql",
        "sqlalchemy.dialects.mysql.pymysql",
        "sqlalchemy.dialects.postgresql",
        "sqlalchemy.dialects.postgresql.psycopg2",
        # DB drivers
        "pymysql",
        "psycopg2",
        "aiosqlite",
        "duckdb",
        # LLM clients
        "openai",
        "anthropic",
        "httpx",
        "tiktoken",
        # RAG
        "chromadb",
        "chromadb.segment.impl",
        # SQL tooling
        "sqlglot",
        "sqlfluff",
        # Plotly + Pandas
        "plotly",
        "pandas",
        "numpy",
        "kaleido",
        # Web shell
        "webview",
        "webview.platforms.winforms",
        "webview.platforms.cocoa",
        "webview.platforms.gtk",
        # Utils
        "pydantic",
        "pydantic_settings",
        "yaml",
        "dotenv",
        "loguru",
        "rich",
        "click",
        "tenacity",
        "platformdirs",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "pytest",
        "tests",
        "sphinx",
        "PIL.ImageQt",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

ICON_ICNS = str(PROJECT_ROOT / "packaging" / "icons" / "icon.icns") if (PROJECT_ROOT / "packaging" / "icons" / "icon.icns").exists() else None

# Windows: one-file EXE. Single .exe the user can run / distribute.
if sys.platform == "win32":
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="SmartBI",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,                # disabled by default; enable after testing
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,            # GUI app, no console window
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(PROJECT_ROOT / "packaging" / "icons" / "icon.ico") if (PROJECT_ROOT / "packaging" / "icons" / "icon.ico").exists() else None,
    )

# macOS: onedir (.app with Frameworks/ + Resources/ folders). PyInstaller's
# recommended pattern for macOS — onefile mode conflicts with macOS code
# signing and will become an error in PyInstaller 7.
if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],                      # binaries go to COLLECT (onedir)
        exclude_binaries=True,
        name="SmartBI",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,            # GUI app, no console window
        disable_windowed_traceback=False,
        icon=ICON_ICNS,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="SmartBI",
    )
    app = BUNDLE(
        coll,
        name="SmartBI.app",
        icon=ICON_ICNS,
        bundle_identifier="com.smartbi.app",
        info_plist={
            "CFBundleName": "Smart BI",
            "CFBundleDisplayName": "Smart BI",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "LSMinimumSystemVersion": "10.15",
            "NSHighResolutionCapable": True,
        },
    )
