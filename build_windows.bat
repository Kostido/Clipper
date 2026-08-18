@echo off
REM Сборка Clipper.exe. Запускать в Windows из папки проекта.
setlocal

where python >nul 2>nul || (echo Не найден Python 3.10+ && exit /b 1)

if not exist .venv (
    echo [1/4] Создаю виртуальное окружение...
    python -m venv .venv || exit /b 1
)

echo [2/4] Ставлю зависимости...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r requirements-build.txt || exit /b 1

if not exist bin\ffmpeg.exe (
    echo [3/4] ffmpeg.exe не найден в bin\ — качаю...
    python tools\fetch_ffmpeg.py || echo ВН�?МАН�?Е: не удалось скачать ffmpeg, положите его в bin\ вручную.
) else (
    echo [3/4] ffmpeg уже на месте.
)

echo [4/4] Собираю exe...
pyinstaller --noconfirm Clipper.spec || exit /b 1

echo.
echo Готово: dist\Clipper.exe
endlocal
