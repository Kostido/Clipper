"""Разбор и печать таймкодов вида ЧЧ:ММ:СС.ммм."""
from __future__ import annotations

import re

_RE = re.compile(r"^\s*(?:(\d+):)?(?:(\d+):)?(\d+(?:[.,]\d+)?)\s*$")


def format_tc(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs:06.3f}"


def parse_tc(text: str) -> float | None:
    """Понимает '12.5', '1:05', '01:02:03.250'. None — если строка мусорная."""
    m = _RE.match(text or "")
    if not m:
        return None
    a, b, c = m.groups()
    secs = float(c.replace(",", "."))
    if a is not None and b is not None:
        return int(a) * 3600 + int(b) * 60 + secs
    if a is not None:
        return int(a) * 60 + secs
    return secs
