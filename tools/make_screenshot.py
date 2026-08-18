"""Скриншот для README: окно с загруженным видео.

Запуск: python tools/make_screenshot.py assets/screenshot.png

QVideoWidget не попадает в grab(), поэтому кадр рисуем сами и вставляем
в область плеера. Рисованный кадр вместо настоящего — чтобы не тащить
в репозиторий чужой видеоряд.
"""
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, r"D:\#WORK\01.PLUGINS . Programs\Clipper")

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication
import clipper.app as app_mod


def video_frame(width: int, height: int) -> QPixmap:
    """Стилизованный кадр: закат над горами."""
    pixmap = QPixmap(width, height)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    sky = QLinearGradient(0, 0, 0, height)
    sky.setColorAt(0.0, QColor("#1b2340"))
    sky.setColorAt(0.45, QColor("#4a3a63"))
    sky.setColorAt(0.72, QColor("#c2643f"))
    sky.setColorAt(1.0, QColor("#f0a15c"))
    painter.fillRect(0, 0, width, height, sky)

    # Солнце у линии гор.
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 214, 150, 235))
    sun_r = height * 0.11
    painter.drawEllipse(QPointF(width * 0.62, height * 0.63), sun_r, sun_r)

    # Три плана гор: чем дальше, тем светлее и мягче.
    layers = (
        (0.70, "#3a3550", 1.00),
        (0.78, "#272238", 0.72),
        (0.88, "#16121f", 0.48),
    )
    for base, color, scale in layers:
        path = QPainterPath()
        path.moveTo(0, height)
        path.lineTo(0, height * base)
        peaks = ((0.10, 0.10), (0.22, 0.04), (0.38, 0.13), (0.52, 0.05),
                 (0.68, 0.12), (0.82, 0.03), (0.94, 0.10), (1.00, 0.06))
        for x, up in peaks:
            path.lineTo(width * x, height * (base - up * scale))
        path.lineTo(width, height)
        path.closeSubpath()
        painter.setBrush(QColor(color))
        painter.drawPath(path)

    # Дымка над дальним планом — кадр перестаёт выглядеть аппликацией.
    haze = QLinearGradient(0, height * 0.62, 0, height * 0.80)
    haze.setColorAt(0.0, QColor(255, 180, 130, 60))
    haze.setColorAt(1.0, QColor(255, 180, 130, 0))
    painter.fillRect(QRectF(0, height * 0.62, width, height * 0.18), haze)

    painter.end()
    return pixmap


app = QApplication(sys.argv)
app_mod._apply_theme(app)
win = app_mod.MainWindow()
win.resize(1180, 820)
win.show()

videos = glob.glob(os.path.join(os.environ["TEMP"], "clipper_*", "*.mp4"))
target = Path(sys.argv[1])


def load():
    if videos:
        win.load_media(Path(videos[0]))
    QTimer.singleShot(2500, mark)


def mark():
    duration = win.timeline.duration() or 185877
    win.timeline.set_duration(duration)
    win.timeline.set_range(int(duration * 0.25), int(duration * 0.70))
    win.timeline.set_position(int(duration * 0.42))
    win._update_range_label()
    win.time_label.setText("00:01:18.500 / 00:03:05.877")
    win.log("Скачано: Sunset Timelapse — 1920x1080, 30.00 к/с")
    QTimer.singleShot(400, shoot)


def shoot():
    shot = win.grab()
    area = win.video_widget
    top_left = area.mapTo(win, area.rect().topLeft())
    rect = QRectF(top_left.x(), top_left.y(), area.width(), area.height())

    frame = video_frame(int(rect.width()), int(rect.height()))
    painter = QPainter(shot)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(rect, 12, 12)      # скругление как у самой области
    painter.setClipPath(path)
    painter.drawPixmap(rect.topLeft(), frame)
    painter.end()

    shot.save(str(target))
    print("снимок:", target)
    app.quit()


QTimer.singleShot(1200, load)
app.exec()
