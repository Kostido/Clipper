"""Clipper — скачать видео по ссылке, обрезать кусок, отрендерить в H.264."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSlider, QSpinBox, QSplitter, QStyle, QVBoxLayout,
    QWidget,
)

from . import downloader, ffmpeg_tools
from .timecode import format_tc, parse_tc
from .workers import DownloadWorker, ExportWorker

APP_NAME = "Clipper"
PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast",
           "medium", "slow", "slower"]
RESOLUTIONS = [("Как в исходнике", 0), ("2160p", 2160), ("1440p", 1440),
               ("1080p", 1080), ("720p", 720), ("480p", 480)]
FPS_CHOICES = [("Как в исходнике", 0.0), ("60", 60.0), ("50", 50.0),
               ("30", 30.0), ("25", 25.0), ("24", 24.0)]
BROWSERS = ["Не использовать", "chrome", "edge", "firefox", "brave", "opera", "vivaldi"]


def default_download_dir() -> Path:
    return Path.home() / "Videos" / APP_NAME


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — скачать, обрезать, отрендерить")
        self.resize(1100, 760)

        self.settings = QSettings("Clipper", "Clipper")
        self.source: Path | None = None
        self.info: ffmpeg_tools.MediaInfo | None = None
        self.download_worker: DownloadWorker | None = None
        self.export_worker: ExportWorker | None = None
        self._slider_held = False

        self._build_ui()
        self._restore_settings()
        self._check_ffmpeg()

    # ---------------------------------------------------------------- UI ----
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(self._build_source_box())

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._build_player_widget())
        bottom = QWidget()
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(self._build_trim_box(), 3)
        bottom_layout.addWidget(self._build_export_box(), 2)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        self.log_view.setFixedHeight(96)
        root.addWidget(self.log_view)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Готов к работе")

    def _build_source_box(self) -> QGroupBox:
        box = QGroupBox("1. Источник видео")
        layout = QVBoxLayout(box)

        row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "Вставьте ссылку: YouTube, Vimeo, TikTok, Instagram, VK, X/Twitter…"
        )
        self.url_edit.returnPressed.connect(self.start_download)
        row.addWidget(self.url_edit, 1)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(list(downloader.QUALITY_FORMATS.keys()))
        row.addWidget(QLabel("Качество:"))
        row.addWidget(self.quality_combo)

        self.download_btn = QPushButton("Скачать")
        self.download_btn.setDefault(True)
        self.download_btn.clicked.connect(self.start_download)
        row.addWidget(self.download_btn)

        self.open_btn = QPushButton("Открыть файл…")
        self.open_btn.clicked.connect(self.open_local_file)
        row.addWidget(self.open_btn)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Куда качать:"))
        self.dir_edit = QLineEdit(str(default_download_dir()))
        row2.addWidget(self.dir_edit, 1)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self.choose_dir)
        row2.addWidget(browse)
        row2.addWidget(QLabel("Cookies из браузера:"))
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(BROWSERS)
        self.browser_combo.setToolTip(
            "Нужно для видео, доступных только после входа в аккаунт "
            "(приватные, возрастные ограничения)."
        )
        row2.addWidget(self.browser_combo)
        layout.addLayout(row2)

        self.dl_progress = QProgressBar()
        self.dl_progress.setTextVisible(True)
        self.dl_progress.setFormat("Скачивание: %p%")
        layout.addWidget(self.dl_progress)
        return box

    def _build_player_widget(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(260)
        self.video_widget.setStyleSheet("background:#101014;")
        layout.addWidget(self.video_widget, 1)

        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_out)
        self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.errorOccurred.connect(
            lambda _e, msg: self.log(f"Проигрыватель: {msg}") if msg else None
        )

        controls = QHBoxLayout()
        style = self.style()
        self.play_btn = QPushButton(style.standardIcon(QStyle.SP_MediaPlay), "")
        self.play_btn.setFixedWidth(40)
        self.play_btn.clicked.connect(self.toggle_play)
        controls.addWidget(self.play_btn)

        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderPressed.connect(lambda: setattr(self, "_slider_held", True))
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.position_slider.sliderMoved.connect(
            lambda v: self.time_label.setText(f"{format_tc(v / 1000)} / {self._duration_text()}")
        )
        controls.addWidget(self.position_slider, 1)

        self.time_label = QLabel("00:00:00.000 / 00:00:00.000")
        self.time_label.setStyleSheet("font-family: Consolas, monospace;")
        controls.addWidget(self.time_label)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setFixedWidth(90)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.valueChanged.connect(lambda v: self.audio_out.setVolume(v / 100))
        self.audio_out.setVolume(0.8)
        controls.addWidget(QLabel("🔊"))
        controls.addWidget(self.volume_slider)
        layout.addLayout(controls)
        return wrapper

    def _build_trim_box(self) -> QGroupBox:
        box = QGroupBox("2. Обрезка")
        layout = QVBoxLayout(box)

        row_in = QHBoxLayout()
        mark_in = QPushButton("⏮ Начало = текущая позиция")
        mark_in.clicked.connect(self.mark_in)
        self.in_edit = QLineEdit("00:00:00.000")
        self.in_edit.editingFinished.connect(self._on_range_edited)
        row_in.addWidget(mark_in)
        row_in.addWidget(self.in_edit, 1)
        goto_in = QPushButton("→")
        goto_in.setFixedWidth(32)
        goto_in.setToolTip("Перейти к началу фрагмента")
        goto_in.clicked.connect(lambda: self.seek(parse_tc(self.in_edit.text()) or 0))
        row_in.addWidget(goto_in)
        layout.addLayout(row_in)

        row_out = QHBoxLayout()
        mark_out = QPushButton("⏭ Конец = текущая позиция")
        mark_out.clicked.connect(self.mark_out)
        self.out_edit = QLineEdit("00:00:00.000")
        self.out_edit.editingFinished.connect(self._on_range_edited)
        row_out.addWidget(mark_out)
        row_out.addWidget(self.out_edit, 1)
        goto_out = QPushButton("→")
        goto_out.setFixedWidth(32)
        goto_out.setToolTip("Перейти к концу фрагмента")
        goto_out.clicked.connect(lambda: self.seek(parse_tc(self.out_edit.text()) or 0))
        row_out.addWidget(goto_out)
        layout.addLayout(row_out)

        nudge = QHBoxLayout()
        for label, delta in (("−1 с", -1.0), ("−0.1 с", -0.1),
                             ("+0.1 с", 0.1), ("+1 с", 1.0)):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, d=delta: self.nudge(d))
            nudge.addWidget(btn)
        preview = QPushButton("▶ Проиграть фрагмент")
        preview.clicked.connect(self.preview_clip)
        nudge.addWidget(preview)
        reset = QPushButton("Сбросить")
        reset.clicked.connect(self.reset_range)
        nudge.addWidget(reset)
        layout.addLayout(nudge)

        self.range_label = QLabel("Длительность фрагмента: —")
        layout.addWidget(self.range_label)
        layout.addStretch(1)
        return box

    def _build_export_box(self) -> QGroupBox:
        box = QGroupBox("3. Рендер H.264")
        form = QFormLayout(box)

        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(14, 32)
        self.crf_spin.setValue(20)
        self.crf_spin.setToolTip("Меньше = лучше качество и больше файл. 18–23 — обычный диапазон.")
        form.addRow("Качество (CRF):", self.crf_spin)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(PRESETS)
        self.preset_combo.setCurrentText("medium")
        form.addRow("Скорость (preset):", self.preset_combo)

        self.res_combo = QComboBox()
        for label, _ in RESOLUTIONS:
            self.res_combo.addItem(label)
        form.addRow("Разрешение:", self.res_combo)

        self.fps_combo = QComboBox()
        for label, _ in FPS_CHOICES:
            self.fps_combo.addItem(label)
        form.addRow("Кадры/с:", self.fps_combo)

        self.copy_check = QCheckBox("Без перекодирования (быстро, режет по ключевым кадрам)")
        self.copy_check.toggled.connect(self._on_copy_toggled)
        form.addRow(self.copy_check)

        self.export_progress = QProgressBar()
        self.export_progress.setFormat("Рендер: %p%")
        form.addRow(self.export_progress)

        buttons = QHBoxLayout()
        self.export_btn = QPushButton("Отрендерить фрагмент…")
        self.export_btn.clicked.connect(self.start_export)
        buttons.addWidget(self.export_btn)
        self.open_folder_btn = QPushButton("Открыть папку")
        self.open_folder_btn.clicked.connect(self.open_output_dir)
        buttons.addWidget(self.open_folder_btn)
        form.addRow(buttons)
        return box

    # ----------------------------------------------------------- helpers ----
    def log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _duration_text(self) -> str:
        return format_tc(self.player.duration() / 1000) if self.player.duration() else "00:00:00.000"

    def _check_ffmpeg(self) -> None:
        path = ffmpeg_tools.ffmpeg_path()
        if path:
            self.log(f"ffmpeg: {path}")
        else:
            self.log("ffmpeg не найден — скачивание в высоком качестве и рендер работать не будут.")
            QMessageBox.warning(self, APP_NAME, str(ffmpeg_tools.FFmpegMissingError()))

    def _restore_settings(self) -> None:
        saved_dir = self.settings.value("download_dir", type=str)
        if saved_dir:
            self.dir_edit.setText(saved_dir)
        self.quality_combo.setCurrentText(
            self.settings.value("quality", "Максимальное", type=str)
        )
        self.crf_spin.setValue(int(self.settings.value("crf", 20)))
        self.preset_combo.setCurrentText(self.settings.value("preset", "medium", type=str))

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        self.settings.setValue("download_dir", self.dir_edit.text())
        self.settings.setValue("quality", self.quality_combo.currentText())
        self.settings.setValue("crf", self.crf_spin.value())
        self.settings.setValue("preset", self.preset_combo.currentText())
        for worker in (self.download_worker, self.export_worker):
            if worker and worker.isRunning():
                worker.cancel()
                worker.wait(3000)
        super().closeEvent(event)

    # ---------------------------------------------------------- download ----
    def choose_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Папка для загрузок", self.dir_edit.text())
        if chosen:
            self.dir_edit.setText(chosen)

    def start_download(self) -> None:
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
            return
        url = downloader.find_url(self.url_edit.text())
        if not url:
            QMessageBox.information(self, APP_NAME, "Вставьте ссылку на видео.")
            return
        out_dir = Path(self.dir_edit.text().strip() or default_download_dir())
        browser = self.browser_combo.currentText()
        browser = None if browser == BROWSERS[0] else browser

        self.dl_progress.setValue(0)
        self.download_btn.setText("Отменить")
        self.statusBar().showMessage("Скачиваю…")
        self.log(f"Скачиваю {url}")

        worker = DownloadWorker(url, out_dir, self.quality_combo.currentText(), browser)
        worker.progress.connect(self._on_download_progress)
        worker.log.connect(self.log)
        worker.finished_ok.connect(self._on_download_done)
        worker.failed.connect(self._on_download_failed)
        worker.finished.connect(lambda: self.download_btn.setText("Скачать"))
        self.download_worker = worker
        worker.start()

    def _on_download_progress(self, percent: float, speed: str) -> None:
        self.dl_progress.setValue(int(percent))
        self.statusBar().showMessage(f"Скачиваю… {percent:.0f}% {speed}".strip())

    def _on_download_done(self, result: downloader.DownloadResult) -> None:
        self.dl_progress.setValue(100)
        self.log(f"Готово: {result.path}")
        self.statusBar().showMessage(f"Скачано: {result.title}")
        self.load_media(result.path)

    def _on_download_failed(self, message: str) -> None:
        self.statusBar().showMessage("Ошибка скачивания")
        self.log(f"Ошибка: {message}")
        QMessageBox.critical(self, APP_NAME, f"Не удалось скачать видео:\n\n{message}")

    def open_local_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите видео", self.dir_edit.text(),
            "Видео (*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.flv);;Все файлы (*.*)",
        )
        if path:
            self.load_media(Path(path))

    # -------------------------------------------------------------- media ---
    def load_media(self, path: Path) -> None:
        self.source = path
        try:
            self.info = ffmpeg_tools.probe(path)
        except Exception as exc:  # noqa: BLE001
            self.info = None
            self.log(f"Не удалось прочитать параметры файла: {exc}")
        if self.info:
            self.log(
                f"Файл: {path.name} — {self.info.width}x{self.info.height}, "
                f"{self.info.fps:.2f} к/с, {format_tc(self.info.duration)}"
            )
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.in_edit.setText(format_tc(0))
        if self.info and self.info.duration:
            self.out_edit.setText(format_tc(self.info.duration))
        self._update_range_label()
        self.setWindowTitle(f"{APP_NAME} — {path.name}")
        QTimer.singleShot(200, self.player.play)
        QTimer.singleShot(400, self.player.pause)

    def toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        else:
            self.player.play()
            self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def seek(self, seconds: float) -> None:
        self.player.setPosition(int(max(0.0, seconds) * 1000))

    def _on_position_changed(self, ms: int) -> None:
        if not self._slider_held:
            self.position_slider.setValue(ms)
        self.time_label.setText(f"{format_tc(ms / 1000)} / {self._duration_text()}")

    def _on_duration_changed(self, ms: int) -> None:
        self.position_slider.setRange(0, ms)
        if ms and (parse_tc(self.out_edit.text()) or 0) <= 0:
            self.out_edit.setText(format_tc(ms / 1000))
        self._update_range_label()

    def _on_slider_released(self) -> None:
        self._slider_held = False
        self.player.setPosition(self.position_slider.value())

    # --------------------------------------------------------------- trim ---
    def _current_seconds(self) -> float:
        return self.player.position() / 1000

    def mark_in(self) -> None:
        start = self._current_seconds()
        if start >= (parse_tc(self.out_edit.text()) or 0):
            self.out_edit.setText(format_tc(self._media_duration()))
        self.in_edit.setText(format_tc(start))
        self._update_range_label()

    def mark_out(self) -> None:
        end = self._current_seconds()
        if end <= (parse_tc(self.in_edit.text()) or 0):
            self.in_edit.setText(format_tc(0))
        self.out_edit.setText(format_tc(end))
        self._update_range_label()

    def nudge(self, delta: float) -> None:
        self.seek(max(0.0, self._current_seconds() + delta))

    def reset_range(self) -> None:
        self.in_edit.setText(format_tc(0))
        self.out_edit.setText(format_tc(self._media_duration()))
        self._update_range_label()

    def preview_clip(self) -> None:
        start, end = self.trim_range()
        if end <= start:
            return
        self.seek(start)
        self.player.play()
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        QTimer.singleShot(int((end - start) * 1000), self._stop_preview)

    def _stop_preview(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

    def _media_duration(self) -> float:
        if self.player.duration():
            return self.player.duration() / 1000
        return self.info.duration if self.info else 0.0

    def trim_range(self) -> tuple[float, float]:
        start = parse_tc(self.in_edit.text()) or 0.0
        end = parse_tc(self.out_edit.text()) or 0.0
        duration = self._media_duration()
        if duration:
            start = min(start, duration)
            end = min(end, duration) if end else duration
        return start, end

    def _on_range_edited(self) -> None:
        start, end = self.trim_range()
        self.in_edit.setText(format_tc(start))
        self.out_edit.setText(format_tc(end))
        self._update_range_label()

    def _update_range_label(self) -> None:
        start, end = self.trim_range()
        length = max(0.0, end - start)
        self.range_label.setText(
            f"Длительность фрагмента: {format_tc(length)}"
            if length else "Длительность фрагмента: —"
        )

    # ------------------------------------------------------------- export ---
    def _on_copy_toggled(self, checked: bool) -> None:
        for widget in (self.crf_spin, self.preset_combo, self.res_combo, self.fps_combo):
            widget.setEnabled(not checked)

    def start_export(self) -> None:
        if self.export_worker and self.export_worker.isRunning():
            self.export_worker.cancel()
            return
        if not self.source or not self.source.exists():
            QMessageBox.information(self, APP_NAME, "Сначала скачайте или откройте видео.")
            return
        start, end = self.trim_range()
        if end - start < 0.05:
            QMessageBox.information(self, APP_NAME, "Задайте фрагмент: конец должен быть позже начала.")
            return
        if not ffmpeg_tools.ffmpeg_path():
            QMessageBox.critical(self, APP_NAME, str(ffmpeg_tools.FFmpegMissingError()))
            return

        suggested = Path(self.dir_edit.text().strip() or ".") / f"{self.source.stem}_clip.mp4"
        dst, _ = QFileDialog.getSaveFileName(
            self, "Сохранить фрагмент", str(suggested), "MP4 (H.264) (*.mp4)"
        )
        if not dst:
            return
        dst_path = Path(dst)
        if dst_path.suffix.lower() != ".mp4":
            dst_path = dst_path.with_suffix(".mp4")
        if dst_path.resolve() == self.source.resolve():
            QMessageBox.warning(self, APP_NAME, "Нельзя записать результат поверх исходного файла.")
            return

        settings = ffmpeg_tools.ExportSettings(
            start=start,
            end=end,
            crf=self.crf_spin.value(),
            preset=self.preset_combo.currentText(),
            scale_height=RESOLUTIONS[self.res_combo.currentIndex()][1],
            fps=FPS_CHOICES[self.fps_combo.currentIndex()][1],
            copy_mode=self.copy_check.isChecked(),
        )
        self.export_progress.setValue(0)
        self.export_btn.setText("Отменить рендер")
        self.statusBar().showMessage("Рендерю…")

        worker = ExportWorker(self.source, dst_path, settings)
        worker.progress.connect(lambda p: self.export_progress.setValue(int(p)))
        worker.log.connect(self.log)
        worker.finished_ok.connect(self._on_export_done)
        worker.failed.connect(self._on_export_failed)
        worker.finished.connect(lambda: self.export_btn.setText("Отрендерить фрагмент…"))
        self.export_worker = worker
        worker.start()

    def _on_export_done(self, path: str) -> None:
        self.export_progress.setValue(100)
        self.statusBar().showMessage("Готово")
        self.log(f"Сохранено: {path}")
        answer = QMessageBox.question(
            self, APP_NAME, f"Фрагмент сохранён:\n{path}\n\nОткрыть папку?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            reveal(Path(path))

    def _on_export_failed(self, message: str) -> None:
        self.statusBar().showMessage("Ошибка рендера")
        self.log(f"Ошибка: {message}")
        QMessageBox.critical(self, APP_NAME, f"Не удалось отрендерить фрагмент:\n\n{message}")

    def open_output_dir(self) -> None:
        target = Path(self.dir_edit.text().strip() or default_download_dir())
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


def reveal(path: Path) -> None:
    """Показать файл в проводнике (на других ОС — открыть папку)."""
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    icon_path = Path(__file__).resolve().parent.parent / "assets" / "clipper.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
