"""Рисует иконку Clipper: скруглённый квадрат, кадр плёнки и метки обрезки.

Запуск: python tools/make_icon.py
Результат: assets/clipper.ico (16–256 px) и assets/clipper.png (512 px).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter,
                           QPainterPath)
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256)

BG_TOP = QColor("#5b9dff")
BG_BOTTOM = QColor("#2f6ae0")
MARK = QColor("#ffffff")


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    s = size / 100.0                      # рисуем в координатах 100x100

    # Подложка — скруглённый квадрат с вертикальным градиентом.
    gradient = QLinearGradient(0, 0, 0, size)
    gradient.setColorAt(0.0, BG_TOP)
    gradient.setColorAt(1.0, BG_BOTTOM)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawRoundedRect(QRectF(6 * s, 6 * s, 88 * s, 88 * s), 24 * s, 24 * s)

    # Треугольник воспроизведения — основной смысл: это про видео.
    play = QPainterPath()
    play.moveTo(QPointF(42 * s, 35 * s))
    play.lineTo(QPointF(42 * s, 65 * s))
    play.lineTo(QPointF(65 * s, 50 * s))
    play.closeSubpath()
    painter.setBrush(MARK)
    painter.drawPath(play)

    # Две метки обрезки по краям — то, чем приложение и занимается.
    # Без засечек и деталей: на 16 px должен читаться силуэт, а не рисунок.
    painter.setBrush(MARK)
    for x in (28, 72):
        painter.drawRoundedRect(
            QRectF((x - 2.5) * s, 30 * s, 5 * s, 40 * s), 2.5 * s, 2.5 * s)

    painter.end()
    return image


def main() -> int:
    app = QApplication(sys.argv)          # QImage/QPainter требуют приложения
    ASSETS.mkdir(parents=True, exist_ok=True)

    large = draw(512)
    png = ASSETS / "clipper.png"
    large.save(str(png))
    print(f"  {png}")

    frames = [draw(size) for size in SIZES]
    ico = ASSETS / "clipper.ico"
    _write_ico(frames, ico)
    print(f"  {ico} ({', '.join(str(s) for s in SIZES)} px)")
    return 0


def _write_ico(images: list, target: Path) -> None:
    """Собираем .ico вручную: каждый кадр — PNG внутри контейнера."""
    import struct
    from PySide6.QtCore import QBuffer, QByteArray

    payloads = []
    for image in images:
        # Ссылку на QByteArray держим в переменной: без неё Python освобождает
        # массив, пока QBuffer им ещё пользуется, и процесс падает.
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QBuffer.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        payloads.append(bytes(data))

    header = struct.pack("<HHH", 0, 1, len(payloads))
    offset = len(header) + 16 * len(payloads)
    entries, blobs = b"", b""
    for image, payload in zip(images, payloads):
        side = 0 if image.width() >= 256 else image.width()
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32,
                               len(payload), offset)
        blobs += payload
        offset += len(payload)
    target.write_bytes(header + entries + blobs)


if __name__ == "__main__":
    main()
    # Выходим без разрушения QApplication: на Windows это иногда падает.
    import os
    os._exit(0)
