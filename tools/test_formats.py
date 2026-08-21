"""Форматы вывода: MP4, WebM с лупом и MP3 из видео.

Проверяем не только команду, но и сам файл: что кодек тот, звук убран там,
где просили, метка зацикливания записана, а из видео получается звук.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper import ffmpeg_tools as ft

ffmpeg = ft.ffmpeg_path()
if not ffmpeg:
    print("ffmpeg не найден — пропускаю")
    sys.exit(0)

sandbox = Path(tempfile.mkdtemp(prefix="clipper_formats_"))
src = sandbox / "src.mp4"
subprocess.run(
    [str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error",
     "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=6",
     "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)],
    check=True,
)


def streams(path: Path) -> str:
    out = subprocess.run([str(ffmpeg), "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    return out.stderr


def render(name: str, settings: ft.ExportSettings) -> Path:
    dst = sandbox / name
    ft.export_clip(src, dst, settings)
    assert dst.exists() and dst.stat().st_size > 0, f"{name} не создан"
    return dst


# 1) MP4 как раньше — со звуком
mp4 = render("clip.mp4", ft.ExportSettings(1, 4, video_bitrate=500))
text = streams(mp4)
print(f"1) MP4: {mp4.stat().st_size / 1024:.0f} КБ")
assert "Video: h264" in text and "Audio: aac" in text, "MP4 собран не тем кодеком"

# 2) MP4 без звука
muted = render("clip_mute.mp4", ft.ExportSettings(1, 4, video_bitrate=500, mute=True))
text = streams(muted)
print(f"2) MP4 без звука: {muted.stat().st_size / 1024:.0f} КБ")
assert "Video: h264" in text, "пропало видео"
assert "Audio:" not in text, "звук остался"

# 3) WebM — VP9 и Opus
webm = render("clip.webm", ft.ExportSettings(1, 4, video_bitrate=500,
                                             container=ft.FORMAT_WEBM))
text = streams(webm)
print(f"3) WebM: {webm.stat().st_size / 1024:.0f} КБ")
assert "Video: vp9" in text, "WebM собран не в VP9"
assert "Audio: opus" in text, "в WebM нет звука Opus"

# 4) WebM с лупом — метка на месте, звука нет, длительность прежняя
looped = render("clip_loop.webm", ft.ExportSettings(1, 4, video_bitrate=500,
                                                    container=ft.FORMAT_WEBM, loop=True))
text = streams(looped)
print(f"4) WebM + луп: {looped.stat().st_size / 1024:.0f} КБ")
assert "Video: vp9" in text, "потеряли VP9"
assert "Audio:" not in text, "зацикленное видео должно быть без звука"
assert "LOOP" in text.upper(), "метка зацикливания не записана"
duration = ft.probe(looped).duration
assert abs(duration - 3.0) < 0.2, f"длительность изменилась: {duration:.2f} с"

# 5) MP3 из видео
mp3 = render("clip.mp3", ft.ExportSettings(1, 4, container=ft.FORMAT_MP3,
                                           audio_bitrate="128k"))
text = streams(mp3)
print(f"5) MP3: {mp3.stat().st_size / 1024:.0f} КБ")
assert "Audio: mp3" in text, "MP3 не собрался"
assert "Video:" not in text, "в MP3 утекло видео"
assert abs(ft.probe(mp3).duration - 3.0) < 0.2

# 6) расширение подставляется по формату
for container, suffix in ((ft.FORMAT_MP4, ".mp4"), (ft.FORMAT_WEBM, ".webm"),
                          (ft.FORMAT_MP3, ".mp3")):
    assert ft.ExportSettings(0, 1, container=container).suffix == suffix

# 7) луп сам по себе выключает звук, даже если галочку «без звука» не ставили
assert ft.ExportSettings(0, 1, loop=True).audio_off
assert ft.ExportSettings(0, 1, mute=True).audio_off
assert not ft.ExportSettings(0, 1).audio_off

# 8) быстрая нарезка тоже умеет выбрасывать звук
cmd = ft.build_export_command(src, sandbox / "copy.mp4",
                              ft.ExportSettings(1, 4, copy_mode=True, mute=True))
assert "-an" in cmd and "copy" in cmd, "в режиме копирования звук не убирается"

print("OK: MP4, WebM с лупом и MP3 собираются, звук отключается где просили")
