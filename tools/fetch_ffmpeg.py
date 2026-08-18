"""Скачивает ffmpeg/ffprobe для Windows в папку bin/.

Запуск: python tools/fetch_ffmpeg.py
Если сеть недоступна — положите ffmpeg.exe и ffprobe.exe в bin/ вручную
(https://www.gyan.dev/ffmpeg/builds/ или https://github.com/BtbN/FFmpeg-Builds).
"""
from __future__ import annotations

import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)
WANTED = ("ffmpeg.exe", "ffprobe.exe")


def main() -> int:
    bin_dir = Path(__file__).resolve().parent.parent / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    if all((bin_dir / name).exists() for name in WANTED):
        print("ffmpeg уже в bin/ — пропускаю.")
        return 0

    print(f"Качаю {URL} …")
    with urllib.request.urlopen(URL, timeout=120) as response:
        payload = response.read()
    print(f"Скачано {len(payload) / 1024 / 1024:.1f} МБ, распаковываю…")

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for member in archive.namelist():
            name = Path(member).name
            if name in WANTED:
                with archive.open(member) as src, open(bin_dir / name, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                print(f"  → bin/{name}")

    missing = [n for n in WANTED if not (bin_dir / n).exists()]
    if missing:
        print("Не найдены в архиве: " + ", ".join(missing), file=sys.stderr)
        return 1
    print("Готово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
