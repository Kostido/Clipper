"""Качает в bin/ то, без чего YouTube отдаёт 403.

qjs.exe                  — движок JavaScript (yt-dlp считает им подписи ссылок)
rustypipe-botguard.exe   — генератор PO-токенов для популярных роликов
"""
from __future__ import annotations

import json
import io
import os
import platform
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"

QJS_RELEASE = "https://api.github.com/repos/quickjs-ng/quickjs/releases/latest"
BOTGUARD_RELEASE = (
    "https://codeberg.org/api/v1/repos/ThetaDev/rustypipe-botguard/releases/latest"
)


def _platform_assets() -> tuple:
    """Какие файлы качать под текущую систему: (имя qjs, хвост архива botguard)."""
    arm = platform.machine().lower() in ("arm64", "aarch64")
    if sys.platform == "darwin":
        return (
            "qjs-darwin-arm64" if arm else "qjs-darwin-x86_64",
            "aarch64-apple-darwin.tar.xz" if arm else "x86_64-apple-darwin.tar.xz",
        )
    if sys.platform.startswith("linux"):
        return (
            "qjs-linux-aarch64" if arm else "qjs-linux-x86_64",
            "aarch64-unknown-linux-gnu.tar.xz" if arm else "x86_64-unknown-linux-gnu.tar.xz",
        )
    return "qjs-windows-x86_64.exe", "x86_64-pc-windows-msvc.zip"


QJS_ASSET, BOTGUARD_ASSET_SUFFIX = _platform_assets()
EXE = ".exe" if sys.platform == "win32" else ""


def _api_headers() -> dict:
    """В CI без токена GitHub быстро упирается в лимит запросов."""
    headers = {"User-Agent": "Clipper-fetch"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(url: str) -> bytes:
    # Codeberg токен GitHub не понимает, но лишний заголовок ему не мешает.
    request = urllib.request.Request(url, headers=_api_headers())
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _assets(api_url: str) -> list:
    return json.loads(_get(api_url).decode("utf-8")).get("assets", [])


def fetch_qjs() -> None:
    target = BIN / f"qjs{EXE}"
    if target.exists():
        print(f"  {target.name} уже на месте ({target.stat().st_size // 1024} КБ)")
        return
    url = next((a["browser_download_url"] for a in _assets(QJS_RELEASE)
                if a["name"] == QJS_ASSET), None)
    if not url:
        raise SystemExit(f"В релизе quickjs-ng нет файла {QJS_ASSET}")
    print(f"  качаю {url}")
    target.write_bytes(_get(url))
    target.chmod(0o755)
    print(f"  {target} ({target.stat().st_size // 1024} КБ)")


def fetch_botguard() -> None:
    target = BIN / f"rustypipe-botguard{EXE}"
    if target.exists():
        print(f"  {target.name} уже на месте "
              f"({target.stat().st_size // 1024 // 1024} МБ)")
        return
    url = next((a["browser_download_url"] for a in _assets(BOTGUARD_RELEASE)
                if a["name"].endswith(BOTGUARD_ASSET_SUFFIX)), None)
    if not url:
        raise SystemExit("В релизе rustypipe-botguard нет сборки под Windows")
    print(f"  качаю {url}")
    blob = _get(url)
    if url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            name = next((n for n in archive.namelist() if n.endswith(".exe")), None)
            if not name:
                raise SystemExit("В архиве rustypipe-botguard нет exe")
            target.write_bytes(archive.read(name))
    else:                                   # tar.xz для macOS и Linux
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:xz") as archive:
            member = next((m for m in archive.getmembers()
                           if m.isfile() and "rustypipe-botguard" in m.name), None)
            if not member:
                raise SystemExit("В архиве rustypipe-botguard нет бинарника")
            extracted = archive.extractfile(member)
            target.write_bytes(extracted.read())
    target.chmod(0o755)
    print(f"  {target} ({target.stat().st_size // 1024 // 1024} МБ)")


def main() -> int:
    BIN.mkdir(parents=True, exist_ok=True)
    print("JavaScript-движок для подписей YouTube:")
    fetch_qjs()
    print("Генератор PO-токенов YouTube:")
    fetch_botguard()
    print("Готово.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
