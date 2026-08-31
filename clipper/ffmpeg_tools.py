"""Поиск ffmpeg/ffprobe и операции обрезки/перекодирования."""
from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable, Optional

# Прячем консольные окна дочерних процессов на Windows.
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _popen_kwargs() -> dict:
    kwargs = {"creationflags": CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    return kwargs


def _bundled_dir() -> Path:
    """Каталог рядом с exe (PyInstaller) или с исходниками."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _candidates(name: str) -> Iterable[Path]:
    exe = f"{name}.exe" if sys.platform == "win32" else name
    base = _bundled_dir()
    yield base / "bin" / exe
    yield base / exe
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        yield Path(meipass) / "bin" / exe
    found = shutil.which(exe)
    if found:
        yield Path(found)


def find_binary(name: str) -> Optional[Path]:
    for path in _candidates(name):
        if path.is_file():
            return path
    if name == "ffmpeg":
        # Последний шанс: пакет imageio-ffmpeg тянет с собой готовый бинарник.
        try:
            import imageio_ffmpeg

            return Path(imageio_ffmpeg.get_ffmpeg_exe())
        except Exception:
            return None
    return None


def ffmpeg_path() -> Optional[Path]:
    return find_binary("ffmpeg")


def ffprobe_path() -> Optional[Path]:
    return find_binary("ffprobe")


@dataclass
class MediaInfo:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    vcodec: str = ""
    acodec: str = ""


def probe(path: Path) -> MediaInfo:
    """Читаем параметры файла. ffprobe если есть, иначе парсим вывод ffmpeg."""
    probe_bin = ffprobe_path()
    if probe_bin:
        cmd = [
            str(probe_bin), "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ]
        out = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", **_popen_kwargs()
        )
        if out.returncode == 0:
            data = json.loads(out.stdout)
            streams = data.get("streams", [])
            video = next((s for s in streams if s.get("codec_type") == "video"), {})
            audio = any(s.get("codec_type") == "audio" for s in streams)
            duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0.0)
            audio_stream = next(
                (s for s in streams if s.get("codec_type") == "audio"), {})
            return MediaInfo(
                duration=duration,
                width=int(video.get("width") or 0),
                height=int(video.get("height") or 0),
                fps=_parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
                has_audio=audio,
                vcodec=str(video.get("codec_name") or ""),
                acodec=str(audio_stream.get("codec_name") or ""),
            )
    return _probe_via_ffmpeg(path)


def _parse_fps(value: Optional[str]) -> float:
    if not value or "/" not in str(value):
        try:
            return float(value or 0)
        except ValueError:
            return 0.0
    num, den = str(value).split("/", 1)
    try:
        den_f = float(den)
        return float(num) / den_f if den_f else 0.0
    except ValueError:
        return 0.0


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)")
_SIZE_RE = re.compile(r"(\d{2,5})x(\d{2,5})")
_FPS_RE = re.compile(r"(\d+\.?\d*)\s*fps")


def _probe_via_ffmpeg(path: Path) -> MediaInfo:
    binary = ffmpeg_path()
    if not binary:
        raise FFmpegMissingError()
    out = subprocess.run(
        [str(binary), "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", **_popen_kwargs()
    )
    text = out.stderr or ""
    duration = 0.0
    m = _DURATION_RE.search(text)
    if m:
        duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    width = height = 0
    video_line = next((ln for ln in text.splitlines() if "Video:" in ln), "")
    ms = _SIZE_RE.search(video_line)
    if ms:
        width, height = int(ms.group(1)), int(ms.group(2))
    mf = _FPS_RE.search(video_line)
    fps = float(mf.group(1)) if mf else 0.0
    return MediaInfo(duration, width, height, fps, "Audio:" in text)


class FFmpegMissingError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "Не найден ffmpeg. Положите ffmpeg.exe в папку bin рядом с программой, "
            "добавьте его в PATH или установите пакет imageio-ffmpeg."
        )


# Что можно получить на выходе. Ключ хранится в настройках, поэтому менять
# его нельзя — подписи берутся из интерфейса.
FORMAT_MP4 = "mp4"
FORMAT_WEBM = "webm"
FORMAT_MP3 = "mp3"
FORMATS = (FORMAT_MP4, FORMAT_WEBM, FORMAT_MP3)

FORMAT_SUFFIX = {FORMAT_MP4: ".mp4", FORMAT_WEBM: ".webm", FORMAT_MP3: ".mp3"}


@dataclass
class ExportSettings:
    start: float
    end: float
    video_bitrate: int = 0         # кбит/с; 0 = подобрать по разрешению
    preset: str = "medium"
    audio_bitrate: str = "192k"
    scale_height: int = 0          # 0 = как в исходнике
    fps: float = 0.0               # 0 = как в исходнике
    copy_mode: bool = False        # быстрая резка без перекодирования
    container: str = FORMAT_MP4    # mp4 | webm | mp3
    mute: bool = False             # выбросить звук из результата
    loop: bool = False             # пометить файл как зацикленный
    hw_encoder: str = ""           # имя аппаратного кодировщика; пусто — на процессоре

    @property
    def audio_off(self) -> bool:
        """Зацикленное видео идёт без звука: так его крутят по кругу и сайты,
        и мессенджеры — дорожка со звуком этому мешает."""
        return self.mute or self.loop

    @property
    def suffix(self) -> str:
        return FORMAT_SUFFIX.get(self.container, ".mp4")


# Разумный битрейт под высоту кадра — если пользователь не выбрал свой.
_BITRATE_BY_HEIGHT = ((2160, 24000), (1440, 14000), (1080, 8000),
                      (720, 5000), (480, 2500), (0, 1500))


# Ручной ввод битрейта: «6», «6.5 Мбит/с», «6000k», «6000 кбит/с».
_BITRATE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(k|к|m|м)?", re.IGNORECASE)
BITRATE_MIN, BITRATE_MAX = 100, 200_000        # кбит/с


def parse_bitrate(text: str) -> int:
    """Введённый вручную битрейт в кбит/с; 0 — если разобрать не вышло.

    Единицу берём из суффикса, а без него — по величине числа: «6» это шесть
    мегабит, «6000» — шесть тысяч килобит. Никто не задаёт 6 кбит/с видео.
    """
    match = _BITRATE_RE.search(str(text or ""))
    if not match:
        return 0
    value = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "").lower()
    if unit in ("m", "м"):
        value *= 1000
    elif unit not in ("k", "к") and value < 100:
        value *= 1000                          # без суффикса маленькое число — мегабиты
    kbit = int(round(value))
    return kbit if BITRATE_MIN <= kbit <= BITRATE_MAX else 0


def default_bitrate(height: int) -> int:
    """Кбит/с для H.264 при данной высоте кадра."""
    for min_height, bitrate in _BITRATE_BY_HEIGHT:
        if height >= min_height:
            return bitrate
    return 1500


_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.?\d*)")
_OUT_TIME_US_RE = re.compile(r"^out_time_(?:ms|us)=(\d+)")


def build_export_command(src: Path, dst: Path, s: ExportSettings) -> list[str]:
    binary = ffmpeg_path()
    if not binary:
        raise FFmpegMissingError()
    duration = max(0.0, s.end - s.start)
    # -progress pipe:2 даёт машинночитаемый прогресс построчно, -nostats убирает шум с \r.
    cmd = [str(binary), "-hide_banner", "-nostats", "-progress", "pipe:2", "-y"]
    # -ss до -i = быстрый поиск; при перекодировании точность даёт -accurate_seek.
    cmd += ["-ss", f"{s.start:.3f}", "-i", str(src), "-t", f"{duration:.3f}"]
    if s.container == FORMAT_MP3:
        cmd += _mp3_args(s)
    elif s.copy_mode:
        cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
        if s.audio_off:
            cmd += ["-an"]
    elif s.container == FORMAT_WEBM:
        cmd += _video_filters(s) + _webm_args(src, s)
    else:
        cmd += _video_filters(s) + _mp4_args(src, s)
    cmd.append(str(dst))
    return cmd


def _video_filters(s: ExportSettings) -> list[str]:
    filters = []
    if s.scale_height:
        filters.append(f"scale=-2:{s.scale_height}")
    if s.fps:
        filters.append(f"fps={s.fps:g}")
    return ["-vf", ",".join(filters)] if filters else []


def _audio_args(s: ExportSettings, codec: str) -> list[str]:
    return ["-an"] if s.audio_off else ["-c:a", codec, "-b:a", s.audio_bitrate]


# Аппаратные кодировщики H.264 по платформам, в порядке предпочтения.
# Наличие в сборке ffmpeg ещё не значит, что железо на месте, поэтому перед
# использованием кодировщик проверяется пробным запуском.
HW_ENCODERS = {
    "win32": ("h264_nvenc", "h264_qsv", "h264_amf"),
    "darwin": ("h264_videotoolbox",),
    "linux": ("h264_nvenc", "h264_qsv"),
}


@functools.lru_cache(maxsize=1)
def _encoder_names() -> frozenset:
    binary = ffmpeg_path()
    if not binary:
        return frozenset()
    out = subprocess.run(
        [str(binary), "-hide_banner", "-encoders"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", **_popen_kwargs())
    names = re.findall(r"^\s*[VAS][.A-Z]{5}\s+(\S+)", out.stdout or "", re.MULTILINE)
    return frozenset(names)


def _encoder_works(name: str) -> bool:
    """Пробуем закодировать один кадр: сборка может знать кодировщик, а
    видеокарты под него на машине не быть — тогда ffmpeg падает на открытии."""
    binary = ffmpeg_path()
    if not binary:
        return False
    cmd = [str(binary), "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", "color=black:s=320x240:d=0.1",
           "-frames:v", "1", "-c:v", name, "-f", "null", "-"]
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=30, **_popen_kwargs())
    except (subprocess.TimeoutExpired, OSError):
        return False
    return done.returncode == 0


@functools.lru_cache(maxsize=1)
def hw_encoder() -> Optional[str]:
    """Первый работающий аппаратный кодировщик H.264, или None."""
    available = _encoder_names()
    for name in HW_ENCODERS.get(sys.platform, ()):
        if name in available and _encoder_works(name):
            return name
    return None


def hw_encoder_label(name: str) -> str:
    """Человеческое имя железа — его показываем в журнале."""
    return {
        "h264_nvenc": "NVIDIA NVENC",
        "h264_qsv": "Intel Quick Sync",
        "h264_amf": "AMD AMF",
        "h264_videotoolbox": "Apple VideoToolbox",
    }.get(name, name)


def _hw_video_args(encoder: str, bitrate: int) -> list[str]:
    """Настройки качества у каждого производителя свои, общий только битрейт."""
    rate = ["-b:v", f"{bitrate}k", "-maxrate", f"{bitrate}k",
            "-bufsize", f"{bitrate * 2}k"]
    tuning = {
        # p5 — предпоследняя по качеству предустановка NVENC: заметно лучше
        # быстрых и всё ещё в разы быстрее процессорного кодирования.
        "h264_nvenc": ["-preset", "p5", "-rc", "vbr", "-profile:v", "high"],
        "h264_qsv": ["-preset", "slow", "-profile:v", "high"],
        "h264_amf": ["-quality", "balanced", "-profile:v", "high"],
        # allow_sw разрешает откат на процессор, если видеодвижок занят.
        "h264_videotoolbox": ["-profile:v", "high", "-allow_sw", "1"],
    }.get(encoder, [])
    return ["-c:v", encoder] + rate + tuning + ["-pix_fmt", "yuv420p"]


def _mp4_args(src: Path, s: ExportSettings) -> list[str]:
    bitrate = s.video_bitrate or default_bitrate(probe(src).height)
    if s.hw_encoder:
        return _hw_video_args(s.hw_encoder, bitrate) + [
            *_audio_args(s, "aac"),
            "-movflags", "+faststart",
        ] + _loop_args(s)
    return [
        "-c:v", "libx264",
        "-preset", s.preset,
        # Постоянный битрейт: размер файла предсказуем. maxrate с bufsize
        # держат поток в рамках, иначе x264 разгоняется на сложных сценах.
        "-b:v", f"{bitrate}k",
        "-maxrate", f"{bitrate}k",
        "-bufsize", f"{bitrate * 2}k",
        "-profile:v", "high",
        "-level", "4.1",
        "-pix_fmt", "yuv420p",
        *_audio_args(s, "aac"),
        "-movflags", "+faststart",
    ] + _loop_args(s)


def _webm_args(src: Path, s: ExportSettings) -> list[str]:
    """VP9 в WebM: то, что понимают браузеры без плагинов.

    row-mt и cpu-used выбраны ради скорости: у libvpx-vp9 качество на глаз
    почти не страдает, а без них рендер минутного ролика тянется вечность.
    """
    bitrate = s.video_bitrate or default_bitrate(probe(src).height)
    return [
        "-c:v", "libvpx-vp9",
        "-b:v", f"{bitrate}k",
        "-maxrate", f"{bitrate}k",
        "-bufsize", f"{bitrate * 2}k",
        "-row-mt", "1",
        "-deadline", "good",
        "-cpu-used", "2",
        "-pix_fmt", "yuv420p",
        *_audio_args(s, "libopus"),
    ] + _loop_args(s)


def _loop_args(s: ExportSettings) -> list[str]:
    """Метка зацикливания.

    Своего флага «крутить по кругу» ни в WebM, ни в MP4 нет — его задаёт плеер.
    Пишем тег, который читают браузеры и мессенджеры; всё остальное решает
    отсутствие звуковой дорожки, по нему такие файлы и считают анимацией.
    """
    return ["-metadata", "loop=true"] if s.loop else []


def _mp3_args(s: ExportSettings) -> list[str]:
    return [
        "-vn",                       # видео не нужно — забираем только звук
        "-c:a", "libmp3lame",
        "-b:a", s.audio_bitrate,
        "-id3v2_version", "3",       # такие теги читают и Windows, и плееры
    ]


def export_clip(
    src: Path,
    dst: Path,
    settings: ExportSettings,
    on_progress: Optional[Callable[[float], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Path:
    """Рендерит кусок видео. Прогресс считаем по time= в выводе ffmpeg.

    Если видеокарта отказала на середине (драйвер, занятый движок, сеанс без
    доступа к железу), повторяем на процессоре: лучше дольше, чем никак.
    """
    if settings.hw_encoder:
        try:
            return _run_export(src, dst, settings, on_progress, on_log, should_cancel)
        except ExportCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 — вторая попытка всё равно честнее
            if on_log:
                on_log(f"{hw_encoder_label(settings.hw_encoder)} не справился "
                       f"({str(exc).splitlines()[0]}) — повторяю на процессоре.")
            settings = replace(settings, hw_encoder="")
            if on_progress:
                on_progress(0.0)
    return _run_export(src, dst, settings, on_progress, on_log, should_cancel)


def _run_export(
    src: Path,
    dst: Path,
    settings: ExportSettings,
    on_progress: Optional[Callable[[float], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Path:
    cmd = build_export_command(src, dst, settings)
    total = max(0.001, settings.end - settings.start)
    if on_log:
        on_log(" ".join(cmd))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1, **_popen_kwargs()
    )
    tail: list[str] = []
    assert proc.stderr is not None
    for line in proc.stderr:
        line = line.rstrip()
        if not line:
            continue
        tail.append(line)
        del tail[:-40]
        done = _parse_progress_time(line)
        if done is not None and on_progress:
            on_progress(min(100.0, done / total * 100.0))
        elif on_log and ("Error" in line or "error" in line):
            on_log(line)
        if should_cancel and should_cancel():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise ExportCancelled()
    code = proc.wait()
    if code != 0:
        raise RuntimeError("ffmpeg завершился с ошибкой:\n" + "\n".join(tail[-15:]))
    if on_progress:
        on_progress(100.0)
    return dst


def _parse_progress_time(line: str) -> Optional[float]:
    """Секунды, уже записанные в файл, из строки прогресса ffmpeg."""
    m = _OUT_TIME_US_RE.match(line)
    if m:
        return int(m.group(1)) / 1_000_000
    m = _TIME_RE.search(line)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return None


class ExportCancelled(RuntimeError):
    pass


# Windows Media Foundation (на нём работает плеер Qt) знает H.264/AAC,
# а AV1, VP9 и Opus у большинства пользователей не воспроизводит.
PLAYABLE_VIDEO = {"h264", "avc1", "mpeg4", "hevc"}
PLAYABLE_AUDIO = {"aac", "mp3", "mp4a", ""}


def needs_preview_proxy(info: "MediaInfo | None") -> bool:
    if not info:
        return False
    if info.vcodec and info.vcodec.lower() not in PLAYABLE_VIDEO:
        return True
    return bool(info.acodec) and info.acodec.lower() not in PLAYABLE_AUDIO


def make_preview_proxy(
    src: Path,
    dst: Path,
    on_progress: Optional[Callable[[float], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Path:
    """Лёгкая H.264-копия только для просмотра — оригинал для рендера не трогаем."""
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("Не найден ffmpeg — не из чего сделать превью.")
    duration = probe(src).duration or 0.0
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ffmpeg), "-y", "-hide_banner", "-i", str(src),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        # Больше 720p для предпросмотра не нужно, а кодируется заметно быстрее.
        "-vf", "scale=-2:'min(720,ih)'",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", "-progress", "pipe:1", "-nostats",
        str(dst),
    ]
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace", **_popen_kwargs()
    )
    for line in process.stdout or ():
        if should_cancel and should_cancel():
            process.kill()
            raise RuntimeError("Подготовка превью отменена.")
        if line.startswith("out_time_ms=") and duration and on_progress:
            try:
                done = int(line.split("=", 1)[1]) / 1_000_000
            except ValueError:
                continue
            on_progress(min(100.0, done / duration * 100.0))
    process.wait()
    if process.returncode != 0 or not dst.exists():
        raise RuntimeError("ffmpeg не смог подготовить превью.")
    return dst


