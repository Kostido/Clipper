"""Обновление из релизов GitHub: проверка версии, загрузка, подмена exe."""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import __version__

REPO = "Kostido/Clipper"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
TIMEOUT = 20


def asset_name() -> str:
    """Как называется наш файл в релизе для текущей системы."""
    if sys.platform == "win32":
        return "Clipper.exe"
    if sys.platform == "darwin":
        return "Clipper-macos.zip"
    return "Clipper-linux"


def can_self_update() -> bool:
    """Себя на месте подменяем только на Windows: там это один exe.

    На macOS программа — бандл Clipper.app из множества файлов, к тому же
    подписанный; менять его на ходу нельзя, поэтому просто ведём в релизы.
    """
    return is_frozen() and sys.platform == "win32"


class UpdateError(RuntimeError):
    pass


@dataclass
class Release:
    tag: str
    version: tuple
    notes: str
    page_url: str
    asset_url: str
    asset_size: int

    @property
    def name(self) -> str:
        return self.tag.lstrip("vV")


def is_frozen() -> bool:
    """True — работаем как собранный exe, только его и можем подменить."""
    return bool(getattr(sys, "frozen", False))


def current_exe() -> Path:
    return Path(sys.executable)


def parse_version(text: str) -> tuple:
    """v1.4.2 → (1, 4, 2). Нечисловые хвосты игнорируем."""
    numbers = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in numbers[:4]) or (0,)


def current_version() -> tuple:
    return parse_version(__version__)


# ------------------------------------------------------------------ сеть ---
def _ssl_context() -> ssl.SSLContext:
    """В собранном приложении нет системного хранилища корневых сертификатов
    (на macOS это особенно заметно), поэтому берём набор из certifi."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 — остаёмся с системным набором
        return ssl.create_default_context()


def _open(url: str, timeout: int = TIMEOUT):
    request = urllib.request.Request(url, headers={
        "User-Agent": f"Clipper/{__version__}",
        "Accept": "application/vnd.github+json",
    })
    context = _ssl_context()
    try:
        return urllib.request.urlopen(request, timeout=timeout, context=context)
    except urllib.error.HTTPError:
        raise
    except Exception:
        # Тот же случай, что и при скачивании видео: в системе прописан прокси
        # выключенного VPN — пробуем в обход.
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context),
        )
        return opener.open(request, timeout=timeout)


def check() -> Optional[Release]:
    """Последний релиз или None, если релизов ещё не публиковали."""
    try:
        with _open(API_LATEST) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise UpdateError(f"GitHub ответил {exc.code}: {exc.reason}") from exc
    except Exception as exc:  # noqa: BLE001
        raise UpdateError(_network_hint(exc)) from exc

    tag = data.get("tag_name") or ""
    wanted = asset_name()
    asset = next(
        (a for a in data.get("assets", []) if a.get("name") == wanted),
        None,
    )
    return Release(
        tag=tag,
        version=parse_version(tag),
        notes=(data.get("body") or "").strip(),
        page_url=data.get("html_url") or RELEASES_URL,
        asset_url=(asset or {}).get("browser_download_url", ""),
        asset_size=int((asset or {}).get("size") or 0),
    )


def is_newer(release: Release) -> bool:
    return release.version > current_version()


def download(release: Release, on_progress: Callable[[float], None] | None = None,
             should_cancel: Callable[[], bool] | None = None) -> Path:
    """Качаем новый exe рядом с текущим, но под временным именем."""
    if not release.asset_url:
        raise UpdateError(
            f"В релизе {release.tag} нет файла {asset_name()} — обновиться нечем."
        )
    target = current_exe().with_name("Clipper.update.exe")
    total = release.asset_size
    done = 0
    with _open(release.asset_url, timeout=60) as response, open(target, "wb") as out:
        while True:
            if should_cancel and should_cancel():
                out.close()
                target.unlink(missing_ok=True)
                raise UpdateError("Обновление отменено.")
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if on_progress and total:
                on_progress(done / total * 100.0)

    _verify(target, total)
    return target


def _verify(path: Path, expected_size: int) -> None:
    size = path.stat().st_size
    if expected_size and size != expected_size:
        path.unlink(missing_ok=True)
        raise UpdateError(
            f"Файл скачался не полностью: {size} вместо {expected_size} байт."
        )
    with open(path, "rb") as handle:        # файл закрываем до удаления,
        header = handle.read(2)             # иначе Windows его не отдаёт
    if header != b"MZ":                     # подпись windows-исполняемого файла
        path.unlink(missing_ok=True)
        raise UpdateError("Скачан не exe-файл — обновление отменено.")


def apply_update(staged: Path) -> Path:
    """Windows не даёт перезаписать запущенный exe, но даёт его переименовать."""
    exe = current_exe()
    backup = exe.with_name("Clipper.old.exe")
    try:
        backup.unlink(missing_ok=True)
    except OSError:
        pass
    exe.rename(backup)
    try:
        staged.replace(exe)
    except OSError:
        backup.rename(exe)                    # откат, если подмена не удалась
        raise
    return exe


def cleanup_old() -> None:
    """Прошлую версию удаляем при следующем запуске — раньше она ещё занята."""
    if not is_frozen():
        return
    for name in ("Clipper.old.exe", "Clipper.update.exe"):
        try:
            current_exe().with_name(name).unlink(missing_ok=True)
        except OSError:
            pass


def restart() -> None:
    import subprocess

    subprocess.Popen([str(current_exe())], close_fds=True,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


def source_hint() -> str:
    return (
        "Программа запущена из исходников — обновляйтесь через git:\n"
        "    git pull\n"
        f"Готовые сборки: {RELEASES_URL}"
    )


def _network_hint(exc: Exception) -> str:
    """Одна и та же ошибка сети означает разное — подсказываем, что именно."""
    text = str(exc)
    low = text.lower()
    if "certificate" in low:
        return ("Не удалось проверить сертификат GitHub. Обычно виноваты "
                "неверные дата и время на компьютере или антивирус/корпоративный "
                "прокси, подменяющий сертификаты." + chr(10) + chr(10) + text)
    if "refused" in low or "10061" in low or "proxy" in low:
        return ("Нет соединения с GitHub: похоже, включён прокси, а его "
                "программа не запущена." + chr(10) + chr(10) + text)
    return f"Не удалось связаться с GitHub: {text}"
