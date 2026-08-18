"""Собирает assets/clipper.icns из нарисованной иконки (только macOS).

Запуск: python tools/make_icns.py
Использует iconutil, который входит в состав Xcode Command Line Tools.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
# Пары «размер в точках, масштаб» по требованиям Apple.
VARIANTS = ((16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
            (256, 1), (256, 2), (512, 1), (512, 2))


def main() -> int:
    if sys.platform != "darwin":
        print("iconutil есть только в macOS — .icns собирается там.")
        return 0
    if not shutil.which("iconutil"):
        print("Не найден iconutil (Xcode Command Line Tools).")
        return 1

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from make_icon import draw                     # рисуем той же функцией

    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)                   # QPainter требует приложения

    iconset = ASSETS / "clipper.iconset"
    shutil.rmtree(iconset, ignore_errors=True)
    iconset.mkdir(parents=True)

    for size, scale in VARIANTS:
        pixels = size * scale
        suffix = "" if scale == 1 else "@2x"
        name = f"icon_{size}x{size}{suffix}.png"
        draw(pixels).save(str(iconset / name))

    target = ASSETS / "clipper.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(target)],
                   check=True)
    shutil.rmtree(iconset, ignore_errors=True)
    print(f"  {target}")
    del app
    return 0


if __name__ == "__main__":
    main()
    import os
    os._exit(0)
