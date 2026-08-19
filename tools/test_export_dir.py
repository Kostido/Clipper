"""Диалог экспорта должен открываться там, куда сохраняли в прошлый раз.

Папка запоминается отдельно от папки загрузок и переживает перезапуск: люди
качают исходники в одно место, а готовые куски складывают в другое.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication
import clipper.app as app_mod

app = QApplication(sys.argv)
app_mod._apply_theme(app)

sandbox = Path(tempfile.mkdtemp(prefix="clipper_export_"))
downloads = sandbox / "downloads"
first = sandbox / "montage"
second = sandbox / "instagram"
for folder in (downloads, first, second):
    folder.mkdir()

win = app_mod.MainWindow()
win.settings.remove("export_dir")
win.export_dir = None
win.dir_edit.setText(str(downloads))
win.source = downloads / "lecture.mp4"
win.source.write_bytes(b"")

# 1) экспорта ещё не было — предлагаем папку загрузок
suggested = win._suggested_export_path()
print(f"1) первый экспорт: {suggested}")
assert suggested.parent == downloads, "без истории должна предлагаться папка загрузок"
assert suggested.name == "lecture_clip.mp4", "имя файла не из исходника"

# 2) сохранили в другую папку — она запомнилась
win._remember_export_dir(first)
suggested = win._suggested_export_path()
print(f"2) после сохранения в {first.name}: {suggested}")
assert suggested.parent == first, "папка последнего сохранения не подставилась"

# 3) папка загрузок на подсказку больше не влияет
win.dir_edit.setText(str(sandbox / "downloads"))
assert win._suggested_export_path().parent == first, "папка загрузок перебила историю"

# 4) сохранили ещё раз в третье место — помним последнее
win._remember_export_dir(second)
print(f"4) после сохранения в {second.name}: {win._suggested_export_path()}")
assert win._suggested_export_path().parent == second

# 5) новое окно (перезапуск программы) — папка на месте
win.close()
again = app_mod.MainWindow()
again.dir_edit.setText(str(downloads))
again.source = win.source
print(f"5) после перезапуска: {again._suggested_export_path()}")
assert again.export_dir == second, "папка не пережила перезапуск"
assert again._suggested_export_path().parent == second

# 6) папку удалили — молча возвращаемся к загрузкам, без падения
second.rmdir()
print(f"6) папка удалена: {again._suggested_export_path()}")
assert again._suggested_export_path().parent == downloads, "исчезнувшая папка не должна ломать диалог"

again.settings.remove("export_dir")
again.close()
print("OK: экспорт помнит последнюю папку и переживает перезапуск")
