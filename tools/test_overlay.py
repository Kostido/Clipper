"""Кадр предпросмотра обязан закрывать всю область видео и меняться при протяжке.

Ошибка, ради которой написан тест: оверлей получал размер только по ресайзу окна,
а собственные ресайзы области видео его не двигали. Кадр рисовался маленьким
прямоугольником в углу, и со стороны это выглядело как «превью не реагирует».
"""
import glob
import hashlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QByteArray, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import clipper.app as app_mod
from clipper.timeline import clip_length_text, frame_count

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
QTest.qWait(2000)

waited = 0
while waited < 60_000 and not win.thumbnails:
    QTest.qWait(300)
    waited += 300
assert win.thumbnails, "раскадровка не получилась"

video, overlay = win.video_widget, win.scrub_view
print(f"1) видео {video.width()}x{video.height()}, оверлей {overlay.width()}x{overlay.height()}")
assert overlay.size() == video.size(), "оверлей не совпадает с областью видео"


def snapshot() -> str:
    pixmap = overlay.pixmap()
    assert not pixmap.isNull(), "кадр предпросмотра пуст"
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.WriteOnly)
    pixmap.toImage().save(buffer, "PNG")
    buffer.close()
    return hashlib.md5(bytes(data)).hexdigest()


timeline = win.timeline
dur = timeline.duration()
y = timeline.height() // 2
x_of = lambda ms: QPoint(int(timeline._x_of(ms)), y)  # noqa: E731

shots = []
QTest.mousePress(timeline, Qt.LeftButton, Qt.NoModifier, x_of(dur))
for part in (0.8, 0.6, 0.4, 0.2):
    QTest.mouseMove(timeline, x_of(int(dur * part)))
    QTest.qWait(80)
    shots.append(snapshot())
QTest.mouseRelease(timeline, Qt.LeftButton, Qt.NoModifier, x_of(int(dur * 0.2)))
QTest.qWait(200)
print(f"2) при тяге метки разных кадров: {len(set(shots))} из {len(shots)}")
assert len(set(shots)) == len(shots), "кадр не меняется во время протяжки"
assert not overlay.isVisible(), "оверлей не исчез после отпускания"

win.resize(940, 700)
QTest.qWait(400)
print(f"3) после ресайза: видео {video.width()}x{video.height()}, "
      f"оверлей {overlay.width()}x{overlay.height()}")
assert overlay.size() == video.size(), "оверлей отстал от области видео"

fps = win.info.fps if win.info else 0.0
timeline.set_range(0, min(dur, 4000))
win._update_range_label()
QTest.qWait(150)
label = win.range_label.text()
expected = frame_count(min(dur, 4000), fps)
print(f"4) подпись фрагмента: {label}")
assert str(expected) in label, f"в подписи нет числа кадров ({expected})"
assert clip_length_text(4000, 25.0) == clip_length_text(4000, 25.0, short=True)

print("OK: оверлей закрывает видео, кадры меняются, длина показана в секундах и кадрах")
win.close()
