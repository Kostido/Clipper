"""Перезапуск после обновления не должен упираться в защиту PyInstaller.

Повод: после установки обновления новый экземпляр отказывался стартовать —
«Security validation failure: parent process has different executable». Виноват
не файл: загрузчик PyInstaller передаёт дочерним процессам служебные
переменные и сверяет их с родителем, а родителем был уже заменённый exe.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper import updater

# Окружение, какое загрузчик оставляет запущенной программе
DIRTY = {
    "_PYI_ARCHIVE_FILE": r"C:\Users\me\Clipper.old.exe",
    "_PYI_APPLICATION_HOME_DIR": r"C:\Users\me\_MEI123",
    "_PYI_PARENT_PROCESS_LEVEL": "1",
    "_MEIPASS2": r"C:\Users\me\_MEI123",
    "CLIPPER_TEST_KEEP": "не трогать",
}

saved = {k: os.environ.get(k) for k in list(DIRTY) + ["LD_LIBRARY_PATH",
                                                      "LD_LIBRARY_PATH_ORIG"]}
try:
    os.environ.update(DIRTY)
    env = updater.child_env()

    print("1) служебные переменные PyInstaller:")
    for key in DIRTY:
        if key == "CLIPPER_TEST_KEEP":
            continue
        print(f"   {key}: {'убрана' if key not in env else 'ОСТАЛАСЬ'}")
        assert key not in env, f"{key} осталась — новый экземпляр снова не стартует"
    assert not [k for k in env if k.startswith("_PYI_")], "остались другие _PYI_*"

    print("2) чужие переменные не трогаем:")
    assert env.get("CLIPPER_TEST_KEEP") == "не трогать", "затёрли постороннюю переменную"
    assert "PATH" in env or "Path" in env, "потеряли PATH"
    print("   CLIPPER_TEST_KEEP и PATH на месте")

    # 3) пути к библиотекам: загрузчик подменяет их, оригинал лежит рядом
    os.environ["LD_LIBRARY_PATH"] = "/tmp/_MEI999"
    os.environ["LD_LIBRARY_PATH_ORIG"] = "/usr/lib/mine"
    env = updater.child_env()
    print(f"3) LD_LIBRARY_PATH: {env.get('LD_LIBRARY_PATH')!r}")
    assert env.get("LD_LIBRARY_PATH") == "/usr/lib/mine", "не вернули исходный путь"
    assert "LD_LIBRARY_PATH_ORIG" not in env, "служебная копия пути осталась"
finally:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

# 4) запуск обновлённой программы идёт именно с чистым окружением
source = Path(updater.__file__).read_text(encoding="utf-8")
starts = [line.strip() for line in source.splitlines()
          if "subprocess.Popen(" in line and ("current_exe()" in line or '"open"' in line)]
print("4) места запуска программы:")
for line in starts:
    print("   " + line[:78])
assert starts, "не нашли ни одного запуска — тест устарел"
for name in ("restart", "launch"):
    body = source.split(f"def {name}(")[1].split("\ndef ")[0]
    assert "child_env()" in body, f"{name}() запускает программу со старым окружением"

print("OK: перезапуск после обновления идёт с чистым окружением")
