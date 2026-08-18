"""Где программа хранит настройки, кэш cookies и куда качает по умолчанию.

Два режима:
* обычный — настройки в профиле пользователя (реестр/plist), кэш в AppData
  или ~/Library/Application Support;
* портативный — всё рядом с программой, чтобы можно было носить на флешке.
  Включается файлом `portable.txt` возле исполняемого файла.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Clipper"
PORTABLE_MARKER = "portable.txt"


def app_dir() -> Path:
    """Каталог с программой: рядом с exe или с исходниками."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        # На macOS exe лежит внутри Clipper.app/Contents/MacOS — наружу от бандла.
        if sys.platform == "darwin" and "Contents/MacOS" in exe.as_posix():
            return exe.parents[3]
        return exe.parent
    return Path(__file__).resolve().parent.parent


def is_portable() -> bool:
    return (app_dir() / PORTABLE_MARKER).exists()


def data_dir() -> Path:
    """Куда писать кэш cookies и прочее наше добро."""
    if is_portable():
        return app_dir() / "ClipperData"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def settings_file() -> Path | None:
    """Путь к ini-файлу настроек — только в портативном режиме."""
    return (data_dir() / "settings.ini") if is_portable() else None


def default_download_dir() -> Path:
    if is_portable():
        return app_dir() / "Downloads"
    folder = "Movies" if sys.platform == "darwin" else "Videos"
    return Path.home() / folder / APP_NAME
