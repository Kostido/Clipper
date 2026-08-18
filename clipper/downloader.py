"""Скачивание видео по ссылке через yt-dlp."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import ffmpeg_tools

URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def find_url(text: str) -> Optional[str]:
    """Достаём ссылку из строки — люди часто вставляют её вместе с текстом."""
    m = URL_RE.search((text or "").strip())
    return m.group(0).rstrip(".,;)") if m else None


class DownloadCancelled(RuntimeError):
    pass


@dataclass
class DownloadResult:
    path: Path
    title: str
    duration: float


QUALITY_FORMATS = {
    "Максимальное": "bestvideo*+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
}


def download(
    url: str,
    out_dir: Path,
    quality: str = "Максимальное",
    on_progress: Optional[Callable[[float, str], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    cookies_from_browser: Optional[str] = None,
) -> DownloadResult:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Не установлен yt-dlp. Выполните: pip install -r requirements.txt"
        ) from exc

    out_dir.mkdir(parents=True, exist_ok=True)

    def hook(d: dict) -> None:
        if should_cancel and should_cancel():
            raise DownloadCancelled()
        if d.get("status") == "downloading" and on_progress:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            percent = (done / total * 100.0) if total else 0.0
            speed = d.get("speed") or 0
            speed_txt = f"{speed / 1024 / 1024:.1f} МБ/с" if speed else ""
            on_progress(percent, speed_txt)
        elif d.get("status") == "finished" and on_progress:
            on_progress(100.0, "обработка…")

    class _Logger:
        def debug(self, msg: str) -> None:
            if on_log and not msg.startswith("[debug]"):
                on_log(msg)

        def info(self, msg: str) -> None:
            if on_log:
                on_log(msg)

        def warning(self, msg: str) -> None:
            if on_log:
                on_log(msg)

        def error(self, msg: str) -> None:
            if on_log:
                on_log(msg)

    opts: dict = {
        "outtmpl": str(out_dir / "%(title).80B [%(id)s].%(ext)s"),
        "format": QUALITY_FORMATS.get(quality, QUALITY_FORMATS["Максимальное"]),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "progress_hooks": [hook],
        "logger": _Logger(),
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
    }
    ffmpeg = ffmpeg_tools.ffmpeg_path()
    if ffmpeg:
        # yt-dlp нужен ffmpeg, чтобы склеить раздельные видео- и аудиодорожки.
        opts["ffmpeg_location"] = str(ffmpeg.parent)
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info.get("_type") == "playlist":
            info = info["entries"][0]
        path = Path(ydl.prepare_filename(info))
        if not path.exists():
            merged = path.with_suffix(".mp4")
            path = merged if merged.exists() else _guess_downloaded(out_dir, path)
    return DownloadResult(
        path=path,
        title=str(info.get("title") or path.stem),
        duration=float(info.get("duration") or 0.0),
    )


def _guess_downloaded(out_dir: Path, expected: Path) -> Path:
    """Расширение могло смениться после мерджа — ищем файл с тем же именем."""
    matches = sorted(out_dir.glob(expected.stem + ".*"), key=lambda p: p.stat().st_mtime)
    if matches:
        return matches[-1]
    raise FileNotFoundError(f"Скачанный файл не найден: {expected}")
