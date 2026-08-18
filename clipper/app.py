"""Clipper — скачать видео по ссылке, обрезать кусок, отрендерить в H.264."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QSettings, QSize, QUrl, QTimer
from PySide6.QtGui import (QColor, QDesktopServices, QIcon, QKeySequence,
                           QPainter, QPainterPath, QPixmap, QShortcut)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from . import __version__, downloader, ffmpeg_tools, storage, updater
from .timecode import format_tc
from .timeline import TimelineWidget
from .workers import (DownloadWorker, ExportWorker, PreviewProxyWorker,
                      UpdateCheckWorker, UpdateDownloadWorker)

APP_NAME = "Clipper"
PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast",
           "medium", "slow", "slower"]
RESOLUTIONS = [("Как в исходнике", 0), ("2160p", 2160), ("1440p", 1440),
               ("1080p", 1080), ("720p", 720), ("480p", 480)]
FPS_CHOICES = [("Как в исходнике", 0.0), ("60", 60.0), ("50", 50.0),
               ("30", 30.0), ("25", 25.0), ("24", 24.0)]
VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".flv",
                  ".mpg", ".mpeg", ".wmv", ".ts", ".m2ts", ".3gp", ".ogv"}
BROWSERS = [downloader.BROWSER_AUTO, "Не использовать",
            "chrome", "edge", "firefox", "brave", "opera", "vivaldi"]


# --- оформление -------------------------------------------------------------
BG = "#0e1015"          # фон окна
CARD = "#151922"        # карточки
FIELD = "#0f1218"       # поля ввода
LINE = "#242a38"        # границы
TEXT = "#e6e8ef"
MUTED = "#868ea4"
ACCENT = "#4c8dff"

QSS = f"""
QWidget {{ color: {TEXT}; font-size: 13px; }}
QWidget#central, QMainWindow {{ background: {BG}; }}

QFrame#card {{
    background: {CARD};
    border: 1px solid {LINE};
    border-radius: 14px;
}}
QLabel#section {{ color: {MUTED}; font-size: 11px; font-weight: 600; }}
QLabel#hint {{ color: {MUTED}; }}
QLabel#mono {{ font-family: Consolas, monospace; color: {MUTED}; }}

QLineEdit, QComboBox, QSpinBox {{
    background: {FIELD};
    border: 1px solid {LINE};
    border-radius: 10px;
    padding: 8px 12px;
    min-height: 20px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QLineEdit#url {{ font-size: 14px; padding: 11px 14px; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: #5a6274; }}

QPushButton {{
    background: #1c2130;
    border: 1px solid {LINE};
    border-radius: 10px;
    padding: 8px 16px;
}}
QPushButton:hover {{ background: #232a3b; }}
QPushButton:pressed {{ background: #161a25; }}
QPushButton:disabled {{ color: #5a6274; background: #171b25; }}
QPushButton#primary {{
    background: {ACCENT}; border: none; color: #07101f; font-weight: 600;
    padding: 10px 22px;
}}
QPushButton#primary:hover {{ background: #6ba1ff; }}
QPushButton#primary:disabled {{ background: #2a3550; color: #6b7488; }}
QPushButton#ghost {{
    background: transparent; border: none; color: {MUTED}; padding: 7px 12px;
}}
QPushButton#ghost:hover {{ color: {TEXT}; background: #1c2130; }}
QPushButton#round {{
    border-radius: 17px; background: {ACCENT}; border: none; padding: 0px;
}}
QPushButton#round:hover {{ background: #6ba1ff; }}

QProgressBar {{
    background: {FIELD}; border: none; border-radius: 4px;
    max-height: 8px; text-align: center; color: {MUTED};
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}

QPlainTextEdit#log {{
    background: #0b0d12; border: 1px solid {LINE}; border-radius: 10px;
    color: {MUTED}; font-family: Consolas, monospace; font-size: 11px;
    padding: 8px;
}}

QSlider::groove:horizontal {{ height: 4px; background: {LINE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 12px; height: 12px; margin: -5px 0; border-radius: 6px; background: {TEXT};
}}

QCheckBox {{ spacing: 8px; color: {MUTED}; }}
QMenuBar {{ background: transparent; padding: 4px 6px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 7px; color: {MUTED}; }}
QMenuBar::item:selected {{ background: #1c2130; color: {TEXT}; }}
QStatusBar {{ color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QToolTip {{
    background: #1c2130; color: {TEXT}; border: 1px solid {LINE};
    padding: 6px 8px; border-radius: 8px;
}}
"""


VIDEO_IDLE_STYLE = f"background:#0a0c11; border:1px dashed {LINE}; border-radius:12px;"
VIDEO_DROP_STYLE = f"background:#111726; border:2px dashed {ACCENT}; border-radius:12px;"
# Когда видео загружено, рамка ни к чему — остаётся чистый кадр.
VIDEO_ACTIVE_STYLE = "background:#000000; border:none; border-radius:12px;"


def _glyph_icon(kind: str, size: int = 18, color: str = "#07101f") -> QIcon:
    """Иконка воспроизведения или паузы: рисуем, чтобы она села ровно по центру."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    if kind == "play":
        path = QPainterPath()
        path.moveTo(size * 0.34, size * 0.22)
        path.lineTo(size * 0.34, size * 0.78)
        path.lineTo(size * 0.80, size * 0.50)
        path.closeSubpath()
        painter.drawPath(path)
    else:
        bar_w, gap = size * 0.16, size * 0.14
        left = (size - (bar_w * 2 + gap)) / 2
        for i in range(2):
            painter.drawRoundedRect(
                QRectF(left + i * (bar_w + gap), size * 0.24, bar_w, size * 0.52),
                bar_w * 0.35, bar_w * 0.35)
    painter.end()
    return QIcon(pixmap)


def default_download_dir() -> Path:
    return storage.default_download_dir()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — скачать, обрезать, отрендерить")
        self.resize(1100, 760)

        ini = storage.settings_file()
        if ini:                                  # портативный режим: файл рядом
            ini.parent.mkdir(parents=True, exist_ok=True)
            self.settings = QSettings(str(ini), QSettings.IniFormat)
        else:
            self.settings = QSettings("Clipper", "Clipper")
        self.source: Path | None = None
        self.info: ffmpeg_tools.MediaInfo | None = None
        self.download_worker: DownloadWorker | None = None
        self.export_worker: ExportWorker | None = None
        self.update_worker: UpdateCheckWorker | None = None
        self.update_dl_worker: UpdateDownloadWorker | None = None
        self._update_silent = True
        # Предпросмотр кадра под меткой: куда вернуться и что было до него.
        self._preview_return: int | None = None
        self._preview_was_playing = False
        self._pending_seek: int | None = None
        self.proxy_worker: PreviewProxyWorker | None = None

        self.setAcceptDrops(True)
        self._build_ui()
        self.settings_dialog = self._build_settings_dialog()
        self._build_menu()
        self._build_shortcuts()
        self._restore_settings()
        self._check_theme()
        self._check_ffmpeg()
        updater.cleanup_old()          # подчищаем прошлую версию после обновления
        if self.autoupdate_action.isChecked():
            QTimer.singleShot(1500, lambda: self.check_updates(silent=True))

    # ---------------------------------------------------------------- UI ----
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 10)
        root.setSpacing(12)

        root.addWidget(self._build_source_card())
        root.addWidget(self._build_player_card(), 1)
        root.addWidget(self._build_render_card())
        root.addLayout(self._build_footer())

        self.setCentralWidget(central)
        self.statusBar().showMessage("Готов к работе")

    @staticmethod
    def _card() -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        return card

    @staticmethod
    def _ghost(text: str, slot=None, tooltip: str = "") -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("ghost")
        if tooltip:
            button.setToolTip(tooltip)
        if slot:
            button.clicked.connect(slot)
        return button

    @staticmethod
    def _label(text: str, kind: str = "hint") -> QLabel:
        label = QLabel(text)
        label.setObjectName(kind)
        return label

    def _build_footer(self) -> QHBoxLayout:
        """Журнал не мешает: лежит свёрнутым, разворачивается по кнопке."""
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        self.log_view.setFixedHeight(110)
        self.log_view.setVisible(False)

        self.log_btn = self._ghost("Журнал ▾", self._toggle_log,
                                   "Показать подробный лог операций")

        footer = QVBoxLayout()
        footer.setSpacing(6)
        footer.addWidget(self.log_view)
        row = QHBoxLayout()
        row.addWidget(self.log_btn)
        row.addStretch(1)
        footer.addLayout(row)

        wrapper = QHBoxLayout()
        wrapper.addLayout(footer)
        return wrapper

    def _toggle_log(self) -> None:
        visible = not self.log_view.isVisible()
        self.log_view.setVisible(visible)
        self.log_btn.setText("Журнал ▴" if visible else "Журнал ▾")

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("Программа")
        menu.addAction("Настройки…").triggered.connect(self.show_settings)
        if sys.platform == "darwin":
            # На macOS без этого разрешения не прочитать cookies Safari.
            menu.addAction("Доступ к cookies…").triggered.connect(self.open_privacy_settings)
        menu.addSeparator()
        check = menu.addAction("Проверить обновления")
        check.triggered.connect(lambda: self.check_updates(silent=False))

        self.autoupdate_action = menu.addAction("Проверять при запуске")
        self.autoupdate_action.setCheckable(True)
        self.autoupdate_action.setChecked(True)

        menu.addSeparator()
        about = menu.addAction("О программе")
        about.triggered.connect(self.show_about)

    def _build_shortcuts(self) -> None:
        """I и O — метки, пробел — пауза: руки не уходят с клавиатуры."""
        for keys, slot in (
            ("I", self.mark_in),
            ("O", self.mark_out),
            ("Space", self.toggle_play),
            ("Left", lambda: self.nudge(-1.0)),
            ("Right", lambda: self.nudge(1.0)),
            ("Shift+Left", lambda: self.nudge(-0.1)),   # точная подводка вместо кнопок
            ("Shift+Right", lambda: self.nudge(0.1)),
        ):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(slot)

    def _build_source_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.url_edit = QLineEdit()
        self.url_edit.setObjectName("url")
        self.url_edit.setPlaceholderText("Ссылка на видео или перетащите файл в окно")
        self.url_edit.returnPressed.connect(self.start_download)
        row.addWidget(self.url_edit, 1)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(list(downloader.QUALITY_FORMATS.keys()))
        self.quality_combo.setFixedWidth(150)
        self.quality_combo.setToolTip("Качество загрузки")
        row.addWidget(self.quality_combo)

        self.download_btn = QPushButton("Скачать")
        self.download_btn.setObjectName("primary")
        self.download_btn.setDefault(True)
        self.download_btn.clicked.connect(self.start_download)
        row.addWidget(self.download_btn)

        self.open_btn = self._ghost("Открыть файл", self.open_local_file)
        row.addWidget(self.open_btn)

        self.settings_btn = self._ghost("Настройки", self.show_settings,
                                        "Папка загрузок, cookies, прокси")
        row.addWidget(self.settings_btn)
        layout.addLayout(row)

        self.dl_progress = QProgressBar()
        self.dl_progress.setTextVisible(True)
        self.dl_progress.setFormat("Скачивание: %p%")
        self.dl_progress.setVisible(False)
        layout.addWidget(self.dl_progress)
        return card

    def _build_settings_dialog(self) -> QDialog:
        """Всё редко используемое живёт в отдельном окне, а не в главном."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Настройки")
        dialog.setMinimumWidth(520)
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(14)

        outer.addWidget(self._label("ЗАГРУЗКА", "section"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(10)

        grid.addWidget(self._label("Папка"), 0, 0)
        self.dir_edit = QLineEdit(str(default_download_dir()))
        grid.addWidget(self.dir_edit, 0, 1)
        grid.addWidget(self._ghost("Обзор", self.choose_dir), 0, 2)

        grid.addWidget(self._label("Cookies"), 1, 0)
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(BROWSERS)
        self.browser_combo.setToolTip(
            "«Авто» — программа сама возьмёт cookies из установленного браузера, "
            "если сайт потребует вход в аккаунт. Браузер при этом должен быть закрыт."
        )
        grid.addWidget(self.browser_combo, 1, 1)

        self.cookies_file: Path | None = None
        self.cookies_btn = self._ghost(
            "Файл cookies", self.choose_cookies_file,
            "Файл cookies.txt (формат Netscape) — запасной путь, когда браузер "
            "не отдаёт cookies напрямую. Экспортируется расширением вроде "
            "«Get cookies.txt LOCALLY».")
        grid.addWidget(self.cookies_btn, 1, 2)

        grid.addWidget(self._label("Прокси"), 2, 0)
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setPlaceholderText(
            "пусто — как в Windows; например socks5://127.0.0.1:10808")
        self.proxy_edit.setToolTip(
            "Некоторые сайты (TikTok, Instagram) не отдают видео на IP датацентров "
            "и VPN. Здесь можно направить скачивание через свой прокси."
        )
        grid.addWidget(self.proxy_edit, 2, 1, 1, 2)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid)

        outer.addWidget(self._label(
            "Настройки сохраняются автоматически и применяются к следующей загрузке."))

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Готово")
        close.setObjectName("primary")
        close.clicked.connect(dialog.accept)
        buttons.addWidget(close)
        outer.addLayout(buttons)
        return dialog

    def show_settings(self) -> None:
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _build_player_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(280)
        self.video_widget.setStyleSheet(VIDEO_IDLE_STYLE)
        layout.addWidget(self.video_widget, 1)

        # Живёт поверх области видео и исчезает, когда файл загружен.
        self.drop_hint = QLabel("Перетащите сюда видео или ссылку", self.video_widget)
        self.drop_hint.setAlignment(Qt.AlignCenter)
        self.drop_hint.setStyleSheet(
            f"color:{MUTED}; font-size:14px; background:transparent; border:none;")

        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_out)
        self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.errorOccurred.connect(
            lambda _e, msg: self.log(f"Проигрыватель: {msg}") if msg else None
        )

        # Перематывать на каждое движение мыши — рвано; копим и применяем по таймеру.
        self._seek_timer = QTimer(self)
        self._seek_timer.setInterval(45)
        self._seek_timer.timeout.connect(self._apply_pending_seek)

        # Выделение фрагмента живёт прямо на дорожке — отдельная панель не нужна.
        self.timeline = TimelineWidget()
        self.timeline.positionMoved.connect(self.player.setPosition)
        self.timeline.rangeChanged.connect(self._on_timeline_range)
        self.timeline.previewRequested.connect(self._on_preview_scrub)
        self.timeline.previewFinished.connect(self._on_preview_finished)
        layout.addWidget(self.timeline)

        layout.addLayout(self._build_controls())
        return card

    def _build_controls(self) -> QHBoxLayout:
        """Одна строка: воспроизведение, время, метки, предпросмотр, звук."""
        row = QHBoxLayout()
        row.setSpacing(8)

        self.play_btn = QPushButton()
        self.play_btn.setObjectName("round")
        self.play_btn.setFixedSize(34, 34)          # размер задаём кодом: в QSS
        self.play_btn.setIconSize(QSize(16, 16))    # min-width меряет контент
        self.play_btn.setIcon(_glyph_icon("play"))
        self.play_btn.setToolTip("Пробел — играть или пауза")
        self.play_btn.clicked.connect(self.toggle_play)
        row.addWidget(self.play_btn)

        self.time_label = self._label("0:00:00.000 / 0:00:00.000", "mono")
        row.addWidget(self.time_label)
        row.addSpacing(6)

        row.addWidget(self._ghost("Начало", self.mark_in,
                                  "Клавиша I — начало фрагмента по текущей позиции"))
        row.addWidget(self._ghost("Конец", self.mark_out,
                                  "Клавиша O — конец фрагмента по текущей позиции"))
        row.addWidget(self._ghost("Фрагмент", self.preview_clip,
                                  "Проиграть выделенный фрагмент"))
        row.addWidget(self._ghost("Сбросить", self.reset_range))

        row.addStretch(1)
        self.range_label = self._label("Фрагмент: —", "mono")
        row.addWidget(self.range_label)
        row.addSpacing(10)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setFixedWidth(90)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setToolTip("Громкость")
        self.volume_slider.valueChanged.connect(lambda v: self.audio_out.setVolume(v / 100))
        self.audio_out.setVolume(0.8)
        row.addWidget(self.volume_slider)
        return row

    def _build_render_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._label("H.264", "section"))
        row.addSpacing(8)

        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(14, 32)
        self.crf_spin.setValue(20)
        self.crf_spin.setPrefix("CRF ")
        self.crf_spin.setFixedWidth(100)
        self.crf_spin.setToolTip(
            "Меньше = лучше качество и больше файл. 18–23 — рабочий диапазон.")
        row.addWidget(self.crf_spin)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(PRESETS)
        self.preset_combo.setCurrentText("medium")
        self.preset_combo.setFixedWidth(124)
        self.preset_combo.setToolTip("Скорость кодирования (preset)")
        row.addWidget(self.preset_combo)

        self.res_combo = QComboBox()
        for label, _ in RESOLUTIONS:
            self.res_combo.addItem(label)
        self.res_combo.setFixedWidth(152)
        self.res_combo.setToolTip("Разрешение результата")
        row.addWidget(self.res_combo)

        self.fps_combo = QComboBox()
        for label, _ in FPS_CHOICES:
            self.fps_combo.addItem(label)
        self.fps_combo.setFixedWidth(140)
        self.fps_combo.setToolTip("Кадры в секунду")
        row.addWidget(self.fps_combo)

        self.copy_check = QCheckBox("Без перекодирования")
        self.copy_check.setToolTip(
            "Мгновенная нарезка копированием потока. Режет по ключевым кадрам, "
            "поэтому границы могут сместиться на пару секунд.")
        self.copy_check.toggled.connect(self._on_copy_toggled)
        row.addWidget(self.copy_check)

        row.addStretch(1)
        self.open_folder_btn = self._ghost("Папка", self.open_output_dir,
                                          "Открыть папку с результатом")
        row.addWidget(self.open_folder_btn)

        self.export_btn = QPushButton("Отрендерить фрагмент")
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self.start_export)
        row.addWidget(self.export_btn)
        layout.addLayout(row)

        self.export_progress = QProgressBar()
        self.export_progress.setFormat("Рендер: %p%")
        self.export_progress.setVisible(False)
        layout.addWidget(self.export_progress)
        return card

    # ----------------------------------------------------------- helpers ----
    def log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _duration_text(self) -> str:
        return format_tc(self.player.duration() / 1000) if self.player.duration() else "0:00:00.000"

    def _check_theme(self) -> None:
        if THEME_NOTE:
            self.log(THEME_NOTE)

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
        self.browser_combo.setCurrentText(
            self.settings.value("browser", downloader.BROWSER_AUTO, type=str)
        )
        self.autoupdate_action.setChecked(
            self.settings.value("autoupdate", True, type=bool)
        )
        self.proxy_edit.setText(self.settings.value("proxy", "", type=str))
        saved_cookies = self.settings.value("cookies_file", type=str)
        if saved_cookies and Path(saved_cookies).exists():
            self._set_cookies_file(Path(saved_cookies))

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        self.settings.setValue("download_dir", self.dir_edit.text())
        self.settings.setValue("quality", self.quality_combo.currentText())
        self.settings.setValue("crf", self.crf_spin.value())
        self.settings.setValue("preset", self.preset_combo.currentText())
        self.settings.setValue("browser", self.browser_combo.currentText())
        self.settings.setValue("proxy", self.proxy_edit.text().strip())
        self.settings.setValue("autoupdate", self.autoupdate_action.isChecked())
        self.settings.setValue(
            "cookies_file", str(self.cookies_file) if self.cookies_file else "")
        self.settings.sync()          # ini пишется отложенно — сбрасываем сразу
        for worker in (self.download_worker, self.export_worker, self.proxy_worker):
            if worker and worker.isRunning():
                worker.cancel()
                worker.wait(3000)
        super().closeEvent(event)

    # ---------------------------------------------------------- download ----
    def choose_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Папка для загрузок", self.dir_edit.text())
        if chosen:
            self.dir_edit.setText(chosen)

    def _set_cookies_file(self, path: Path | None) -> None:
        self.cookies_file = path
        self.cookies_btn.setText(f"Cookies: {path.name}" if path else "Файл cookies")

    def choose_cookies_file(self) -> None:
        if self.cookies_file:
            # Повторный клик по выбранному файлу — сбрасываем.
            self._set_cookies_file(None)
            self.log("Файл cookies отключён.")
            return
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Файл cookies (Netscape cookies.txt)", "", "cookies.txt (*.txt);;Все файлы (*)"
        )
        if chosen:
            self._set_cookies_file(Path(chosen))
            self.log(f"Использую cookies из {chosen}")

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
        browser = None if browser == "Не использовать" else browser

        self.dl_progress.setValue(0)
        self.dl_progress.setVisible(True)
        self.download_btn.setText("Отменить")
        self.statusBar().showMessage("Скачиваю…")
        self.log(f"Скачиваю {url}")

        worker = DownloadWorker(
            url, out_dir, self.quality_combo.currentText(), browser, self.cookies_file,
            self.proxy_edit.text().strip() or None,
        )
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
        self.dl_progress.setVisible(False)
        self.log(f"Готово: {result.path}")
        if result.cookies_source:
            self.log(f"Сработали cookies: {result.cookies_source}")
        self.statusBar().showMessage(f"Скачано: {result.title}")
        self.load_media(result.path)

    def _on_download_failed(self, message: str) -> None:
        self.dl_progress.setVisible(False)
        self.statusBar().showMessage("Ошибка скачивания")
        self.log(f"Ошибка: {message}")
        QMessageBox.critical(self, APP_NAME, f"Не удалось скачать видео:{chr(10)}{chr(10)}{message}")

    def open_local_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите видео", self.dir_edit.text(),
            "Видео (*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.flv);;Все файлы (*.*)",
        )
        if path:
            self.load_media(Path(path))

    # ---------------------------------------------------------- drag & drop --
    def _dropped_items(self, mime) -> tuple:
        """Из перетащенного берём локальные видеофайлы и ссылки."""
        files, links = [], []
        for url in mime.urls() if mime.hasUrls() else ():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.suffix.lower() in VIDEO_SUFFIXES and path.is_file():
                    files.append(path)
            elif url.scheme() in ("http", "https"):
                links.append(url.toString())
        if not files and not links and mime.hasText():
            found = downloader.find_url(mime.text())
            if found:
                links.append(found)
        return files, links

    def _highlight_drop(self, active: bool) -> None:
        if active:
            style = VIDEO_DROP_STYLE
        else:
            style = VIDEO_ACTIVE_STYLE if self.source else VIDEO_IDLE_STYLE
        self.video_widget.setStyleSheet(style)
        if active:
            self.drop_hint.setText("Отпустите — откроется в плеере")
            self.drop_hint.setVisible(True)
        else:
            self.drop_hint.setText("Перетащите сюда видео или ссылку")
            self.drop_hint.setVisible(self.source is None)

    def dragEnterEvent(self, event) -> None:
        files, links = self._dropped_items(event.mimeData())
        if files or links:
            event.acceptProposedAction()
            self._highlight_drop(True)

    def dragMoveEvent(self, event) -> None:
        if self._dropped_items(event.mimeData()) != ([], []):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: ARG002
        self._highlight_drop(False)

    def dropEvent(self, event) -> None:
        files, links = self._dropped_items(event.mimeData())
        self._highlight_drop(False)
        if files:
            event.acceptProposedAction()
            if len(files) > 1:
                self.log(f"Перетащено файлов: {len(files)} — открываю первый.")
            self.log(f"Открываю {files[0].name}")
            self.load_media(files[0])
        elif links:
            event.acceptProposedAction()
            self.url_edit.setText(links[0])
            self.start_download()

    # -------------------------------------------------------------- media ---
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_drop_hint()

    def _place_drop_hint(self) -> None:
        self.drop_hint.setGeometry(0, 0, self.video_widget.width(),
                                   self.video_widget.height())

    def load_media(self, path: Path) -> None:
        self.source = path
        self.drop_hint.setVisible(False)
        self.video_widget.setStyleSheet(VIDEO_ACTIVE_STYLE)
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
        self._stop_proxy()
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        if ffmpeg_tools.needs_preview_proxy(self.info):
            self._start_preview_proxy(path)
        duration_ms = int((self.info.duration if self.info else 0) * 1000)
        self.timeline.set_duration(duration_ms)
        self.timeline.set_range(0, duration_ms)
        self._update_range_label()
        self.setWindowTitle(f"{APP_NAME} — {path.name}")
        QTimer.singleShot(200, self.player.play)
        QTimer.singleShot(400, self.player.pause)


    # ------------------------------------------------------ preview proxy ---
    def _stop_proxy(self) -> None:
        if self.proxy_worker and self.proxy_worker.isRunning():
            self.proxy_worker.cancel()
            self.proxy_worker.wait(2000)
        self.proxy_worker = None

    def _start_preview_proxy(self, path: Path) -> None:
        """Плеер Windows не тянет AV1/VP9/Opus — смотрим лёгкую H.264-копию."""
        codecs = f"{self.info.vcodec}/{self.info.acodec}" if self.info else "?"
        self.log(f"Кодек {codecs} встроенный плеер не воспроизводит — готовлю превью…")
        self.statusBar().showMessage("Готовлю превью для просмотра…")
        target = Path(tempfile.gettempdir()) / "clipper_preview" / f"{path.stem}.preview.mp4"
        if target.exists() and target.stat().st_mtime >= path.stat().st_mtime:
            self.log("Превью уже готово, беру из кэша.")
            self._use_preview(target)
            return
        worker = PreviewProxyWorker(path, target)
        worker.progress.connect(
            lambda p: self.statusBar().showMessage(f"Готовлю превью… {p:.0f}%"))
        worker.finished_ok.connect(self._use_preview)
        worker.failed.connect(self._on_proxy_failed)
        self.proxy_worker = worker
        worker.start()

    def _use_preview(self, path: Path) -> None:
        position = self.player.position()
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        QTimer.singleShot(300, lambda: self.player.setPosition(position))
        self.log(f"Превью готово: {path.name} (обрезка и рендер идут из оригинала)")
        self.statusBar().showMessage("Превью готово — оригинал для рендера сохранён")

    def _on_proxy_failed(self, message: str) -> None:
        self.log(f"Превью не получилось: {message}")
        self.statusBar().showMessage("Не удалось подготовить превью")

    def toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_btn.setIcon(_glyph_icon("play"))
            return
        start, end = self.timeline.range()
        # Плей всегда играет выделенное: если позиция вне фрагмента (или мы
        # уже упёрлись в его конец) — начинаем с начала фрагмента.
        if end > start and not (start <= self.player.position() < end - 40):
            self.player.setPosition(start)
        self.player.play()
        self.play_btn.setIcon(_glyph_icon("pause"))

    def seek(self, seconds: float) -> None:
        self.player.setPosition(int(max(0.0, seconds) * 1000))

    def _on_position_changed(self, ms: int) -> None:
        if not self.timeline.is_dragging():
            self.timeline.set_position(ms)
        self.time_label.setText(f"{format_tc(ms / 1000)} / {self._duration_text()}")
        self._stop_at_fragment_end(ms)

    def _stop_at_fragment_end(self, ms: int) -> None:
        """Дошли до конца выделения — останавливаемся, дальше не играем."""
        if self.player.playbackState() != QMediaPlayer.PlayingState:
            return
        start, end = self.timeline.range()
        if end > start and ms >= end:
            self.player.pause()
            self.player.setPosition(end)
            self.play_btn.setIcon(_glyph_icon("play"))

    def _on_duration_changed(self, ms: int) -> None:
        self.timeline.set_duration(ms)
        start, end = self.timeline.range()
        if ms and end <= start:
            self.timeline.set_range(0, ms)
        self._update_range_label()


    def _on_preview_scrub(self, ms: int) -> None:
        """Метку тянут — показываем кадр под ней, не теряя позицию плеера."""
        if self._preview_return is None:
            self._preview_return = self.player.position()
            self._preview_was_playing = (
                self.player.playbackState() == QMediaPlayer.PlayingState
            )
            if self._preview_was_playing:
                self.player.pause()
        self._pending_seek = ms
        if not self._seek_timer.isActive():
            self._apply_pending_seek()      # первый кадр — сразу, без задержки
            self._seek_timer.start()

    def _apply_pending_seek(self) -> None:
        if self._pending_seek is None:
            self._seek_timer.stop()
            return
        self.player.setPosition(self._pending_seek)
        self._pending_seek = None

    def _on_preview_finished(self) -> None:
        """Метку отпустили — возвращаемся туда, где стоит плеер."""
        self._seek_timer.stop()
        self._pending_seek = None
        if self._preview_return is None:
            return
        self.player.setPosition(self._preview_return)
        if self._preview_was_playing:
            self.player.play()
            self.play_btn.setIcon(_glyph_icon("pause"))
        self._preview_return = None
        self.timeline.set_position(self.player.position())

    def _on_timeline_range(self, in_ms: int, out_ms: int) -> None:
        self._update_range_label()

    # --------------------------------------------------------------- trim ---
    def _current_seconds(self) -> float:
        return self.player.position() / 1000

    def mark_in(self) -> None:
        start, end = self.timeline.range()
        pos = self.player.position()
        # Начало «перепрыгнуло» конец — растягиваем фрагмент до конца ролика.
        self.timeline.set_range(pos, end if end > pos else self.timeline.duration())
        self._update_range_label()

    def mark_out(self) -> None:
        start, _ = self.timeline.range()
        pos = self.player.position()
        self.timeline.set_range(start if start < pos else 0, pos)
        self._update_range_label()

    def nudge(self, delta: float) -> None:
        self.seek(max(0.0, self._current_seconds() + delta))

    def reset_range(self) -> None:
        self.timeline.set_range(0, self.timeline.duration())
        self._update_range_label()

    def preview_clip(self) -> None:
        """Проиграть фрагмент с начала. Остановится сам — границы стережёт плеер."""
        start, end = self.trim_range()
        if end <= start:
            return
        self.seek(start)
        self.player.play()
        self.play_btn.setIcon(_glyph_icon("pause"))

    def _media_duration(self) -> float:
        if self.player.duration():
            return self.player.duration() / 1000
        return self.info.duration if self.info else 0.0

    def trim_range(self) -> tuple[float, float]:
        in_ms, out_ms = self.timeline.range()
        start, end = in_ms / 1000, out_ms / 1000
        duration = self._media_duration()
        if duration:
            start = min(start, duration)
            end = min(end, duration) if end else duration
        return start, end

    def _update_range_label(self) -> None:
        start, end = self.trim_range()
        length = max(0.0, end - start)
        self.range_label.setText(
            f"Фрагмент: {format_tc(start)} → {format_tc(end)}   ({length:.3f} с)"
            if length else "Фрагмент: —"
        )


    # ------------------------------------------------------------ update ----
    def check_updates(self, silent: bool = False) -> None:
        """silent=True — проверка при запуске: молчим, если всё актуально."""
        if self.update_worker and self.update_worker.isRunning():
            return
        self._update_silent = silent
        if not silent:
            self.statusBar().showMessage("Проверяю обновления…")
        worker = UpdateCheckWorker()
        worker.result.connect(self._on_update_checked)
        worker.failed.connect(self._on_update_check_failed)
        self.update_worker = worker
        worker.start()

    def _on_update_check_failed(self, message: str) -> None:
        self.log(f"Проверка обновлений: {message}")
        if not self._update_silent:
            QMessageBox.warning(self, APP_NAME, message)

    def _on_update_checked(self, release) -> None:
        if release is None:
            self.log("Обновления: релизов на GitHub пока нет.")
            if not self._update_silent:
                QMessageBox.information(
                    self, APP_NAME,
                    "На GitHub ещё нет опубликованных релизов — обновляться не с чего.",
                )
            return

        if not updater.is_newer(release):
            self.log(f"Обновления: установлена последняя версия {__version__}.")
            if not self._update_silent:
                QMessageBox.information(
                    self, APP_NAME, f"У вас последняя версия — {__version__}.")
            return

        notes = release.notes[:600] + ("…" if len(release.notes) > 600 else "")
        head = f"""Доступна версия {release.name} (у вас {__version__}).

{notes}"""
        if not updater.can_self_update():
            # Из исходников подменять нечего — ведём в релизы.
            QMessageBox.information(self, APP_NAME, head + """

""" + updater.source_hint())
            return
        if QMessageBox.question(self, APP_NAME, head + """

Обновить сейчас?""") != QMessageBox.Yes:
            return
        self._start_update_download(release)

    def _start_update_download(self, release) -> None:
        self.log(f"Качаю обновление {release.name}…")
        self.dl_progress.setFormat("Обновление: %p%")
        self.dl_progress.setValue(0)
        self.dl_progress.setVisible(True)
        worker = UpdateDownloadWorker(release)
        worker.progress.connect(lambda p: self.dl_progress.setValue(int(p)))
        worker.finished_ok.connect(lambda path: self._on_update_downloaded(path, release))
        worker.failed.connect(self._on_update_failed)
        self.update_dl_worker = worker
        worker.start()

    def _reset_dl_progress(self) -> None:
        self.dl_progress.setVisible(False)
        self.dl_progress.setFormat("Скачивание: %p%")

    def _on_update_failed(self, message: str) -> None:
        self._reset_dl_progress()
        self.log(f"Обновление не удалось: {message}")
        QMessageBox.warning(self, APP_NAME, f"Обновление не удалось: {message}")

    def _on_update_downloaded(self, staged, release) -> None:
        self._reset_dl_progress()
        try:
            updater.apply_update(staged)
        except Exception as exc:  # noqa: BLE001
            self._on_update_failed(f"не удалось заменить программу: {exc}")
            return
        self.log(f"Обновление {release.name} установлено.")
        answer = QMessageBox.question(
            self, APP_NAME,
            f"Версия {release.name} установлена. Перезапустить сейчас?",
        )
        if answer == QMessageBox.Yes:
            updater.restart()
            self.close()

    def open_privacy_settings(self) -> None:
        """Открывает раздел «Полный доступ к диску» в настройках macOS."""
        QDesktopServices.openUrl(QUrl(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"))
        self.log("Добавьте Clipper в «Полный доступ к диску» и перезапустите программу.")

    def show_about(self) -> None:
        QMessageBox.information(self, APP_NAME, f"""{APP_NAME} {__version__}

Скачивание видео по ссылке, обрезка фрагмента и рендер в H.264.
Исходники и релизы: {updater.RELEASES_URL}""")

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
        self.export_progress.setVisible(True)
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


THEME_NOTE = ""


def _selftest(report_path: str) -> int:
    """Clipper.exe --selftest file.txt — что нашлось внутри сборки.

    Окно приложения без консоли, поэтому пишем результат в файл.
    """
    lines = [f"Clipper {__version__}", f"frozen: {updater.is_frozen()}",
             f"платформа: {sys.platform}",
             f"портативный режим: {storage.is_portable()}",
             f"каталог программы: {storage.app_dir()}",
             f"данные: {storage.data_dir()}",
             f"загрузки по умолчанию: {storage.default_download_dir()}",
             f"самообновление: {updater.can_self_update()} (ассет {updater.asset_name()})"]
    lines.append(f"ffmpeg: {ffmpeg_tools.ffmpeg_path()}")
    lines.append(f"JS-рантаймы: {downloader.js_runtimes()}")
    lines.append(f"PO-токены: {downloader.pot_binary()}")
    # Именно файл, а не импорт: импорт зарегистрировал бы провайдер второй раз.
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    plugin = root / "yt_dlp_plugins" / "extractor" / "yt_dlp_get_pot_rustypipe.py"
    lines.append(f"плагин PO-токенов: {'найден' if plugin.exists() else 'НЕ найден'} ({plugin})")
    try:
        import certifi
        ca = Path(certifi.where())
        lines.append(f"сертификаты: {ca} (есть: {ca.exists()})")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"сертификаты: НЕ найдены — {exc}")
    try:
        release = updater.check()
        lines.append(f"связь с GitHub: ок, последний релиз "
                     f"{release.tag if release else 'не опубликован'}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"связь с GitHub: ОШИБКА — {str(exc)[:160]}")
    try:
        import yt_dlp_ejs
        lines.append(f"yt_dlp_ejs: {yt_dlp_ejs.version}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"yt_dlp_ejs: НЕ найден — {exc}")
    if "--download" in sys.argv:
        # Полная проверка боевого пути прямо внутри сборки.
        url = sys.argv[sys.argv.index("--download") + 1]
        import tempfile
        try:
            result = downloader.download(
                url, Path(tempfile.gettempdir()) / "clipper_selftest",
                quality="480p", on_log=lambda m: lines.append(f"  {m[:110]}"),
            )
            size = result.path.stat().st_size / 1024 / 1024
            lines.append(f"скачивание: OK — {result.title} ({size:.1f} МБ)")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"скачивание: ОШИБКА — {exc}")
    Path(report_path).write_text(chr(10).join(lines), encoding="utf-8")
    return 0


def _apply_theme(app: QApplication) -> None:
    """Тёмная база qdarktheme плюс наш минималистичный слой поверх."""
    global THEME_NOTE
    try:
        import qdarktheme
    except ImportError:
        THEME_NOTE = "Тема qdarktheme не найдена — интерфейс в системном оформлении."
    else:
        qdarktheme.setup_theme("dark", corner_shape="rounded",
                               custom_colors={"primary": ACCENT})
        THEME_NOTE = "Тема: qdarktheme (тёмная)"
    app.setStyleSheet(app.styleSheet() + QSS)


def _ensure_writable_cwd() -> None:
    """У .app рабочий каталог — корень тома, а туда писать нельзя."""
    try:
        current = Path.cwd()
    except OSError:
        current = None
    if current is None or not os.access(current, os.W_OK):
        fallback = storage.data_dir()
        fallback.mkdir(parents=True, exist_ok=True)
        os.chdir(fallback)


def main() -> int:
    _ensure_writable_cwd()
    if "--selftest" in sys.argv:
        index = sys.argv.index("--selftest")
        target = sys.argv[index + 1] if len(sys.argv) > index + 1 else "clipper-selftest.txt"
        return _selftest(target)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    _apply_theme(app)
    icon_path = Path(__file__).resolve().parent.parent / "assets" / "clipper.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
