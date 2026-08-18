#!/usr/bin/env bash
# Сборка Clipper.app. Запускать на macOS из папки проекта: ./build_macos.sh
set -euo pipefail

PY=${PYTHON:-python3}
command -v "$PY" >/dev/null || { echo "Не найден python3"; exit 1; }

echo "[1/5] Виртуальное окружение..."
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[2/5] Зависимости..."
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements-build.txt

echo "[3/5] ffmpeg в bin/..."
python tools/fetch_ffmpeg.py || echo "ВНИМАНИЕ: ffmpeg не скачался, положите его в bin/ вручную"

echo "[4/5] Инструменты для YouTube (qjs, botguard)..."
python tools/fetch_youtube_tools.py || echo "ВНИМАНИЕ: инструменты YouTube не скачались"

echo "[4.5/5] Иконка .icns..."
python tools/make_icon.py
if command -v iconutil >/dev/null; then
    python tools/make_icns.py || echo "ВНИМАНИЕ: .icns не собрался, соберётся без иконки"
fi

echo "[5/5] Сборка Clipper.app..."
pyinstaller --noconfirm Clipper-macos.spec

# Подписи разработчика у нас нет — ставим ad-hoc, иначе Gatekeeper ругается сильнее.
if command -v codesign >/dev/null; then
    codesign --force --deep --sign - "dist/Clipper.app" >/dev/null 2>&1 \
        && echo "Подписано ad-hoc." || echo "codesign не сработал — не критично."
fi

cd dist
rm -f Clipper-macos.zip
# ditto сохраняет права и симлинки внутри бандла, обычный zip их портит.
ditto -c -k --sequesterRsrc --keepParent Clipper.app Clipper-macos.zip
cd ..

echo
echo "Готово: dist/Clipper.app и dist/Clipper-macos.zip"
echo "Первый запуск: правый клик по Clipper.app -> Открыть (приложение без подписи Apple)."
