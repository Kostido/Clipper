"""Собирает портативный архив: dist/Clipper-portable-win64.zip

Запуск: python tools/make_portable.py   (после build_windows.bat)

Портативная сборка отличается только файлом-маркером portable.txt: увидев его
рядом с собой, программа держит настройки, кэш cookies и загрузки в своей папке,
не касаясь реестра и профиля пользователя.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
EXE = DIST / "Clipper.exe"
ARCHIVE = DIST / "Clipper-portable-win64.zip"

MARKER = """Этот файл включает портативный режим Clipper.
Пока он лежит рядом с Clipper.exe, программа хранит всё своё в этой же папке:

  ClipperData\\settings.ini   настройки
  ClipperData\\cookies\\       сохранённые cookies сайтов
  Downloads\\                 скачанные видео

Удалите файл — и программа вернётся к обычному режиму (настройки в реестре,
кэш в %APPDATA%\\Clipper, загрузки в «Видео»).
"""

READ_ME = """Clipper (портативная версия)
============================

Запуск: Clipper.exe — установка не нужна, всё внутри одного файла.

Что умеет: скачивает видео по ссылке (YouTube, Vimeo, TikTok и ещё ~1000 сайтов),
даёт выделить фрагмент прямо на дорожке плеера и рендерит его в MP4 / H.264.
ffmpeg, движок JavaScript и генератор PO-токенов для YouTube уже внутри.

Портативный режим включён файлом portable.txt: настройки, cookies и загрузки
лежат в этой папке, реестр Windows не используется. Папку можно носить на флешке.

Автообновление в портативном режиме работает так же, но если папка лежит там,
где нет прав на запись, обновление не установится — просто скачайте новую
версию вручную: https://github.com/Kostido/Clipper/releases

Диагностика, если что-то не работает:
    Clipper.exe --selftest report.txt
"""


def main() -> int:
    if not EXE.exists():
        print(f"Не найден {EXE} — сначала выполните build_windows.bat")
        return 1

    ARCHIVE.unlink(missing_ok=True)
    with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(EXE, "Clipper/Clipper.exe")
        archive.writestr("Clipper/portable.txt", MARKER)
        archive.writestr("Clipper/ПРОЧТИ_МЕНЯ.txt", READ_ME)

    size = ARCHIVE.stat().st_size / 1024 / 1024
    print(f"  {ARCHIVE} ({size:.1f} МБ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
