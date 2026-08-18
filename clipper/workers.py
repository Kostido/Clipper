"""Фоновые потоки: скачивание и рендер не должны морозить интерфейс."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import downloader, ffmpeg_tools


class DownloadWorker(QThread):
    progress = Signal(float, str)
    log = Signal(str)
    finished_ok = Signal(object)      # downloader.DownloadResult
    failed = Signal(str)

    def __init__(self, url: str, out_dir: Path, quality: str, browser: str | None = None) -> None:
        super().__init__()
        self._url = url
        self._out_dir = out_dir
        self._quality = quality
        self._browser = browser
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            result = downloader.download(
                self._url,
                self._out_dir,
                quality=self._quality,
                on_progress=lambda p, s: self.progress.emit(p, s),
                on_log=lambda m: self.log.emit(m),
                should_cancel=lambda: self._cancel,
                cookies_from_browser=self._browser,
            )
        except downloader.DownloadCancelled:
            self.failed.emit("Скачивание отменено.")
        except Exception as exc:  # noqa: BLE001 — показываем пользователю любую ошибку
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(result)


class ExportWorker(QThread):
    progress = Signal(float)
    log = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, src: Path, dst: Path, settings: ffmpeg_tools.ExportSettings) -> None:
        super().__init__()
        self._src = src
        self._dst = dst
        self._settings = settings
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            ffmpeg_tools.export_clip(
                self._src,
                self._dst,
                self._settings,
                on_progress=lambda p: self.progress.emit(p),
                on_log=lambda m: self.log.emit(m),
                should_cancel=lambda: self._cancel,
            )
        except ffmpeg_tools.ExportCancelled:
            self.failed.emit("Рендер отменён.")
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(str(self._dst))
