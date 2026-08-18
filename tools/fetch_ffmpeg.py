"""Скачивает ffmpeg/ffprobe в папку bin/ под текущую систему.

Запуск: python tools/fetch_ffmpeg.py
Windows — сборки BtbN, macOS — сборки OSXExperts/evermeet.
Если сеть недоступна, положите бинарники в bin/ вручную:
https://github.com/BtbN/FFmpeg-Builds (Windows) или https://evermeet.cx/ffmpeg (macOS).
"""
from __future__ import annotations

import io
import os
import platform
import shutil
import sys
import tarfile
import urllib.parse
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
# Для macOS берём статические сборки: бинарники из Homebrew тянут за собой
# библиотеки из /opt/homebrew и на чужой машине не запускаются.
MAC_RELEASE = "https://api.github.com/repos/eugeneware/ffmpeg-static/releases/latest"
LINUX_TAR = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-linux64-gpl.tar.xz"
)


def _api_headers(url: str) -> dict:
    """Токен шлём только на api.github.com: на редиректах загрузки и на
    Codeberg он вызывает 401. Без него CI упирается в лимит запросов."""
    headers = {"User-Agent": "Clipper-fetch"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and urllib.parse.urlparse(url).hostname == "api.github.com":
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _download(url: str) -> bytes:
    print(f"Качаю {url} …")
    request = urllib.request.Request(url, headers=_api_headers(url))
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


def _fetch_macos() -> None:
    """Статические сборки ffmpeg/ffprobe под нужную архитектуру."""
    import gzip
    import json

    arch = "arm64" if platform.machine().lower() == "arm64" else "x64"
    data = json.loads(_download(MAC_RELEASE).decode("utf-8"))
    for tool in ("ffmpeg", "ffprobe"):
        wanted = f"{tool}-darwin-{arch}.gz"
        url = next((a["browser_download_url"] for a in data.get("assets", [])
                    if a["name"] == wanted), None)
        if not url:
            raise SystemExit(f"В релизе ffmpeg-static нет {wanted}")
        (BIN / tool).write_bytes(gzip.decompress(_download(url)))
        print(f"  → bin/{tool}")


def main() -> int:
    BIN.mkdir(parents=True, exist_ok=True)
    if all((BIN / name).exists() for name in WANTED):
        print("ffmpeg уже в bin/ — пропускаю.")
        return 0

    if sys.platform == "win32":
        _from_archive(_download(WINDOWS_ZIP), "zip")
    elif sys.platform == "darwin":
        _fetch_macos()
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
