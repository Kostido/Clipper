# -*- mode: python ; coding: utf-8 -*-
"""Сборка одного .exe: pyinstaller Clipper.spec"""
from pathlib import Path

project = Path(SPECPATH)

# ffmpeg.exe/ffprobe.exe кладём в bin/ — тогда они попадут внутрь exe.
binaries = []
for name in ("ffmpeg.exe", "ffprobe.exe", "qjs.exe", "rustypipe-botguard.exe"):
    candidate = project / "bin" / name
    if candidate.exists():
        binaries.append((str(candidate), "bin"))

datas = []
# Плагин генерации PO-токенов: yt-dlp ищет пакет yt_dlp_plugins в путях sys.path,
# а в собранном exe туда попадает корень бандла.
try:
    import yt_dlp_plugins.extractor.yt_dlp_get_pot_rustypipe as _pot_plugin
    datas.append((_pot_plugin.__file__, "yt_dlp_plugins/extractor"))
except ImportError:
    pass
icon_file = project / "assets" / "clipper.ico"
if icon_file.exists():
    datas.append((str(icon_file), "assets"))

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
    a.binaries,
    a.datas,
    [],
    name="Clipper",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(icon_file) if icon_file.exists() else None,
)
