"""Перемотка должна идти по самому видео — и по дорожке, и при тяге меток.

Раскадровки больше нет: в плеере всегда оригинал (или перекодированное превью
для неиграбельных кодеков), поэтому проверяем, что плеер реально отрабатывает
позиции во время протяжки, а не догоняет их после отпускания.
"""
import glob
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import clipper.app as app_mod

TEMP = os.environ.get("TEMP") or tempfile.gettempdir()

app = QApplication(sys.argv)
app_mod._apply_theme(app)
win = app_mod.MainWindow()
win.resize(1180, 860)
win.show()
QTest.qWaitForWindowExposed(win)

videos = glob.glob(os.path.join(TEMP, "clipper_*", "*.mp4"))
if not videos:
    print("нет тестового видео — пропускаю")
    sys.exit(0)
win.load_media(Path(videos[0]))

waited = 0
while waited < 30_000 and not win.timeline.duration():
    QTest.qWait(200)
    waited += 200
dur = win.timeline.duration()
assert dur, "плеер не сообщил длительность"
print(f"1) видео открыто за ~{waited/1000:.1f} с, длительность {dur} мс")

# Тест про перемотку, а не про воспроизведение: играющий плеер уехал бы
# с места отпускания за время проверки.
win.player.pause()
QTest.qWait(200)

seen = []
win.player.positionChanged.connect(lambda ms: seen.append(ms))
timeline = win.timeline
y = timeline.height() // 2
x_of = lambda ms: QPoint(int(timeline._x_of(ms)), y)  # noqa: E731

# Сдвигаем метки к началу, чтобы протяжка дорожки не цепляла их.
timeline.set_range(0, int(dur * 0.3))
QTest.qWait(150)

# --- протяжка позиции по дорожке ---------------------------------------
seen.clear()
QTest.mousePress(timeline, Qt.LeftButton, Qt.NoModifier, x_of(int(dur * 0.5)))
for part in (0.6, 0.7, 0.8, 0.9):
    QTest.mouseMove(timeline, x_of(int(dur * part)))
    QTest.qWait(120)
QTest.mouseRelease(timeline, Qt.LeftButton, Qt.NoModifier, x_of(int(dur * 0.9)))
QTest.qWait(600)
during = len(set(seen))
print(f"2) во время протяжки плеер отработал позиций: {during}")
assert during >= 3, "видео не перематывается, пока тянут дорожку"
target = int(dur * 0.9)
print(f"3) после отпускания: {win.player.position()} мс (цель ~{target})")
assert abs(win.player.position() - target) < 400, "плеер не доехал до места отпускания"

# --- протяжка метки ----------------------------------------------------
before = win.player.position()
seen.clear()
QTest.mousePress(timeline, Qt.LeftButton, Qt.NoModifier, x_of(int(dur * 0.3)))
for part in (0.4, 0.5, 0.6):
    QTest.mouseMove(timeline, x_of(int(dur * part)))
    QTest.qWait(120)
QTest.mouseRelease(timeline, Qt.LeftButton, Qt.NoModifier, x_of(int(dur * 0.6)))
QTest.qWait(600)
print(f"4) при тяге метки плеер отработал позиций: {len(set(seen))}, "
      f"конец фрагмента: {timeline.range()[1]} мс")
assert len(set(seen)) >= 3, "видео не перематывается, пока тянут метку"
assert abs(timeline.range()[1] - int(dur * 0.6)) < 400, "метка не встала на место"
assert abs(win.player.position() - before) < 400, "позиция плеера не вернулась после метки"

print("OK: перематывается само видео — и по дорожке, и при тяге меток")
win.close()
