"""Очистка кэша: служебные файлы удаляются молча, видео — только с подтверждением."""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
import clipper.app as app_mod
from clipper import storage

app = QApplication(sys.argv)
app_mod._apply_theme(app)
win = app_mod.MainWindow()
win.show()
QTest.qWaitForWindowExposed(win)

# своя папка загрузок, чтобы не трогать настоящие файлы
downloads = Path(tempfile.mkdtemp(prefix="clipper-cache-test-"))
win.dir_edit.setText(str(downloads))
(downloads / "clip1.mp4").write_bytes(b"0" * 2_000_000)
(downloads / "clip2.mkv").write_bytes(b"0" * 1_000_000)
(downloads / "notes.txt").write_text("не видео", encoding="utf-8")
(downloads / "subfolder").mkdir()
(downloads / "subfolder" / "keep.mp4").write_bytes(b"0" * 500)

# служебные файлы
for folder in storage.temp_dirs():
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "junk.bin").write_bytes(b"0" * 300_000)

win._refresh_cache_info()
print("1) сводка:", win.cache_label.text())
assert "2" in win.cache_label.text(), "видео посчитаны неверно"

print("2) чистим служебные файлы")
win.clear_temp_cache()
left = sum(storage.folder_size(f) for f in storage.temp_dirs())
print("   осталось служебных:", left)
assert left == 0, "служебные файлы не удалились"
assert (downloads / "clip1.mp4").exists(), "видео не должны были пострадать"

print("3) отказ от удаления видео")
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
win.delete_downloads()
assert (downloads / "clip1.mp4").exists(), "файл удалён вопреки отказу"
print("   файлы на месте")

print("4) согласие на удаление")
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
win.delete_downloads()
QTest.qWait(300)
print("   осталось в папке:", sorted(p.name for p in downloads.iterdir()))
assert not (downloads / "clip1.mp4").exists() and not (downloads / "clip2.mkv").exists()
assert (downloads / "notes.txt").exists(), "не-видео трогать нельзя"
assert (downloads / "subfolder" / "keep.mp4").exists(), "вложенные папки трогать нельзя"

print("5) пустая папка")
QMessageBox.information = staticmethod(lambda *a, **k: None)
win.delete_downloads()
print("   сводка после очистки:", win.cache_label.text())

shutil.rmtree(downloads, ignore_errors=True)
print("OK: кэш чистится, чужие файлы и подпапки не трогаются")
QTimer.singleShot(100, app.quit)
app.exec()
