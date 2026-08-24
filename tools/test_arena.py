"""Сайты-доски: Are.na и внятная ошибка вместо чужой.

Повод: ссылка на блок Are.na давала «Unsupported URL». Слово «unsupported»
попадало в признаки нечитаемых cookies, программа уходила перебирать браузеры
и показывала в конце отказ macOS в доступе к cookies Safari — то есть ошибку
про свой компьютер вместо настоящей причины.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper import downloader as dl

UNSUPPORTED = RuntimeError("ERROR: Unsupported URL: https://www.are.na/block/20345333")
SAFARI_DENIED = RuntimeError(
    "[Errno 1] Operation not permitted: '/Users/polinatitorova/Library/Containers/"
    "com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies'")

# 1) «Unsupported URL» — это не про cookies
print("1) разбор ошибки:")
assert not dl._cookies_unreadable(UNSUPPORTED), "снова уйдёт перебирать браузеры"
assert not dl._cookies_may_help(UNSUPPORTED), "cookies тут не помогут"
assert dl._looks_like_unsupported(UNSUPPORTED)
# ошибки чтения cookies по-прежнему считаются несущественными
assert dl._cookies_unreadable(SAFARI_DENIED), "отказ Safari перестал распознаваться"
assert dl._cookies_unreadable(RuntimeError("Could not copy Chrome cookie database"))

message = str(dl._friendly_error(UNSUPPORTED, "https://www.are.na/block/20345333"))
print("   " + message.splitlines()[0])
assert "не нашлось видео" in message
assert "Are.na" in message, "не названы сайты-доски"
assert "Cookies.binarycookies" not in message

# 2) блок со встроенным видео → ссылка на первоисточник
print("2) резолвер Are.na:")
CASES = {
    "встроенный YouTube": (
        {"source": {"url": "https://www.youtube.com/watch?v=abc123"}},
        "https://www.youtube.com/watch?v=abc123"),
    "загруженный файл": (
        {"attachment": {"url": "https://arena-attachments.s3.amazonaws.com/x/clip.mp4",
                        "content_type": "video/mp4"}},
        "https://arena-attachments.s3.amazonaws.com/x/clip.mp4"),
    "только iframe": (
        {"embed": {"html": '<iframe src="https://player.vimeo.com/video/76979871" '
                           'frameborder="0"></iframe>'}},
        "https://player.vimeo.com/video/76979871"),
    "iframe без схемы": (
        {"embed": {"html": "<iframe src='//player.vimeo.com/video/1'></iframe>"}},
        "https://player.vimeo.com/video/1"),
    "файл важнее ссылки": (
        {"source": {"url": "https://www.are.na/block/1"},
         "attachment": {"url": "https://cdn/x.mp4", "content_type": "video/mp4"}},
        "https://cdn/x.mp4"),
}
requested = []


def fake_fetch(url, proxy=None, timeout=20):      # noqa: ARG001
    requested.append(url)
    return payload


saved_fetch = dl._fetch_json
dl._fetch_json = fake_fetch
try:
    for label, (payload, expected) in CASES.items():
        got = dl.resolve_arena("https://www.are.na/block/20345333")
        print(f"   {label}: {got}")
        assert got == expected, f"{label}: получили {got}"
    assert requested[0] == "https://api.are.na/v2/blocks/20345333", \
        f"не тот адрес API: {requested[0]}"

    # 3) картинка или текст — подменять нечем, адрес остаётся прежним
    payload = {"class": "Image", "image": {"original": {"url": "https://cdn/x.jpg"}}}
    notes = []
    assert dl.resolve_arena("https://www.are.na/block/1") is None
    assert dl.resolve_url("https://www.are.na/block/1", None, notes.append) == \
        "https://www.are.na/block/1"
    print("3) картинка: " + notes[-1])
    assert "нет видео" in notes[-1]

    # 4) API недоступно — не падаем, качаем как раньше
    def boom(url, proxy=None, timeout=20):        # noqa: ARG001
        raise OSError("сеть недоступна")

    dl._fetch_json = boom
    notes.clear()
    assert dl.resolve_url("https://are.na/blocks/777", None, notes.append) == \
        "https://are.na/blocks/777"
    print("4) API недоступно: " + notes[-1])
    assert "не удалось узнать" in notes[-1]
finally:
    dl._fetch_json = saved_fetch

# 5) чужих ссылок резолвер не трогает
for other in ("https://www.youtube.com/watch?v=x", "https://vimeo.com/1", ""):
    assert dl.resolve_url(other) == other, f"тронул чужую ссылку: {other}"
assert dl.resolve_arena("https://www.youtube.com/watch?v=x") is None

# 6) финальной ошибкой становится причина, а не отказ доступа к cookies
print("6) выбор финальной ошибки:")
source = Path(dl.__file__).read_text(encoding="utf-8")
assert "final = login_exc or primary_exc or last_exc" in source, \
    "финальная ошибка снова берётся по последней попытке"
print("   ошибка чтения cookies больше не перебивает настоящую причину")

print("OK: Are.na резолвится, неподдерживаемый сайт объясняется понятно")
