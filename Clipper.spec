# -*- mode: python ; coding: utf-8 -*-
"""Сборка одного .exe: pyinstaller Clipper.spec"""
from pathlib import Path

project = Path(SPECPATH)

# ffmpeg.exe/ffprobe.exe кладём в bin/ — тогда они попадут внутрь exe.
binaries = []
for name in ("ffmpeg.exe", "ffprobe.exe"):
    candidate = project / "bin" / name
    if candidate.exists():
        binaries.append((str(candidate), "bin"))

datas = []
icon_file = project / "assets" / "clipper.ico"
if icon_file.exists():
    datas.append((str(icon_file), "assets"))

a = Analysis(
    ["main.py"],
    pathex=[str(project)],
    binaries=binaries,
    datas=datas,
    hiddenimports=["yt_dlp"],
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
