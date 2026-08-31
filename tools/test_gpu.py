"""Ускорение рендера видеокартой.

Наличие кодировщика в сборке ffmpeg ничего не гарантирует: железа под него на
машине может не быть. Поэтому кодировщик проверяется пробным запуском, а если
он всё-таки отвалится посреди рендера — работа доводится на процессоре.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper import ffmpeg_tools as ft

ffmpeg = ft.ffmpeg_path()
if not ffmpeg:
    print("ffmpeg не найден — пропускаю")
    sys.exit(0)

# 1) список кодировщиков читается, процессорный на месте
names = ft._encoder_names()
print(f"1) кодировщиков в сборке: {len(names)}")
assert "libx264" in names, "не разобрали вывод ffmpeg -encoders"

# 2) проба отсекает то, что есть в сборке, но не работает без железа
print("2) проба кодировщиков:")
assert ft._encoder_works("libx264"), "процессорный кодировщик не прошёл пробу"
for fake in ("h264_v4l2m2m", "h264_vaapi"):
    if fake in names:
        print(f"   {fake}: в сборке есть, проба -> {ft._encoder_works(fake)}")
assert not ft._encoder_works("no_such_encoder"), "несуществующий кодировщик прошёл пробу"

# 3) что нашли на этой машине — просто печатаем: на CI видеокарты нет
found = ft.hw_encoder()
print(f"3) аппаратный H.264: {ft.hw_encoder_label(found) if found else 'не найден'}")
assert found is None or found in names

# 4) у каждого производителя свои ключи, битрейт задаётся всем одинаково
print("4) аргументы кодировщиков:")
for encoder in ("h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox"):
    args = ft._hw_video_args(encoder, 5000)
    print(f"   {ft.hw_encoder_label(encoder):20} {' '.join(args)}")
    assert args[:2] == ["-c:v", encoder]
    assert "-b:v" in args and "5000k" in args, f"{encoder}: не задан битрейт"
    assert "-pix_fmt" in args, f"{encoder}: не задан формат пикселей"
    assert "-preset" not in args or encoder != "h264_videotoolbox"

# 5) в команде экспорта появляется именно аппаратный кодировщик
sandbox = Path(tempfile.mkdtemp(prefix="clipper_gpu_"))
src = sandbox / "src.mp4"
os.system(f'"{ffmpeg}" -y -hide_banner -loglevel error -f lavfi '
          f'-i testsrc=size=320x240:rate=25:duration=4 -f lavfi '
          f'-i sine=frequency=440:duration=4 -c:v libx264 -pix_fmt yuv420p '
          f'-c:a aac -shortest "{src}"')
assert src.exists(), "не удалось подготовить тестовое видео"

cmd = ft.build_export_command(src, sandbox / "gpu.mp4",
                              ft.ExportSettings(1, 3, hw_encoder="h264_nvenc"))
print("5) команда с ускорением:", " ".join(cmd[cmd.index("-t") + 2:])[:96], "…")
assert "h264_nvenc" in cmd and "libx264" not in cmd
assert "-preset" in cmd and "p5" in cmd, "не подставлены настройки NVENC"

# без ускорения — как раньше, процессорный кодировщик со своим preset
cmd = ft.build_export_command(src, sandbox / "cpu.mp4",
                              ft.ExportSettings(1, 3, preset="slow"))
assert "libx264" in cmd and "slow" in cmd and "h264_nvenc" not in cmd

# 6) ускорение только для H.264: у VP9 и MP3 его нет
for container in (ft.FORMAT_WEBM, ft.FORMAT_MP3):
    cmd = ft.build_export_command(src, sandbox / f"x{container}",
                                  ft.ExportSettings(1, 3, container=container,
                                                    hw_encoder="h264_nvenc"))
    assert "h264_nvenc" not in cmd, f"{container}: подставили аппаратный H.264"
print("6) WebM и MP3 ускорение не трогает")

# 7) кодировщик отвалился — рендер доводится на процессоре, файл всё равно есть
notes: list = []
broken = "h264_v4l2m2m" if "h264_v4l2m2m" in names else "h264_nvenc"
out = ft.export_clip(src, sandbox / "fallback.mp4",
                     ft.ExportSettings(1, 3, video_bitrate=800, hw_encoder=broken),
                     on_log=notes.append)
print(f"7) откат на процессор: файл {out.stat().st_size / 1024:.0f} КБ")
assert out.exists() and out.stat().st_size > 0, "после отката файла нет"
assert any("процессоре" in n for n in notes), "об откате не сообщили"
info = ft.probe(out)
assert abs(info.duration - 2.0) < 0.3, f"длительность не та: {info.duration:.2f} с"

# 8) битрейт можно вписать руками — разными способами
print("8) разбор битрейта:")
CASES = {
    "6": 6000, "6,5": 6500, "6.5": 6500,          # без суффикса — мегабиты
    "5 Мбит/с": 5000, "5 Mbps": 5000, "12M": 12000,
    "6000": 6000, "6000k": 6000, "6000 кбит/с": 6000,
    "": 0, "абв": 0, "0": 0,                       # мусор и ноль — авто
    "99999999": 0, "50": 50000,                    # вне диапазона и верхняя граница
}
for text, expected in CASES.items():
    got = ft.parse_bitrate(text)
    assert got == expected, f"{text!r}: ожидали {expected}, получили {got}"
print(f"   разобрано вариантов: {len(CASES)}")

# подписи из списка разбираются в те же значения, что в них заявлены
for label, value in (("1,5 Мбит/с — экономно", 1500), ("20 Мбит/с — максимум", 20000),
                     ("Авто (по разрешению)", 0)):
    assert ft.parse_bitrate(label) == value, f"пункт списка {label!r} разобран неверно"

# вписанное значение доезжает до команды ffmpeg
cmd = ft.build_export_command(src, sandbox / "manual.mp4",
                              ft.ExportSettings(1, 3, video_bitrate=ft.parse_bitrate("6,5")))
assert "6500k" in cmd, "ручной битрейт не попал в команду"
print("   «6,5» -> 6500k в команде ffmpeg")

print("OK: видеокарта проверяется пробой, аргументы верные, откат работает, "
      "битрейт вводится вручную")
