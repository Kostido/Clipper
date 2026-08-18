"""Проверка подмены программы при обновлении, без обращения к сети.

Запуск: python tools/test_self_update.py
На macOS собирает игрушечный Clipper.app, архивирует его как релиз и
прогоняет apply_update: новая версия должна встать на место старой,
старая — сохраниться рядом, а cleanup_old — убрать её.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper import updater  # noqa: E402


def _fake_bundle(root: Path, marker: str) -> Path:
    """Минимальный .app: исполняемый файл и Info.plist."""
    bundle = root / "Clipper.app"
    macos = bundle / "Contents" / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)
    binary = macos / "Clipper"
    binary.write_text(f"#!/bin/sh\necho {marker}\n", encoding="utf-8")
    binary.chmod(0o755)
    (bundle / "Contents" / "Info.plist").write_text(marker, encoding="utf-8")
    return bundle


def main() -> int:
    if sys.platform != "darwin":
        print("Тест рассчитан на macOS: подмена бандла проверяется там.")
        return 0

    workspace = Path(tempfile.mkdtemp(prefix="clipper-selfupdate-"))
    installed_dir = workspace / "Applications"
    installed_dir.mkdir()
    release_dir = workspace / "release"
    release_dir.mkdir()

    bundle = _fake_bundle(installed_dir, "версия-старая")
    new_bundle = _fake_bundle(release_dir, "версия-новая")

    archive = workspace / "Clipper-macos.zip"
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                    str(new_bundle), str(archive)], check=True)
    shutil.rmtree(release_dir)

    # Подменяем только определение путей — логика обновления остаётся боевой.
    updater.macos_bundle = lambda: bundle
    updater.is_frozen = lambda: True

    print("1) проверка файла релиза")
    updater._verify(archive, archive.stat().st_size)

    print("2) установка обновления")
    result = updater.apply_update(archive)
    assert result == bundle, result
    binary = bundle / "Contents" / "MacOS" / "Clipper"
    assert (bundle / "Contents" / "Info.plist").read_text(encoding="utf-8") == "версия-новая", \
        "новая версия не встала на место"
    assert os.access(binary, os.X_OK), "потеряно право на запуск — приложение не стартует"
    assert (installed_dir / "Clipper.app.old").is_dir(), "старая версия не сохранена"
    print("   новая версия на месте, права сохранены, старая отложена")

    print("3) уборка при следующем запуске")
    updater.cleanup_old()
    assert not (installed_dir / "Clipper.app.old").exists(), "старая версия осталась"

    print("4) битый архив не принимается")
    broken = workspace / "broken.zip"
    broken.write_text("<html>404</html>", encoding="utf-8")
    try:
        updater._verify(broken, 0)
    except updater.UpdateError as exc:
        print(f"   отклонён: {exc}")
    else:
        raise AssertionError("битый архив прошёл проверку")

    shutil.rmtree(workspace, ignore_errors=True)
    print("OK: обновление устанавливается и откатывать нечего")
    return 0


if __name__ == "__main__":
    sys.exit(main())
