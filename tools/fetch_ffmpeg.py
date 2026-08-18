"""Скачивает ffmpeg/ffprobe в папку bin/ под текущую систему.

Запуск: python tools/fetch_ffmpeg.py
Windows — сборки BtbN, macOS — сборки OSXExperts/evermeet.
Если сеть недоступна, положите бинарники в bin/ вручную:
https://github.com/BtbN/FFmpeg-Builds (Windows) или https://evermeet.cx/ffmpeg (macOS).
"""
from __future__ import annotations

import io
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"
EXE = ".exe" if sys.platform == "win32" else ""
WANTED = (f"ffmpeg{EXE}", f"ffprobe{EXE}")

WINDOWS_ZIP = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)
# У evermeet каждый бинарник лежит отдельным архивом.
MAC_ZIPS = {
    "ffmpeg": "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
    "ffprobe": "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip",
}
LINUX_TAR = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-linux64-gpl.tar.xz"
)


def _download(url: str) -> bytes:
    print(f"Качаю {url} …")
    request = urllib.request.Request(url, headers={"User-Agent": "Clipper-fetch"})
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
    print(f"  {len(payload) / 1024 / 1024:.1f} МБ")
    return payload


def _from_archive(payload: bytes, kind: str) -> None:
    """Достаём только ffmpeg/ffprobe, остальное из архива не нужно."""
    if kind == "zip":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [(m, Path(m).name) for m in archive.namelist()]
            for member, name in members:
                if name in WANTED:
                    with archive.open(member) as src, open(BIN / name, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    print(f"  → bin/{name}")
        return
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as archive:
        for member in archive.getmembers():
            name = Path(member.name).name
            if member.isfile() and name in WANTED:
                extracted = archive.extractfile(member)
                (BIN / name).write_bytes(extracted.read())
                print(f"  → bin/{name}")


def main() -> int:
    BIN.mkdir(parents=True, exist_ok=True)
    if all((BIN / name).exists() for name in WANTED):
        print("ffmpeg уже в bin/ — пропускаю.")
        return 0

    if sys.platform == "win32":
        _from_archive(_download(WINDOWS_ZIP), "zip")
    elif sys.platform == "darwin":
        if platform.machine().lower() == "arm64":
            print("Внимание: evermeet отдаёт сборки x86_64; на Apple Silicon они "
                  "работают через Rosetta. Для нативной сборки поставьте "
                  "ffmpeg через brew и уберите bin/ffmpeg.")
        for url in MAC_ZIPS.values():
            _from_archive(_download(url), "zip")
    else:
        _from_archive(_download(LINUX_TAR), "tar")

    missing = [name for name in WANTED if not (BIN / name).exists()]
    if missing:
        print(f"Не удалось получить: {', '.join(missing)}")
        return 1
    for name in WANTED:
        (BIN / name).chmod(0o755)
    print("Готово.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
