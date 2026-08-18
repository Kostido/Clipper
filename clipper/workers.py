"""Фоновые потоки: скачивание и рендер не должны морозить интерфейс."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import downloader, ffmpeg_tools, updater


class DownloadWorker(QThread):
    progress = Signal(float, str)
    log = Signal(str)
    finished_ok = Signal(object)      # downloader.DownloadResult
    failed = Signal(str)

    def __init__(self, url: str, out_dir: Path, quality: str, browser: str | None = None,
                 cookies_file: Path | None = None, proxy: str | None = None) -> None:
        super().__init__()
        self._url = url
        self._out_dir = out_dir
        self._quality = quality
        self._browser = browser
        self._cookies_file = cookies_file
        self._proxy = proxy
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
                cookies_file=self._cookies_file,
                proxy=self._proxy,
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


class UpdateCheckWorker(QThread):
    """Тихо спрашиваем GitHub про свежий релиз — интерфейс не ждёт сеть."""

    result = Signal(object)      # updater.Release | None
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.result.emit(updater.check())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class UpdateDownloadWorker(QThread):
    progress = Signal(float)
    finished_ok = Signal(object)   # Path со скачанным exe
    failed = Signal(str)

    def __init__(self, release) -> None:
        super().__init__()
        self._release = release
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            staged = updater.download(
                self._release,
                on_progress=lambda p: self.progress.emit(p),
                should_cancel=lambda: self._cancel,
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(staged)


class PreviewProxyWorker(QThread):
    """Пережимает файл в H.264 для просмотра — оригинал остаётся как есть."""

    progress = Signal(float)
    finished_ok = Signal(object)   # Path готового превью
    failed = Signal(str)

    def __init__(self, src: Path, dst: Path) -> None:
        super().__init__()
        self._src = src
        self._dst = dst
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            path = ffmpeg_tools.make_preview_proxy(
                self._src, self._dst,
                on_progress=lambda p: self.progress.emit(p),
                should_cancel=lambda: self._cancel,
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(path)


class ThumbnailWorker(QThread):
    """Нарезает кадры для предпросмотра, пока пользователь смотрит видео."""

    ready = Signal(object)         # список (секунда, путь)

    def __init__(self, src: Path, out_dir: Path) -> None:
        super().__init__()
        self._src = src
        self._out_dir = out_dir
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    # Сначала редкая сетка — с ней предпросмотр работает почти сразу,
    # потом плотная. Первый запуск ffmpeg на холодной машине долгий, и ждать
    # сотню кадров ради первого движения мышью незачем.
    STAGES = (16, 120)

    def run(self) -> None:
        for count in self.STAGES:
            if self._cancel:
                return
            try:
                frames = ffmpeg_tools.extract_thumbnails(
                    self._src, self._out_dir / str(count), count=count,
                    should_cancel=lambda: self._cancel)
            except Exception:  # noqa: BLE001 — без раскадровки работаем как раньше
                frames = []
            if frames and not self._cancel:
                self.ready.emit(frames)
