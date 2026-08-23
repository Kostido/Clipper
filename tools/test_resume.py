"""Длинные ролики: обрыв связи не должен убивать загрузку.

Часовое видео — это сотни мегабайт и десятки минут связи, и на таком сроке
канал (особенно через VPN) рвётся регулярно: WinError 10054, таймаут
TLS-рукопожатия, EOF посреди чтения. Раньше yt-dlp сдавался после пяти
попыток, а наши меры обхода такой случай не покрывали вовсе.
"""
import contextlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper import downloader as dl

DROPS = {
    "WinError 10054": RuntimeError(
        "[download] Got error: [WinError 10054] Удаленный хост принудительно "
        "разорвал существующее подключение. Giving up after 5 retries"),
    "таймаут рукопожатия": RuntimeError(
        "[download] Got error: _ssl.c:993: The handshake operation timed out. "
        "Giving up after 5 retries"),
    "обрыв чтения": RuntimeError(
        "ERROR: [youtube] Ole5nMVFLak: Unable to download API page: "
        "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"),
}

# 1) все три обрыва распознаются
print("1) распознавание обрывов:")
for label, exc in DROPS.items():
    assert dl._looks_like_connection_drop(exc), f"не распознан обрыв: {label}"
    print(f"   {label}: да")
assert not dl._looks_like_connection_drop(RuntimeError("HTTP Error 404: Not Found"))
assert not dl._looks_like_connection_drop(RuntimeError("Video is DRM protected"))

# 2) на обрыв выбирается докачка, и её можно применить несколько раз подряд
print("2) повторы докачки:")
exc = DROPS["WinError 10054"]
applied: dict = {}
picked = []
while True:
    fix = dl._pick_mitigation(exc, "https://youtube.com/watch?v=x", applied)
    if not fix or fix[0] != "resume":
        break
    name, _msg, _apply = fix
    applied[name] = applied.get(name, 0) + 1
    picked.append(name)
print(f"   докачку выбрали {len(picked)} раз(а), лимит {dl.RESUME_ATTEMPTS}")
assert len(picked) == dl.RESUME_ATTEMPTS, "лимит повторов не соблюдается"

# исчерпав докачку, программа не зацикливается
assert dl._pick_mitigation(exc, "https://youtube.com/watch?v=x", applied) is None, \
    "после исчерпания попыток мера всё ещё предлагается"

# 3) со второго раза режим щадящий: мелкие куски и одно соединение
print("3) щадящий режим:")
dl.RESUME_PAUSE, saved_pause = 0.0, dl.RESUME_PAUSE   # в тесте не спим
try:
    opts = {"http_chunk_size": 10 * 1024 * 1024, "concurrent_fragment_downloads": 4}
    with contextlib.ExitStack() as stack:
        dl._fix_resume(opts, stack)
        print(f"   после 1-го: кусок={opts['http_chunk_size'] // 1024} КБ, "
              f"потоков={opts['concurrent_fragment_downloads']}")
        assert opts["continuedl"] is True, "докачка не включена"
        assert opts["http_chunk_size"] == 10 * 1024 * 1024, "режим сменился слишком рано"
        dl._fix_resume(opts, stack)
    print(f"   после 2-го: кусок={opts['http_chunk_size'] // 1024} КБ, "
          f"потоков={opts['concurrent_fragment_downloads']}")
    assert opts["http_chunk_size"] == 1024 * 1024, "кусок не уменьшился"
    assert opts["concurrent_fragment_downloads"] == 1, "соединения не сокращены"
    assert opts["_resume_attempt"] == 2
finally:
    dl.RESUME_PAUSE = saved_pause

# 4) пауза перед повтором действительно выдерживается
print("4) пауза перед повтором:")
dl.RESUME_PAUSE, saved_pause = 0.2, dl.RESUME_PAUSE
try:
    started = time.monotonic()
    with contextlib.ExitStack() as stack:
        dl._fix_resume({}, stack)
    waited = time.monotonic() - started
    print(f"   подождали {waited:.2f} с")
    assert waited >= 0.19, "повтор идёт без паузы — канал не успеет очнуться"
finally:
    dl.RESUME_PAUSE = saved_pause

# 5) сообщение объясняет, что докачка продолжится
print("5) сообщение об ошибке:")
exc = DROPS["таймаут рукопожатия"]
dl._remember_applied(exc, {"resume": 6})
message = str(dl._friendly_error(exc, "https://www.youtube.com/watch?v=Ole5nMVFLak"))
print("   " + message.splitlines()[0])
assert "Связь обрывается" in message
assert "продолжит с того же места" in message, "не сказано про докачку"
assert "6 раз" in message, "не показано число уже сделанных попыток"
assert "Системный прокси" not in message, "обрыв связи приписан прокси"

# 6) настройки терпения подняты — на длинном файле пяти попыток мало
print("6) терпение yt-dlp:")
import inspect

source = inspect.getsource(dl.download)
for option in ('"retries": 20', '"fragment_retries": 20', '"socket_timeout": 30'):
    assert option in source, f"не выставлено {option}"
print("   retries=20, fragment_retries=20, socket_timeout=30")

print("OK: обрыв связи распознаётся, докачка повторяется, сообщение объясняет")
