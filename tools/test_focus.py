"""Фокус после ввода ссылки: клавиши должны работать без клика по окну."""
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import clipper.app as app_mod

app = QApplication(sys.argv)
app_mod._apply_theme(app)
win = app_mod.MainWindow()
win.show()
QTest.qWaitForWindowExposed(win)
win.activateWindow()

videos = glob.glob(os.path.join(os.environ["TEMP"], "clipper_*", "*.mp4"))
if not videos:
    print("нет тестового видео — пропускаю")
    sys.exit(0)


def press(key, mods=Qt.NoModifier):
    target = QApplication.focusWidget() or win
    app.sendEvent(target, QKeyEvent(QEvent.KeyPress, key, mods))
    QTest.qWait(150)


# 1. пока пишем ссылку — клавиши принадлежат тексту
win.url_edit.setFocus()
win.url_edit.setText("https://vimeo.com/22439234")
QTest.qWait(200)
print("1) фокус во время ввода:", type(QApplication.focusWidget()).__name__)
assert QApplication.focusWidget() is win.url_edit

# 2. видео открылось — фокус должен уйти на дорожку
win.load_media(Path(videos[0]))
QTest.qWait(2500)
focused = QApplication.focusWidget()
print("2) фокус после загрузки:", type(focused).__name__)
assert focused is win.timeline, f"фокус остался на {type(focused).__name__}"

# 3. клавиши работают сразу, без клика по окну
dur = win.timeline.duration()
win.timeline.set_range(0, dur)
win.player.setPosition(int(dur * 0.4))
QTest.qWait(700)
press(Qt.Key_I)
in_ms, _ = win.timeline.range()
print(f"3) после I: начало {in_ms} мс")
assert in_ms > 0, "клавиша I не сработала — фокус не там"

press(Qt.Key_Space)
QTest.qWait(400)
playing = win.player.playbackState().name
print("   после пробела состояние плеера:", playing)
win.player.pause()

# 4. текст в поле ссылки не пострадал
print("4) в поле ссылки:", win.url_edit.text())
assert "vimeo.com" in win.url_edit.text(), "ссылка потерялась"

print("OK: после загрузки фокус на дорожке, клавиши работают, ссылка на месте")
QTimer.singleShot(100, app.quit)
app.exec()
