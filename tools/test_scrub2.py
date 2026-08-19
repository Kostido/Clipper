"""Превью должно откликаться и при перетаскивании позиции, и при тяге меток."""
import glob
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import clipper.app as app_mod

app = QApplication(sys.argv)
app_mod._apply_theme(app)
win = app_mod.MainWindow()
win.show()
QTest.qWaitForWindowExposed(win)

videos = glob.glob(os.path.join(os.environ["TEMP"], "clipper_*", "*.mp4"))
if not videos:
    print("нет тестового видео — пропускаю")
    sys.exit(0)
win.load_media(Path(videos[0]))
QTest.qWait(2500)

waited = 0
while waited < 60_000 and not win.thumbnails:
    QTest.qWait(300)
    waited += 300
print(f"1) раскадровка готова за ~{waited/1000:.1f} с, кадров: {len(win.thumbnails)}")
assert win.thumbnails

dur = win.timeline.duration()
timeline = win.timeline

# 2. тянем позицию по дорожке — кадр меняется, плеер не трогаем
start_pos = win.player.position()
timeline._drag = "scrub"
seen = []
t0 = time.perf_counter()
for fraction in (0.2, 0.4, 0.6, 0.8):
    timeline._apply_drag(timeline._x_of(int(dur * fraction)))
    QTest.qWait(60)
    pix = win.scrub_view.pixmap()
    seen.append(pix.cacheKey() if pix else None)
elapsed = (time.perf_counter() - t0) * 1000
print(f"2) 4 кадра за {elapsed:.0f} мс, различных: {len(set(seen))}, "
      f"плеер стоит на месте: {win.player.position() == start_pos}")
assert len(set(seen)) == 4, "кадр не менялся при перетаскивании позиции"
assert win.scrub_view.isVisible(), "кадр не показан"

# 3. отпустили — плеер доходит до выбранной позиции, кадр убирается
timeline.mouseReleaseEvent(type("E", (), {"button": lambda self=None: None})())
timeline._drag = None
win._on_scrub_finished()
QTest.qWait(1200)
target = int(dur * 0.8)
print(f"3) после отпускания: позиция {win.player.position()} (цель ~{target}), "
      f"кадр скрыт: {not win.scrub_view.isVisible()}")
assert abs(win.player.position() - target) < 1500, "плеер не догнал позицию"
assert not win.scrub_view.isVisible()

# 4. метки фрагмента — то же поведение
before = win.player.position()
timeline._drag = "out"
frames = []
for fraction in (0.5, 0.55, 0.6):
    timeline._apply_drag(timeline._x_of(int(dur * fraction)))
    QTest.qWait(60)
    frames.append(win.scrub_view.pixmap().cacheKey())
print(f"4) при тяге метки различных кадров: {len(set(frames))}, "
      f"плеер не тронут: {win.player.position() == before}")
assert len(set(frames)) >= 2, "кадр не менялся при тяге метки"
timeline._drag = None
win._on_preview_finished()

print("OK: превью откликается и на позицию, и на метки")
QTimer.singleShot(100, app.quit)
app.exec()
