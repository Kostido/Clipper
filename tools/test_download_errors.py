"""Разбор ошибок скачивания: что показываем и что пробуем.

Повод: Vimeo отвечает 403 и в тексте отказа сам упоминает «VPN/proxy». Из-за
подстроки «proxy» программа принимала это за обрыв на системном прокси и
советовала запустить VPN-клиент — хотя соединение было, а забанен адрес.
"""
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper import downloader as dl

VIMEO_403 = RuntimeError(
    'ERROR: [vimeo] 1217890213: Got HTTP Error 403 when using impersonate target '
    '"chrome-146:macos-26". If you are using a data center IP or VPN/proxy, your IP '
    'may be blocked; please report this issue on https://github.com/yt-dlp/yt-dlp/issues'
)
DEAD_PROXY = RuntimeError(
    "Unable to download webpage: <urlopen error Failed to connect to 127.0.0.1 port "
    "10809 after 2049 ms: Could not connect to server> (caused by ProxyError())"
)
REFUSED = RuntimeError("curl: (7) Failed to connect to localhost port 8080: "
                       "Connection refused")

# 1) отказ сайта больше не выдаётся за проблему с прокси
print("1) Vimeo 403:")
assert not dl._looks_like_dead_proxy(VIMEO_403), "403 от сайта принят за мёртвый прокси"
assert dl._looks_like_blocked_ip(VIMEO_403), "не распознан бан адреса"
message = str(dl._friendly_error(VIMEO_403, "https://vimeo.com/1217890213"))
print("   " + message.splitlines()[0])
assert "заблокирован адрес" in message
assert "другую страну или другой сервер" in message
assert "Параметры → Сеть и Интернет" not in message, "остался совет про системный прокси"
assert "cookies.txt" in message, "нет пути через cookies"

# 2) настоящий мёртвый прокси распознаётся как раньше
print("2) мёртвый прокси:")
for exc in (DEAD_PROXY, REFUSED):
    assert dl._looks_like_dead_proxy(exc), f"не распознан прокси: {exc}"
    assert not dl._looks_like_blocked_ip(exc)
proxy_message = str(dl._friendly_error(DEAD_PROXY, "https://vimeo.com/1"))
print("   " + proxy_message.splitlines()[0])
assert "системный прокси" in proxy_message

# 3) при 403 пробуем представиться другим браузером
print("3) меры обхода:")
names = [name for name, *_ in dl._MITIGATIONS]
print("   порядок мер:", ", ".join(names))
for expected in ("as_safari", "as_firefox", "as_edge"):
    assert expected in names, f"нет меры {expected}"
assert names.index("as_safari") < names.index("retry_fresh"), "смена браузера идёт слишком поздно"

targets = dl._impersonate_targets()
print(f"   целей имперсонации доступно: {len(targets)}")
if not targets:
    print("   curl_cffi не установлен — проверку подстановки пропускаю")
else:
    for name, _msg, apply, when in dl._MITIGATIONS:
        if name != "as_safari":
            continue
        assert when(VIMEO_403, "https://vimeo.com/1"), "мера не сработала на 403"
        assert not when(DEAD_PROXY, "https://vimeo.com/1"), "мера сработала не на 403"
        opts = {}
        with contextlib.ExitStack() as stack:
            apply(opts, stack)
        chosen = str(opts["impersonate"])
        print("   подставлена цель:", chosen)
        assert chosen.startswith("safari"), "цель не сменилась на Safari"
        assert ":macos" in chosen or ":windows" in chosen, \
            "выбрана мобильная цель — сайт отдаст мобильную вёрстку"
    # цель, на которой пользователь получил отказ, среди запасных не повторяется
    fallbacks = []
    for name, _msg, apply, _when in dl._MITIGATIONS:
        if not name.startswith("as_"):
            continue
        opts = {}
        with contextlib.ExitStack() as stack:
            apply(opts, stack)
        fallbacks.append(str(opts.get("impersonate")))
    print("   запасные цели:", ", ".join(fallbacks))
    assert "chrome-146:macos-26" not in fallbacks, "пробуем ту же цель, что уже отказала"
    assert len(set(fallbacks)) == len(fallbacks), "цели повторяются"

# 4) недоступную цель не подставляем — иначе yt-dlp падает до запроса
assert dl._impersonate_like("netscape-1") is None

print("OK: 403 от сайта разбирается верно, прокси-диагностика на месте, "
      "смена браузера включена")
