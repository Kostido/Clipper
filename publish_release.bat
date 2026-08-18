@echo off
REM Публикация релиза на GitHub — после этого автообновление увидит новую версию.
REM Использование: publish_release.bat 1.2.0 "Что нового"
setlocal

if "%~1"=="" (
    echo Укажите версию: publish_release.bat 1.2.0 "Что нового"
    exit /b 1
)
set VERSION=%~1
set NOTES=%~2
if "%NOTES%"=="" set NOTES=Обновление Clipper %VERSION%

where gh >nul 2>nul || (echo Не найден GitHub CLI: https://cli.github.com && exit /b 1)

echo [1/4] Прописываю версию %VERSION% в clipper\__init__.py...
> clipper\__init__.py echo """Clipper — скачивание видео по ссылке, обрезка и рендер в H.264."""
>> clipper\__init__.py echo.
>> clipper\__init__.py echo __version__ = "%VERSION%"

echo [2/4] Собираю exe...
call build_windows.bat || exit /b 1

echo [3/4] Фиксирую версию в git...
git add -A
git commit -m "Release v%VERSION%" || echo (нечего коммитить)
git tag -f v%VERSION%
git push || exit /b 1
git push -f origin v%VERSION% || exit /b 1

echo [4/4] Публикую релиз с файлом dist\Clipper.exe...
gh release create v%VERSION% "dist\Clipper.exe" --title "Clipper %VERSION%" --notes "%NOTES%" || exit /b 1

echo.
echo Готово. Установленные копии увидят обновление при следующем запуске.
endlocal
