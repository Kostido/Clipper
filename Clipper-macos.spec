# -*- mode: python ; coding: utf-8 -*-
"""Сборка Clipper.app для macOS: pyinstaller Clipper-macos.spec"""
from pathlib import Path

project = Path(SPECPATH)

# Бинарники-помощники лежат в bin/ и попадают внутрь бандла.
binaries = []
for name in ("ffmpeg", "ffprobe", "qjs", "rustypipe-botguard"):
    candidate = project / "bin" / name
    if candidate.exists():
        binaries.append((str(candidate), "bin"))

datas = []
# Плагин генерации PO-токенов: yt-dlp ищет пакет yt_dlp_plugins в путях sys.path.
try:
    import yt_dlp_plugins.extractor.yt_dlp_get_pot_rustypipe as _pot_plugin
    datas.append((_pot_plugin.__file__, "yt_dlp_plugins/extractor"))
except ImportError:
    pass

icon_file = project / "assets" / "clipper.icns"
png_file = project / "assets" / "clipper.png"
if png_file.exists():
    datas.append((str(png_file), "assets"))

a = Analysis(
    ["main.py"],
    pathex=[str(project)],
    binaries=binaries,
    datas=datas,
    hiddenimports=["yt_dlp", "curl_cffi", "qdarktheme", "yt_dlp_ejs", "certifi"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Clipper",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(icon_file) if icon_file.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Clipper",
)

app = BUNDLE(
    coll,
    name="Clipper.app",
    icon=str(icon_file) if icon_file.exists() else None,
    bundle_identifier="com.kostido.clipper",
    info_plist={
        "CFBundleName": "Clipper",
        "CFBundleDisplayName": "Clipper",
        "CFBundleShortVersionString": "1.4.0",
        "CFBundleVersion": "1.4.0",
        "NSHighResolutionCapable": True,
        # Приложение только читает файлы и качает по сети — камера и микрофон не нужны.
        "LSMinimumSystemVersion": "11.0",
        "NSAppleEventsUsageDescription": "Открытие папки с результатом в Finder.",
    },
)
