<div align="center">

<img src="assets/clipper.png" width="96" alt="Clipper">

# Clipper

**Ссылка → видео → нужный кусок → MP4/H.264.**
Windows и macOS. Без установки, без рекламы, без облаков.

[![Release](https://img.shields.io/github/v/release/Kostido/Clipper?style=flat-square&color=4c8dff)](https://github.com/Kostido/Clipper/releases/latest)
[![Build](https://img.shields.io/github/actions/workflow/status/Kostido/Clipper/build.yml?style=flat-square)](https://github.com/Kostido/Clipper/actions)
[![Downloads](https://img.shields.io/github/downloads/Kostido/Clipper/total?style=flat-square&color=4c8dff)](https://github.com/Kostido/Clipper/releases)

<img src="assets/screenshot.png" width="820" alt="Окно Clipper">

</div>

## Скачать

| Файл | Система |
|------|---------|
| [`Clipper.exe`](https://github.com/Kostido/Clipper/releases/latest) | Windows 10/11 — один файл |
| [`Clipper-portable-win64.zip`](https://github.com/Kostido/Clipper/releases/latest) | Windows — настройки и загрузки в своей папке |
| [`Clipper-macos.zip`](https://github.com/Kostido/Clipper/releases/latest) | macOS 11+ — внутри `Clipper.app` |

> macOS: перетащите `Clipper.app` в «Программы», затем правый клик → **Открыть**
> (нет подписи Apple). Запуск прямо из папки загрузок macOS выполняет из временной
> копии — оттуда не работает автообновление; программа предложит перенести себя сама.

## Как работать

1. Вставьте ссылку → **Скачать**. Или перетащите файл в окно.
2. Растяните синие метки на дорожке — это и есть фрагмент.
3. **Отрендерить фрагмент** → готовый MP4.

Плей всегда играет выделенное: начинает с метки начала, встаёт на метке конца.
Пока тянете метку или дорожку, плеер перематывает само видео — кадр под курсором виден сразу.
На самом выделении написана его длина: секунды и кадры (`4.75 с · 142 кадра`).

| Клавиша | Действие |
|---------|----------|
| `I` / `O` | начало / конец фрагмента по текущей позиции |
| `Пробел` | играть / пауза |
| `←` `→` | шаг 1 с (с `Shift` — 0,1 с) |

## Возможности

- **~1000 сайтов** через yt-dlp: YouTube, Vimeo, TikTok, Instagram, VK, X.
- **Всё внутри**: ffmpeg, движок JavaScript и генератор PO-токенов для YouTube.
- **H.264 + AAC** приоритетом — файл играется везде и режется без перекодирования.
- **Рендер**: битрейт, preset, разрешение, fps. Или «без перекодирования» — мгновенно.
- **Cookies** для видео «только после входа»: сами из браузера, кэш по домену, файл `cookies.txt`.
- **Автообновление** из релизов GitHub — на Windows и macOS.
- **Два языка**: интерфейс на английском, если система не русская. Переключается в меню.
- **Очистка кэша** в настройках: служебные файлы и, отдельно, скачанные видео.
