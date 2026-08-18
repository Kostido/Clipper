"""Английский интерфейс: собираем окно и проверяем, что русского текста
на видимых элементах не осталось.

Запуск: python tools/test_i18n.py
"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\#WORK\01.PLUGINS . Programs\Clipper")

import os

os.environ["CLIPPER_LANG"] = "en"             # до импорта интерфейса

from PySide6.QtTest import QTest              # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QLabel,  # noqa: E402
                               QLineEdit, QPushButton)
import clipper.i18n as i18n                   # noqa: E402

assert i18n.LANG == "en", f"язык определился как {i18n.LANG}"

import clipper.app as app_mod                 # noqa: E402

app = QApplication(sys.argv)
app_mod._apply_theme(app)
win = app_mod.MainWindow()
win.resize(1180, 820)
win.show()
QTest.qWaitForWindowExposed(win)

CYRILLIC = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")


def has_russian(text: str) -> bool:
    return any(ch in CYRILLIC for ch in text or "")


leftovers = []
for widget_type in (QPushButton, QLabel, QCheckBox):
    for widget in win.findChildren(widget_type):
        if has_russian(widget.text()):
            leftovers.append(f"{widget_type.__name__}: {widget.text()!r}")
for widget in win.findChildren(QLineEdit):
    if has_russian(widget.placeholderText()):
        leftovers.append(f"placeholder: {widget.placeholderText()!r}")
for widget in win.findChildren(QComboBox):
    for index in range(widget.count()):
        if has_russian(widget.itemText(index)):
            leftovers.append(f"combo: {widget.itemText(index)!r}")
for action in win.menuBar().actions():
    if has_russian(action.text()):
        leftovers.append(f"menu: {action.text()!r}")
    for sub in (action.menu().actions() if action.menu() else ()):
        if has_russian(sub.text()):
            leftovers.append(f"menu item: {sub.text()!r}")

print("заголовок окна:", win.windowTitle())
print("кнопка загрузки:", win.download_btn.text(), "| рендер:", win.export_btn.text())
print("метки:", win.range_label.text(), "|", win.play_btn.toolTip())
print("качество:", [win.quality_combo.itemText(i) for i in range(win.quality_combo.count())])
print("битрейт:", [win.bitrate_combo.itemText(i) for i in range(3)])

if leftovers:
    print("НЕ ПЕРЕВЕДЕНО:")
    for item in leftovers:
        print("  ", item)
    sys.exit(1)
print("OK: русского текста в интерфейсе не осталось")
