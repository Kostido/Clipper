"""Поиск ffmpeg/ffprobe и операции обрезки/перекодирования."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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


# Разумный битрейт под высоту кадра — если пользователь не выбрал свой.
_BITRATE_BY_HEIGHT = ((2160, 24000), (1440, 14000), (1080, 8000),
                      (720, 5000), (480, 2500), (0, 1500))


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
    if s.copy_mode:
        cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    else:
        filters = []
        if s.scale_height:
            filters.append(f"scale=-2:{s.scale_height}")
        if s.fps:
            filters.append(f"fps={s.fps:g}")
        if filters:
            cmd += ["-vf", ",".join(filters)]
        bitrate = s.video_bitrate or default_bitrate(probe(src).height)
        cmd += [
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
            "-c:a", "aac",
            "-b:a", s.audio_bitrate,
            "-movflags", "+faststart",
        ]
    cmd.append(str(dst))
    return cmd


def export_clip(
    src: Path,
    dst: Path,
    settings: ExportSettings,
    on_progress: Optional[Callable[[float], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Path:
    """Рендерит кусок видео. Прогресс считаем по time= в выводе ffmpeg."""
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


def _thumb_workers() -> int:
    """Кадры режутся независимыми вызовами ffmpeg — грузим все ядра, но не машину целиком."""
    return max(2, min(8, (os.cpu_count() or 4)))


def extract_thumbnails(
    src: Path,
    out_dir: Path,
    count: int = 120,
    height: int = 180,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> list:
    """Раскадровка для отзывчивого предпросмотра.

    Плеер перематывается медленно, поэтому пока метку тянут, показываем
    заранее вырезанные кадры. Каждый кадр берём отдельным быстрым переходом
    (-ss до -i) и делаем это в несколько потоков: декодировать весь файл
    ради сотни картинок слишком долго — на трёхминутном ролике это минута.
    """
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return []
    duration = probe(src).duration
    if duration <= 0:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        old.unlink(missing_ok=True)

    count = max(2, min(count, int(duration * 2)))
    step = duration / count
    jobs = [(index, index * step) for index in range(count)]

    def grab(job: tuple) -> tuple:
        index, moment = job
        if should_cancel and should_cancel():
            return moment, None
        target = out_dir / f"{index:05d}.jpg"
        cmd = [
            str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{moment:.3f}", "-i", str(src), "-frames:v", "1",
            "-vf", f"scale=-2:{height}", "-q:v", "6", str(target),
        ]
        result = subprocess.run(cmd, capture_output=True, **_popen_kwargs())
        if result.returncode != 0 or not target.exists():
            return moment, None
        return moment, target

    with ThreadPoolExecutor(max_workers=_thumb_workers()) as pool:
        frames = list(pool.map(grab, jobs))

    if should_cancel and should_cancel():
        return []
    return [(moment, path) for moment, path in frames if path]
