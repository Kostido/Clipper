"""Выбор качества: «Максимальное» обязано брать настоящий максимум.

Повод: селектор начинался с bestvideo[vcodec^=avc1], а H.264 на YouTube есть
только до 1080p — 1440p и 4K отдаются в VP9 и AV1. Первая ступень всегда
находилась, и «Максимальное» молча упиралось в 1080p.

Проверяем не строку селектора, а решение самого yt-dlp на каталоге форматов,
устроенном как у YouTube.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from yt_dlp import YoutubeDL
from clipper import downloader as dl

AUDIO = [
    {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2",
     "abr": 128, "url": "http://x/a"},
    {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus",
     "abr": 160, "url": "http://x/b"},
]
VIDEO = [
    {"format_id": "18", "ext": "mp4", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2",
     "height": 360, "fps": 30, "tbr": 700, "url": "http://x/c"},
    {"format_id": "244", "ext": "webm", "vcodec": "vp9", "acodec": "none",
     "height": 480, "fps": 30, "tbr": 1200, "url": "http://x/d"},
    {"format_id": "136", "ext": "mp4", "vcodec": "avc1.4d401f", "acodec": "none",
     "height": 720, "fps": 30, "tbr": 2500, "url": "http://x/e"},
    {"format_id": "137", "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none",
     "height": 1080, "fps": 30, "tbr": 4500, "url": "http://x/f"},
    {"format_id": "299", "ext": "mp4", "vcodec": "avc1.64002a", "acodec": "none",
     "height": 1080, "fps": 60, "tbr": 6000, "url": "http://x/g"},
    {"format_id": "308", "ext": "webm", "vcodec": "vp9", "acodec": "none",
     "height": 1440, "fps": 60, "tbr": 12000, "url": "http://x/h"},
    {"format_id": "315", "ext": "webm", "vcodec": "vp9", "acodec": "none",
     "height": 2160, "fps": 60, "tbr": 22000, "url": "http://x/i"},
]


def choose(quality: str, formats: list) -> list:
    info = {"_type": "video", "id": "test", "title": "t", "extractor": "test",
            "extractor_key": "Test", "webpage_url": "http://x",
            "formats": [dict(f) for f in formats]}
    params = {"quiet": True, "no_warnings": True, "simulate": True,
              "format": dl.QUALITY_FORMATS[quality], "format_sort": dl.FORMAT_SORT}
    with YoutubeDL(params) as ydl:
        result = ydl.process_ie_result(info, download=False)
    return result.get("requested_formats") or [result]


def describe(picked: list) -> str:
    return " + ".join(
        f"{f['format_id']}"
        f"({f.get('height', 'звук')}{'p' if f.get('height') else ''}"
        f"{'/' + str(int(f['fps'])) if f.get('fps') else ''} "
        f"{f['vcodec'] if f.get('vcodec') not in (None, 'none') else f.get('acodec')})"
        for f in picked)


all_formats = VIDEO + AUDIO

print("1) что выбирается на полном каталоге:")
expected = {"Максимальное": 2160, "2160p": 2160, "1440p": 1440,
            "1080p": 1080, "720p": 720, "480p": 480}
for quality, height in expected.items():
    picked = choose(quality, all_formats)
    video = next(f for f in picked if f.get("vcodec") not in (None, "none"))
    print(f"   {quality:14} -> {describe(picked)}")
    assert video["height"] == height, \
        f"{quality}: ожидали {height}p, получили {video['height']}p"

# 2) главное: максимум не упирается в H.264
picked = choose("Максимальное", all_formats)
video = next(f for f in picked if f.get("vcodec") not in (None, "none"))
assert video["height"] == 2160, "«Максимальное» снова взяло не максимум"
assert not video["vcodec"].startswith("avc1"), \
    "выбран H.264 — значит кодек снова важнее разрешения"

# 3) среди равных по разрешению предпочитаем H.264 и 60 кадров
picked = choose("1080p", all_formats)
video = next(f for f in picked if f.get("vcodec") not in (None, "none"))
print(f"2) при равном разрешении: {video['format_id']} "
      f"({video['vcodec']}, {int(video['fps'])} к/с)")
assert video["vcodec"].startswith("avc1"), "H.264 больше не предпочитается"
assert video["fps"] == 60, "выбрана менее плавная дорожка"

# 4) звук: при прочих равных берём AAC — он играет везде
audio = next(f for f in picked if f.get("vcodec") in (None, "none"))
print(f"3) звук: {audio['format_id']} ({audio['acodec']})")
assert audio["acodec"].startswith("mp4a"), "AAC больше не предпочитается"

# 5) среди равных по картинке берём то, что ложится в mp4
AV1_4K = {"format_id": "701", "ext": "mp4", "vcodec": "av01.0.13M.08",
          "acodec": "none", "height": 2160, "fps": 60, "tbr": 20000, "url": "http://x/j"}
picked = choose("Максимальное", all_formats + [AV1_4K])
video = next(f for f in picked if f.get("vcodec") not in (None, "none"))
print(f"4) AV1 против VP9 в 4K: {video['format_id']} ({video['vcodec']})")
assert video["vcodec"].startswith("av01"), \
    "выбран VP9 — файл уедет в mkv, хотя рядом был AV1 в mp4"

# 6) под потолок ничего не подходит — берём что есть, а не падаем
only_4k = [f for f in VIDEO if f["height"] == 2160] + AUDIO
picked = choose("480p", only_4k)
video = next(f for f in picked if f.get("vcodec") not in (None, "none"))
print(f"5) видео только в 4K, просили 480p -> {describe(picked)}")
assert video["height"] == 2160, "запасная ступень не сработала"

print("OK: максимум берёт максимум, H.264 предпочитается среди равных")
