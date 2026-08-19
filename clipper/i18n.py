"""Язык интерфейса: русский по умолчанию, английский для остальных систем.

Ключ словаря — русская строка прямо из кода, значение — перевод. Так текст
в исходниках остаётся читаемым, а переводится только при показе.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QLocale

EN = {
    # --- окно и меню ---
    "{app} — скачать, обрезать, отрендерить": "{app} — download, trim, render",
    "Программа": "App",
    "Настройки…": "Settings…",
    "Настройки": "Settings",
    "Доступ к cookies…": "Cookie access…",
    "Перенести в «Программы»…": "Move to Applications…",
    "Проверить обновления": "Check for updates",
    "Проверять при запуске": "Check on startup",
    "О программе": "About",
    "Язык": "Language",
    "Как в системе": "System default",
    "Русский": "Русский",
    "English": "English",
    "Язык интерфейса изменится после перезапуска программы.":
        "The interface language will change after you restart the app.",
    "Готово": "Done",
    "Журнал ▾": "Log ▾",
    "Журнал ▴": "Log ▴",
    "Готов к работе": "Ready",

    # --- источник ---
    "Ссылка на видео или перетащите файл в окно": "Video link, or drop a file here",
    "Качество загрузки": "Download quality",
    "Скачать": "Download",
    "Отменить": "Cancel",
    "Открыть файл": "Open file",
    "Скачивание: %p%": "Downloading: %p%",
    "Обновление: %p%": "Updating: %p%",
    "Максимальное": "Best available",
    "ЗАГРУЗКА": "DOWNLOADING",
    "Папка": "Folder",
    "Обзор": "Browse",
    "Cookies": "Cookies",
    "Файл cookies": "Cookie file",
    "Cookies: {name}": "Cookies: {name}",
    "Прокси": "Proxy",
    "пусто — как в Windows; например socks5://127.0.0.1:10808":
        "empty — use system settings; e.g. socks5://127.0.0.1:10808",
    "Настройки сохраняются автоматически и применяются к следующей загрузке.":
        "Settings are saved automatically and apply to the next download.",
    "«Авто» — программа сама возьмёт cookies из установленного браузера, "
    "если сайт потребует вход в аккаунт. Браузер при этом должен быть закрыт.":
        "“Auto” takes cookies from an installed browser when a site asks you to "
        "sign in. The browser must be closed.",
    "Файл cookies.txt (формат Netscape) — запасной путь, когда браузер "
    "не отдаёт cookies напрямую. Экспортируется расширением вроде "
    "«Get cookies.txt LOCALLY».":
        "A cookies.txt file (Netscape format) — the fallback when a browser will "
        "not hand over its cookies. Export it with an add-on such as "
        "“Get cookies.txt LOCALLY”.",
    "Некоторые сайты (TikTok, Instagram) не отдают видео на IP датацентров "
    "и VPN. Здесь можно направить скачивание через свой прокси.":
        "Some sites (TikTok, Instagram) refuse datacenter and VPN addresses. "
        "Route downloads through your own proxy here.",
    "Папка загрузок, cookies, прокси": "Download folder, cookies, proxy",
    "ХРАНЕНИЕ": "STORAGE",
    "Очистить служебные файлы": "Clear temporary files",
    "Превью и раскадровки — создаются заново при следующем открытии":
        "Previews and frame strips — rebuilt next time you open a video",
    "Удалить скачанные видео…": "Delete downloaded videos…",
    "Файлы из папки загрузок — это ваши видео, они удаляются навсегда":
        "Files in the download folder are your videos; deletion is permanent",
    "Скачанные видео: {count} шт., {size}. Служебные файлы: {temp_size}.":
        "Downloaded videos: {count}, {size}. Temporary files: {temp_size}.",
    "Служебные файлы удалены, освобождено {size}.":
        "Temporary files removed, {size} freed.",
    "Папка загрузок пуста.": "The download folder is empty.",
    "Удалить {count} видео из {folder} ({size})? Файлы будут стёрты безвозвратно.":
        "Delete {count} videos from {folder} ({size})? This cannot be undone.",
    "Удалено видео: {count}.": "Videos deleted: {count}.",
    "Не удалось удалить:": "Could not delete:",
    "Авто": "Auto",
    "Не использовать": "Don't use",

    # --- плеер и фрагмент ---
    "Перетащите сюда видео или ссылку": "Drop a video or a link here",
    "Отпустите — откроется в плеере": "Release to open in the player",
    "Видео не загружено": "No video loaded",
    "Пробел — играть или пауза": "Space — play or pause",
    "Громкость": "Volume",
    "Начало": "Start",
    "Конец": "End",
    "Фрагмент": "Clip",
    "Сбросить": "Reset",
    "Фрагмент: —": "Clip: —",
    "Фрагмент: {start} → {end}   ({length:6.1f} с)":
        "Clip: {start} → {end}   ({length:6.1f} s)",
    "Клавиша I — начало фрагмента по текущей позиции":
        "Key I — set clip start at the playhead",
    "Клавиша O — конец фрагмента по текущей позиции":
        "Key O — set clip end at the playhead",
    "Проиграть выделенный фрагмент": "Play the selected clip",
    "Тяните синие метки — это начало и конец фрагмента.\n"
    "Клик по дорожке — перемотка. I и O — метки, ← → — шаг 1 с, с Shift — 0,1 с.":
        "Drag the blue handles to set the clip.\n"
        "Click the track to seek. I and O set handles, ← → step 1 s, with Shift 0.1 s.",

    # --- рендер ---
    "H.264": "H.264",
    "Сколько данных в секунду. Больше — чётче картинка и тяжелее файл: "
    "минута при 5 Мбит/с весит примерно 38 МБ.":
        "Data per second. Higher means a sharper picture and a bigger file: "
        "a minute at 5 Mbps is about 38 MB.",
    "Авто (по разрешению)": "Auto (by resolution)",
    "1,5 Мбит/с — экономно": "1.5 Mbps — light",
    "3 Мбит/с": "3 Mbps",
    "5 Мбит/с — обычный": "5 Mbps — standard",
    "8 Мбит/с — высокий": "8 Mbps — high",
    "12 Мбит/с": "12 Mbps",
    "20 Мбит/с — максимум": "20 Mbps — maximum",
    "Скорость кодирования (preset)": "Encoding speed (preset)",
    "Разрешение результата": "Output resolution",
    "Кадры в секунду": "Frames per second",
    "Как в исходнике": "Same as source",
    "Без перекодирования": "No re-encoding",
    "Мгновенная нарезка копированием потока. Режет по ключевым кадрам, "
    "поэтому границы могут сместиться на пару секунд.":
        "Instant cut by copying the stream. It cuts on keyframes, so the edges "
        "can shift by a couple of seconds.",
    "Открыть папку с результатом": "Open the output folder",
    "Отрендерить фрагмент": "Render clip",
    "Отрендерить фрагмент…": "Render clip…",
    "Отменить рендер": "Cancel render",
    "Рендер: %p%": "Rendering: %p%",
    "Рендерю…": "Rendering…",
    "Ошибка рендера": "Render failed",
    "Готово: {path}": "Done: {path}",
    "Куда сохранить фрагмент": "Where to save the clip",
    "Видео (*.mp4)": "Video (*.mp4)",
    "Нельзя записать результат поверх исходного файла.":
        "The result cannot overwrite the source file.",
    "Сначала откройте или скачайте видео.": "Open or download a video first.",
    "Отметьте фрагмент: конец должен быть позже начала.":
        "Mark a clip: the end must come after the start.",

    # --- скачивание ---
    "Вставьте ссылку на видео.": "Paste a video link.",
    "Скачиваю…": "Downloading…",
    "Скачиваю {url}": "Downloading {url}",
    "Скачиваю… {percent:.0f}% {speed}": "Downloading… {percent:.0f}% {speed}",
    "Скачано: {title}": "Downloaded: {title}",
    "Ошибка скачивания": "Download failed",
    "Не удалось скачать видео:": "Could not download the video:",
    "Ошибка: {message}": "Error: {message}",
    "Готово: {path_str}": "Done: {path_str}",
    "Сработали cookies: {source}": "Cookies that worked: {source}",
    "Скачивание отменено.": "Download cancelled.",
    "Выберите видео": "Choose a video",
    "Видео (*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.flv);;Все файлы (*.*)":
        "Video (*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.flv);;All files (*.*)",
    "Папка для загрузок": "Download folder",
    "Файл cookies (Netscape cookies.txt)": "Cookie file (Netscape cookies.txt)",
    "cookies.txt (*.txt);;Все файлы (*)": "cookies.txt (*.txt);;All files (*)",
    "Файл cookies отключён.": "Cookie file disabled.",
    "Использую cookies из {path}": "Using cookies from {path}",
    "Открываю {name}": "Opening {name}",
    "Перетащено файлов: {count} — открываю первый.":
        "{count} files dropped — opening the first one.",

    # --- превью и раскадровка ---
    "Кодек {codecs} встроенный плеер не воспроизводит — готовлю превью…":
        "The built-in player cannot play {codecs} — preparing a preview…",
    "Готовлю превью для просмотра…": "Preparing a preview…",
    "Готовлю превью… {percent:.0f}%": "Preparing a preview… {percent:.0f}%",
    "Превью уже готово, беру из кэша.": "Preview already cached.",
    "Превью готово: {name} (обрезка и рендер идут из оригинала)":
        "Preview ready: {name} (trimming and rendering use the original)",
    "Превью готово — оригинал для рендера сохранён":
        "Preview ready — the original is kept for rendering",
    "Превью не получилось: {message}": "Preview failed: {message}",
    "Не удалось подготовить превью": "Could not prepare the preview",
    "Предпросмотр: {count} кадров.": "Preview: {count} frames.",
    "Раскадровка не получилась — предпросмотр будет медленнее.":
        "Could not build the frame strip — preview will be slower.",
    "Проигрыватель: {message}": "Player: {message}",
    "Файл: {name} — {width}x{height}, {fps:.2f} к/с, {duration}":
        "File: {name} — {width}x{height}, {fps:.2f} fps, {duration}",
    "Не удалось прочитать параметры файла: {error}":
        "Could not read the file parameters: {error}",

    # --- обновления ---
    "Проверяю обновления…": "Checking for updates…",
    "Проверка обновлений: {message}": "Update check: {message}",
    "Обновления: релизов на GitHub пока нет.": "Updates: no GitHub releases yet.",
    "На GitHub ещё нет опубликованных релизов — обновляться не с чего.":
        "There are no published releases on GitHub yet — nothing to update to.",
    "Обновления: установлена последняя версия {version}.":
        "Updates: you are on the latest version {version}.",
    "У вас последняя версия — {version}.": "You are on the latest version — {version}.",
    "Доступна версия {name} (у вас {version}).":
        "Version {name} is available (you have {version}).",
    "Обновить сейчас?": "Update now?",
    "Качаю обновление {name}…": "Downloading update {name}…",
    "Обновление не удалось: {message}": "Update failed: {message}",
    "Обновление {name} установлено.": "Update {name} installed.",
    "Версия {name} установлена. Перезапустить сейчас?":
        "Version {name} is installed. Restart now?",
    "не удалось заменить программу: {error}": "could not replace the app: {error}",
    "Программа перенесена: {path}": "App moved to: {path}",
    "Не удалось перенести: {error}": "Could not move the app: {error}",
    "Готово: {path}\n\nСейчас откроется перенесённая копия. Прежнюю можно удалить "
    "из папки загрузок — дальше обновления будут ставиться сами.":
        "Done: {path}\n\nThe moved copy will open now. You can delete the one in "
        "Downloads — updates will install themselves from now on.",
    "Программа запущена из временной копии — так macOS поступает с "
    "приложениями из интернета, пока их не перенесли к себе. "
    "Поэтому обновиться на месте нельзя.\n\n"
    "Перенести Clipper в «Программы» ({folder}) и перезапустить?":
        "The app is running from a temporary copy — macOS does this to apps from "
        "the internet until they are moved. Updating in place is impossible.\n\n"
        "Move Clipper to Applications ({folder}) and restart?",
    "Программа запущена из временной копии macOS — перенесите её "
    "в «Программы», иначе обновления ставиться не будут.":
        "Running from a macOS temporary copy — move the app to Applications, "
        "otherwise updates cannot install.",
    "Добавьте Clipper в «Полный доступ к диску» и перезапустите программу.":
        "Add Clipper to Full Disk Access and restart it.",
    "{app} {version}\n\nСкачивание видео по ссылке, обрезка фрагмента и рендер "
    "в H.264.\nИсходники и релизы: {url}":
        "{app} {version}\n\nDownload videos by link, trim a clip and render it to "
        "H.264.\nSource code and releases: {url}",

    # --- окружение ---
    "Тема: qdarktheme (тёмная)": "Theme: qdarktheme (dark)",
    "Тема qdarktheme не найдена — интерфейс в системном оформлении.":
        "qdarktheme not found — using the system look.",
    "ffmpeg: {path}": "ffmpeg: {path}",
    "ffmpeg не найден — скачивание в высоком качестве и рендер работать не будут.":
        "ffmpeg not found — high-quality downloads and rendering will not work.",
}


SUPPORTED = ("ru", "en")


def detect() -> str:
    """Русский — для русской системы, остальным английский.

    Переменная CLIPPER_LANG перекрывает выбор: удобно для проверки и для тех,
    у кого система на одном языке, а работать хочется на другом.
    """
    forced = os.environ.get("CLIPPER_LANG", "").strip().lower()
    if forced in SUPPORTED:
        return forced
    return "ru" if QLocale.system().language() == QLocale.Russian else "en"


LANG = detect()


def set_language(code: str) -> str:
    """Явно задать язык: «ru», «en» или пустая строка — как в системе."""
    global LANG
    LANG = code if code in SUPPORTED else detect()
    return LANG


def tr(text: str) -> str:
    """Русский текст как есть, для остальных систем — английский перевод."""
    if LANG == "ru":
        return text
    return EN.get(text, text)
