"""Скачивание видео по ссылке через yt-dlp."""
from __future__ import annotations

import contextlib
import os
import re
import sys
import shutil
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import ffmpeg_tools, storage

URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

# Режим «сам разберись»: пробуем без cookies, а если сайт требует логин —
# перебираем установленные браузеры.
BROWSER_AUTO = "Авто"


def _browser_roots() -> dict:
    if sys.platform == "darwin":
        support = Path.home() / "Library" / "Application Support"
        return {
            "chrome": support / "Google/Chrome",
            "edge": support / "Microsoft Edge",
            "opera": support / "com.operasoftware.Opera",
            "brave": support / "BraveSoftware/Brave-Browser",
            "vivaldi": support / "Vivaldi",
            "firefox": support / "Firefox/Profiles",
            "safari": Path.home() / "Library" / "Cookies",
        }
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roaming = Path(os.environ.get("APPDATA", ""))
    return {
        "chrome": local / "Google/Chrome/User Data",
        "edge": local / "Microsoft/Edge/User Data",
        "opera": roaming / "Opera Software/Opera Stable",
        "brave": local / "BraveSoftware/Brave-Browser/User Data",
        "vivaldi": local / "Vivaldi/User Data",
        "firefox": roaming / "Mozilla/Firefox/Profiles",
    }


def site_domain(url: str) -> str:
    """vimeo.com из https://vimeo.com/123 — по нему и раскладываем cookies."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    parts = [p for p in host.split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def cookie_cache_path(url: str) -> Path:
    """Свой файл на каждый сайт: чужие cookies на диск не выкладываем."""
    return storage.data_dir() / "cookies" / f"{site_domain(url) or 'site'}.txt"


POT_BINARY = "rustypipe-botguard"


def pot_binary() -> Optional[Path]:
    """Генератор PO-токенов: без него YouTube отдаёт 403 на популярные ролики."""
    return ffmpeg_tools.find_binary(POT_BINARY)


def _prepare_pot() -> bool:
    """Плагин ищет бинарник в PATH — добавляем туда наш каталог."""
    binary = pot_binary()
    if not binary:
        return False
    folder = str(binary.parent)
    if folder not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
    return True


# Имя рантайма для yt-dlp -> имя исполняемого файла.
JS_RUNTIME_BINARIES = {"quickjs": "qjs", "deno": "deno", "node": "node", "bun": "bun"}


def js_runtimes() -> dict:
    """YouTube считает подписи ссылок в JS: без рантайма он отдаёт 403.

    Сами по себе yt-dlp ищет только deno, поэтому подсказываем ему и наш
    встроенный qjs (лежит в bin рядом с ffmpeg), и то, что стоит в системе.
    """
    found = {}
    for runtime, binary in JS_RUNTIME_BINARIES.items():
        path = ffmpeg_tools.find_binary(binary) or shutil.which(binary)
        if path:
            found[runtime] = {"path": str(path)}
    return found


def installed_browsers() -> list:
    """Браузеры, у которых на диске есть профиль — только их и пробуем."""
    return [name for name, root in _browser_roots().items() if root.exists()]


def find_url(text: str) -> Optional[str]:
    """Достаём ссылку из строки — люди часто вставляют её вместе с текстом."""
    m = URL_RE.search((text or "").strip())
    return m.group(0).rstrip(".,;)") if m else None


class DownloadCancelled(RuntimeError):
    pass


@dataclass
class DownloadResult:
    path: Path
    title: str
    duration: float
    cookies_source: str = ""   # что сработало — приложение это запоминает


def _quality(limit: str = "") -> str:
    """Цепочка запасных вариантов: H.264+AAC → любой mp4 → вообще что-нибудь.

    H.264 нужен не из вредности: встроенный проигрыватель Windows не умеет
    AV1 и VP9, а рендер из H.264 идёт без лишнего перекодирования.
    """
    height = f"[height<={limit}]" if limit else ""
    return (
        f"bestvideo[vcodec^=avc1]{height}+bestaudio[acodec^=mp4a]/"
        f"bestvideo[vcodec^=avc1]{height}+bestaudio/"
        f"best[vcodec^=avc1]{height}/"
        f"bestvideo{height}+bestaudio/"
        f"best{height}/best"
    )


QUALITY_FORMATS = {
    "Максимальное": _quality(),
    "1080p": _quality("1080"),
    "720p": _quality("720"),
    "480p": _quality("480"),
}


def download(
    url: str,
    out_dir: Path,
    quality: str = "Максимальное",
    on_progress: Optional[Callable[[float, str], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    cookies_from_browser: Optional[str] = None,
    cookies_file: Optional[Path] = None,
    proxy: Optional[str] = None,
) -> DownloadResult:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Не установлен yt-dlp. Выполните: pip install -r requirements.txt"
        ) from exc

    out_dir.mkdir(parents=True, exist_ok=True)

    def hook(d: dict) -> None:
        if should_cancel and should_cancel():
            raise DownloadCancelled()
        if d.get("status") == "downloading" and on_progress:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            percent = (done / total * 100.0) if total else 0.0
            speed = d.get("speed") or 0
            speed_txt = f"{speed / 1024 / 1024:.1f} МБ/с" if speed else ""
            on_progress(percent, speed_txt)
        elif d.get("status") == "finished" and on_progress:
            on_progress(100.0, "обработка…")

    opts: dict = {
        "outtmpl": str(out_dir / "%(title).80B [%(id)s].%(ext)s"),
        "format": QUALITY_FORMATS.get(quality, QUALITY_FORMATS["Максимальное"]),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "restrictfilenames": True,
        # Только на Windows: на macOS этот режим ломает пути — разделители
        # заменяются на обратные слэши, а пустой путь превращается в корень,
        # из-за чего временные файлы уезжали в «/» (там запись запрещена).
        "windowsfilenames": sys.platform == "win32",
        # Служебные файлы держим рядом с результатом: у собранного приложения
        # рабочий каталог может оказаться корнем тома.
        "paths": {"temp": str(out_dir)},
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        # Качаем кусками: ссылки YouTube протухают, и на середине прилетает 403 —
        # с кусками yt-dlp перезапрашивает только текущий отрезок.
        "http_chunk_size": 10 * 1024 * 1024,
    }
    runtimes = js_runtimes()
    if runtimes:
        opts["js_runtimes"] = runtimes
    _prepare_pot()
    if proxy:
        # Пустая строка у yt-dlp означает «строго напрямую», поэтому пишем
        # значение только когда пользователь его задал.
        opts["proxy"] = proxy
    ffmpeg = ffmpeg_tools.ffmpeg_path()
    if ffmpeg:
        # yt-dlp нужен ffmpeg, чтобы склеить раздельные видео- и аудиодорожки.
        opts["ffmpeg_location"] = str(ffmpeg.parent)
    # Порядок попыток: что указал пользователь → без cookies → перебор браузеров.
    # Порядок источников cookies: явный выбор → анонимно → сохранённый кэш.
    cache = cookie_cache_path(url)
    auto = cookies_from_browser == BROWSER_AUTO and not cookies_file
    sources: list = []
    if cookies_file:
        sources.append((f"{cookies_file.name}", {"cookiefile": str(cookies_file)}))
    if cookies_from_browser and cookies_from_browser != BROWSER_AUTO:
        sources.append((cookies_from_browser, {"cookiesfrombrowser": (cookies_from_browser,)}))
    if auto:
        # Большинству сайтов cookies не нужны — не платим за них временем.
        sources.insert(0, ("", {}))
    if cache.exists() and not cookies_file:
        # Снятые раньше cookies: браузер для них закрывать уже не нужно.
        sources.append((f"сохранённые cookies для {site_domain(url)}", {"cookiefile": str(cache)}))
    if not sources:
        sources.append(("", {}))

    # yt-dlp пишет причины отказа в лог (например «no key found»), а исключение
    # приходит потом и уже без подробностей — запоминаем их по ходу.
    notes: dict = {}

    def watch(message: str) -> None:
        low = message.lower()
        if "could not be decrypted" in low or "no key found" in low:
            notes["locked_keyring"] = True
        if "find-generic-password failed" in low:
            notes["locked_keyring"] = True
        if on_log:
            on_log(message)

    opts["logger"] = _Logger(watch)
    info, used_source = _extract_trying_cookies(opts, url, sources, auto, watch, notes)

    with YoutubeDL(opts) as ydl:
        path = Path(ydl.prepare_filename(info))
        if not path.exists():
            merged = path.with_suffix(".mp4")
            path = merged if merged.exists() else _guess_downloaded(out_dir, path)
    return DownloadResult(
        path=path,
        title=str(info.get("title") or path.stem),
        duration=float(info.get("duration") or 0.0),
        cookies_source=used_source,
    )





class _Logger:
    """Приёмник сообщений yt-dlp."""

    def __init__(self, sink) -> None:
        self._sink = sink

    def debug(self, msg: str) -> None:
        if self._sink and not msg.startswith("[debug]"):
            self._sink(msg)

    def info(self, msg: str) -> None:
        if self._sink:
            self._sink(msg)

    def warning(self, msg: str) -> None:
        if self._sink:
            self._sink(msg)

    def error(self, msg: str) -> None:
        if self._sink:
            self._sink(msg)


def _extract_trying_cookies(opts: dict, url: str, sources: list, auto: bool,
                            on_log, notes: dict | None = None):
    """Перебираем источники cookies, пока сайт не отдаст видео."""
    # Итоговое сообщение строим по исходной причине («нужен логин»), а не по
    # технической ошибке последнего браузера — иначе она сбивает с толку.
    login_exc: Exception | None = None
    last_exc: Exception | None = None
    tried: list = []

    for label, extra in sources:
        save_to = cookie_cache_path(url) if "cookiesfrombrowser" in extra else None
        try:
            info = _extract_with_retries({**opts, **extra}, url, on_log, save_to)
            if save_to and on_log:
                on_log(f"Cookies из {label} сохранены — дальше закрывать браузер не нужно.")
            return info, label
        except Exception as exc:  # noqa: BLE001
            if not _cookies_may_help(exc) and not _cookies_unreadable(exc):
                raise _friendly_error(exc, url) from exc
            last_exc = exc
            if _cookies_may_help(exc):
                login_exc = exc
            if label:
                tried.append(f"{label}: {_cookie_failure_reason(exc, label, notes)}")

    if not auto:
        final = login_exc or last_exc
        raise _friendly_error(final, url, tried) from final

    # Сайт требует логин, а конкретный источник не задан — ищем сами.
    for browser in installed_browsers():
        if on_log:
            on_log(f"Нужен вход в аккаунт — пробую cookies из {browser}…")
        try:
            info = _extract_with_retries(
                {**opts, "cookiesfrombrowser": (browser,)}, url, on_log,
                save_cookies_to=cookie_cache_path(url),
            )
            if on_log:
                on_log(
                    f"Cookies из {browser} сохранены — дальше закрывать браузер не нужно."
                )
            return info, browser
        except Exception as exc:  # noqa: BLE001
            reason = _cookie_failure_reason(exc, browser, notes)
            tried.append(f"{browser}: {reason}")
            if on_log:
                on_log(f"{browser}: {reason}")
            if not _cookies_may_help(exc) and not _cookies_unreadable(exc):
                raise _friendly_error(exc, url) from exc
            last_exc = exc
            if _cookies_may_help(exc):
                login_exc = exc

    final = login_exc or last_exc
    raise _friendly_error(final, url, tried) from final


def _cookies_unreadable(exc: Exception) -> bool:
    """Этот источник cookies не читается — не беда, берём следующий."""
    if isinstance(exc, (PermissionError, FileNotFoundError)):
        return True
    low = str(exc).lower()
    return any(hint in low for hint in (
        "could not copy", "failed to decrypt", "could not find", "unsupported",
        # macOS закрывает cookies Safari до выдачи полного доступа к диску,
        # а Windows — базу запущенного браузера.
        "operation not permitted", "errno 1", "permission denied", "access is denied"))


def _cookie_failure_reason(exc: Exception, browser: str, notes: dict | None = None) -> str:
    low = str(exc).lower()
    if notes and notes.pop("locked_keyring", False):
        if sys.platform == "darwin":
            return ("cookies зашифрованы, ключ в Связке ключей — разрешите доступ "
                    "во всплывающем запросе macOS")
        return "браузер шифрует cookies, нужен файл cookies.txt"
    if "operation not permitted" in low or "errno 1" in low or "permission denied" in low:
        if sys.platform == "darwin":
            return ("нет доступа — дайте программе «Полный доступ к диску» "
                    "в Системных настройках")
        return "нет прав на чтение файла cookies"
    if "could not copy" in low:
        return f"браузер запущен, закройте {browser} и повторите"
    if "failed to decrypt" in low:
        return "браузер шифрует cookies, нужен файл cookies.txt"
    if "could not find" in low:
        return "нет базы cookies"
    if _needs_login(exc):
        return "нет входа в аккаунт на этом сайте"
    return str(exc)[:120]


def _save_cookies(ydl, path: Path, domain: str) -> None:
    """Снятые из браузера cookies живут долго — держим копию, но только по делу."""
    try:
        jar = ydl.cookiejar
        for cookie in list(jar):
            if not (cookie.domain or "").lstrip(".").endswith(domain):
                jar.clear(cookie.domain, cookie.path, cookie.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        jar.save(str(path), ignore_discard=True, ignore_expires=True)
    except Exception:  # noqa: BLE001 — не критично, просто не будет кэша
        pass


def _extract_with_retries(opts: dict, url: str, on_log, save_cookies_to: Path | None = None) -> dict:
    """Применяем меры по одной, накапливая их: беды часто идут парами."""
    attempt_opts = dict(opts)
    applied: set = set()
    with contextlib.ExitStack() as stack:
        for _ in range(len(_MITIGATIONS) + 1):
            try:
                return _extract(attempt_opts, url, save_cookies_to)
            except Exception as exc:  # noqa: BLE001
                fix = _pick_mitigation(exc, url, applied)
                if not fix:
                    raise
                name, message, apply = fix
                applied.add(name)
                if on_log:
                    on_log(message)
                apply(attempt_opts, stack)
        raise RuntimeError("Не удалось скачать: перебраны все обходные пути.")


def _fix_proxy(opts: dict, stack) -> None:
    # В системе включён прокси (VPN-клиент), но сам он не запущен.
    opts["proxy"] = ""
    stack.enter_context(_without_proxy_env())


def _fix_ipv4(opts: dict, stack) -> None:      # noqa: ARG001
    opts["source_address"] = "0.0.0.0"


def _fix_plain_tls(opts: dict, stack) -> None:  # noqa: ARG001
    opts["_plain_tls"] = True
    opts["http_headers"] = _browser_headers(opts.get("http_headers"))


def _fix_pot(opts: dict, stack) -> None:        # noqa: ARG001
    # YouTube отдаёт 403, пока клиент не предъявит PO-токен, а умеют это
    # только web-клиенты. Ни один не работает на всех роликах, поэтому даём
    # список: yt-dlp соберёт форматы со всех и проверит перед скачиванием.
    extractor_args = dict(opts.get("extractor_args") or {})
    extractor_args["youtube"] = {
        **extractor_args.get("youtube", {}),
        "player_client": ["web_embedded", "mweb", "web_safari", "tv_embedded"],
    }
    opts["extractor_args"] = extractor_args
    opts["check_formats"] = "selected"


def _fix_check_formats(opts: dict, stack) -> None:  # noqa: ARG001
    opts["check_formats"] = "selected"


# Порядок важен: сначала дешёвые и безопасные меры, потом тяжёлые.
_MITIGATIONS = (
    ("proxy", "Системный прокси не отвечает — пробую напрямую…",
     _fix_proxy, lambda exc, url: _looks_like_dead_proxy(exc)),
    ("ipv4", "Таймаут соединения — повторяю по IPv4…",
     _fix_ipv4, lambda exc, url: _looks_like_network_timeout(exc)),
    ("plain_tls", "Сайт заблокировал запрос — пробую как обычный браузер…",
     _fix_plain_tls, lambda exc, url: _looks_like_bot_wall(exc) or (
         "403" in str(exc).lower() and "tiktok.com" in url.lower())),
    ("pot", "YouTube требует PO-токен — перехожу на web-клиент…",
     _fix_pot, lambda exc, url: (_is_forbidden(exc) or _is_bot_check(exc))
     and _prepare_pot()),
    ("retry_fresh", "Ссылка протухла (403) — беру свежую и продолжаю…",
     _fix_check_formats, lambda exc, url: _is_forbidden(exc)),
    ("drm", "Формат под DRM — ищу пригодный…",
     _fix_check_formats, lambda exc, url: "drm" in str(exc).lower()),
)


def _is_forbidden(exc: Exception) -> bool:
    low = str(exc).lower()
    return "403" in low or "forbidden" in low


def _is_bot_check(exc: Exception) -> bool:
    """«Sign in to confirm you're not a bot» — это не про аккаунт, а про
    PO-токен: у нас есть чем ответить, cookies тут не первое средство."""
    low = str(exc).lower()
    return "not a bot" in low or "sign in to confirm" in low


def _pick_mitigation(exc: Exception, url: str, applied: set):
    """Первая подходящая мера, которую ещё не применяли."""
    for name, message, apply, matches in _MITIGATIONS:
        if name not in applied and matches(exc, url):
            return name, message, apply
    return None


BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _browser_headers(extra: dict | None = None) -> dict:
    """Дефолтные заголовки yt-dlp плюс наши — затирать их целиком нельзя,
    иначе пропадают Accept и Sec-Fetch-*, и защита сайта это замечает."""
    from yt_dlp.utils.networking import std_headers

    headers = dict(std_headers)
    headers.update(extra or {})
    headers.update({
        "User-Agent": BROWSER_UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.tiktok.com/",
    })
    return headers


def _plain_tls_class():
    """yt-dlp подделывает отпечаток TLS через curl_cffi, а защита TikTok именно
    его и блокирует. Такому клиенту говорим ходить обычным TLS."""
    from yt_dlp import YoutubeDL

    class PlainTlsYoutubeDL(YoutubeDL):
        def _impersonate_target_available(self, target) -> bool:  # noqa: ARG002
            return False

    return PlainTlsYoutubeDL


def _extract(opts: dict, url: str, save_cookies_to: Path | None = None) -> dict:
    from yt_dlp import YoutubeDL

    opts = dict(opts)
    downloader_class = _plain_tls_class() if opts.pop("_plain_tls", False) else YoutubeDL
    with downloader_class(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if save_cookies_to is not None:
            _save_cookies(ydl, save_cookies_to, site_domain(url))
    if info.get("_type") == "playlist":
        info = info["entries"][0]
    return info


_TIMEOUT_HINTS = ("timed out", "timeout", "connection reset", "handshake operation")

# Классика: в Windows остался включён прокси от выключенного VPN-клиента.
_PROXY_HINTS = ("failed to connect to 127.0.0.1", "failed to connect to localhost",
                "proxy", "curl: (7)", "10061", "actively refused", "connection refused")


def _looks_like_dead_proxy(exc: Exception) -> bool:
    low = str(exc).lower()
    return any(hint in low for hint in _PROXY_HINTS)


# Признаки того, что до нас даже не доехала настоящая страница.
_BOT_WALL_HINTS = ("unexpected response from webpage request",
                   "unable to extract universal data",
                   "site maintenance", "unable to extract challenge data")


def _looks_like_bot_wall(exc: Exception) -> bool:
    low = str(exc).lower()
    return any(hint in low for hint in _BOT_WALL_HINTS)


def _needs_login(exc: Exception) -> bool:
    low = str(exc).lower()
    return any(hint in low for hint in _LOGIN_HINTS)


def _cookies_may_help(exc: Exception) -> bool:
    """Кому сайт не доверяет — тому помогают cookies: и при запросе логина,
    и при антибот-защите, и при глухом 403 после всех обходных путей."""
    return _needs_login(exc) or _looks_like_bot_wall(exc) or _is_forbidden(exc)


def _looks_like_network_timeout(exc: Exception) -> bool:
    low = str(exc).lower()
    return any(hint in low for hint in _TIMEOUT_HINTS)


def _guess_downloaded(out_dir: Path, expected: Path) -> Path:
    """Расширение могло смениться после мерджа — ищем файл с тем же именем."""
    matches = sorted(out_dir.glob(expected.stem + ".*"), key=lambda p: p.stat().st_mtime)
    if matches:
        return matches[-1]
    raise FileNotFoundError(f"Скачанный файл не найден: {expected}")


# Сайты периодически ломают публичные ключи/анонимный доступ — в таких случаях
# нужны cookies залогиненного аккаунта, а голая ошибка yt-dlp это не объясняет.
_LOGIN_HINTS = (
    "failed to fetch macos oauth token",
    "only works when logged-in",
    "http error 401",
    "sign in to confirm",
    "login required",
    "this video is private",
)


def _friendly_error(exc: Exception, url: str, tried: list | None = None) -> Exception:
    if getattr(exc, "_clipper_friendly", False):
        return exc
    text = str(exc)
    low = text.lower()
    if _looks_like_bot_wall(exc) or ("403" in low and "tiktok" in low):
        lines = [
            "Сайт не пустил программу: сработала защита от автоматических запросов.",
            "",
        ]
        if tried:
            lines += ["Что я попробовал:"] + [f"  • {t}" for t in tried] + [""]
        lines += [
            "Что помогает:",
            "1. Подождать 10–15 минут — защита снимает блок сама.",
            "2. Дать программе cookies: откройте сайт в браузере, закройте браузер",
            "   полностью и повторите (режим «Авто» подберёт их сам), либо укажите",
            "   файл cookies.txt кнопкой «Файл cookies…».",
            "",
            "Исходная ошибка:",
            text,
        ]
        return _mark(RuntimeError(chr(10).join(lines)))
    if ("403" in low or "forbidden" in low) and not pot_binary():
        return _mark(RuntimeError(
            "YouTube требует PO-токен, а генератор токенов не найден." + chr(10) + chr(10) +
            f"Положите {POT_BINARY}.exe в папку bin рядом с программой "
            "или выполните: python tools/fetch_pot.py" + chr(10) + chr(10) +
            "Исходная ошибка:" + chr(10) + text
        ))
    if ("403" in low or "forbidden" in low) and not js_runtimes():
        return _mark(RuntimeError(
            "YouTube отдал 403: не найден JavaScript-рантайм, без него подписи "
            "ссылок не считаются." + chr(10) + chr(10) +
            "Поставьте Node.js (https://nodejs.org) или Deno и повторите — "
            "программа подхватит его сама." + chr(10) + chr(10) +
            "Исходная ошибка:" + chr(10) + text
        ))
    if "drm" in low:
        return _mark(RuntimeError(
            "Видео защищено DRM — скачать его нельзя ни этой программой, "
            "ни любой другой: поток зашифрован на стороне сайта."
        ))
    if _looks_like_dead_proxy(exc):
        return _mark(RuntimeError(
            "Нет соединения через системный прокси, и напрямую сайт тоже не открылся."
            + chr(10) + chr(10) +
            "В Windows включён прокси, но программа-клиент (VPN) не запущена. "
            "Запустите её — либо снимите прокси в «Параметры → Сеть и Интернет → Прокси-сервер»."
            + chr(10) + chr(10) + "Исходная ошибка:" + chr(10) + text
        ))
    if any(hint in low for hint in _LOGIN_HINTS):
        lines = [
            "Сайт не отдаёт видео анонимно — нужны cookies залогиненного аккаунта.",
            "",
        ]
        if tried:
            lines += ["Что я попробовал:"] + [f"  • {t}" for t in tried] + [""]
        if sys.platform == "darwin":
            lines += [
                "Что сделать на macOS:",
                "1. Войдите на сайт в Safari.",
                "2. Дайте программе «Полный доступ к диску»: Системные настройки →",
                "   Конфиденциальность и безопасность → Полный доступ к диску → добавьте",
                "   Clipper и перезапустите его. Пункт «Программа → Доступ к cookies…»",
                "   открывает нужный раздел настроек.",
                "3. Chrome и Opera держат ключ от cookies в Связке ключей: если macOS",
                "   покажет запрос доступа — разрешите.",
                "4. Всегда работающий путь: экспортируйте cookies.txt расширением вроде",
                "   «Get cookies.txt LOCALLY» и укажите файл в Настройках.",
            ]
        else:
            lines += [
                "Что сделать:",
                "1. Войдите на сайт в браузере.",
                "2. Полностью закройте этот браузер (запущенный держит cookies заблокированными)",
                "   и повторите — в режиме «Авто» программа сама переберёт браузеры.",
                "3. Если браузер шифрует cookies (Chrome 127+), экспортируйте их расширением",
                "   вроде «Get cookies.txt LOCALLY» и укажите файл в Настройках.",
            ]
        lines += ["", "Исходная ошибка:", text]
        return _mark(RuntimeError(chr(10).join(lines)))
    return exc


def _mark(exc: Exception) -> Exception:
    """Помечаем уже переведённые ошибки, чтобы не заворачивать их дважды."""
    exc._clipper_friendly = True   # noqa: SLF001
    return exc


@contextlib.contextmanager
def _without_proxy_env():
    """libcurl читает *_PROXY из окружения сам, поэтому гасим их на время попытки."""
    keys = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
    saved = {k: os.environ.pop(k, None) for k in keys}
    os.environ["NO_PROXY"] = "*"
    try:
        yield
    finally:
        os.environ.pop("NO_PROXY", None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
