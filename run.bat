@echo off
REM Запуск из исходников без сборки exe.
setlocal
if not exist .venv (
    python -m venv .venv || exit /b 1
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip >nul
    python -m pip install -r requirements.txt || exit /b 1
) else (
    call .venv\Scripts\activate.bat
)
python main.py
endlocal
