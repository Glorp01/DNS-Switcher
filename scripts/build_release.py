from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


APP_NAME = "DNS Switcher"
REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"
BUILD_DIR = REPO_ROOT / "build" / "pyinstaller"
RELEASE_DIR = REPO_ROOT / "release"


def remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()


def run(command: list[str]) -> None:
    print("+", " ".join(str(part) for part in command))
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def current_asset_name() -> str:
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        return "DNS-Switcher-windows-x64.zip"

    if system == "Darwin":
        if machine in {"arm64", "aarch64"}:
            return "DNS-Switcher-macos-apple-silicon.zip"
        return "DNS-Switcher-macos-intel.zip"

    raise SystemExit(f"Unsupported build platform: {system}")


def pyinstaller_command() -> list[str]:
    system = platform.system()
    base = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
    ]

    if system == "Windows":
        return [*base, "--onefile", str(REPO_ROOT / "dns_switcher.pyw")]

    if system == "Darwin":
        return [
            *base,
            "--osx-bundle-identifier",
            "io.github.glorp01.dnsswitcher",
            str(REPO_ROOT / "dns_switcher_app.py"),
        ]

    raise SystemExit(f"Unsupported build platform: {system}")


def archive_windows(asset_path: Path) -> None:
    executable = DIST_DIR / f"{APP_NAME}.exe"
    if not executable.exists():
        raise SystemExit(f"Expected build output was not found: {executable}")

    with zipfile.ZipFile(asset_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(executable, arcname=executable.name)


def archive_macos(asset_path: Path) -> None:
    app_bundle = DIST_DIR / f"{APP_NAME}.app"
    if not app_bundle.exists():
        raise SystemExit(f"Expected build output was not found: {app_bundle}")

    run(
        [
            "ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            str(app_bundle),
            str(asset_path),
        ]
    )


def main() -> int:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        raise SystemExit("Release builds are only supported on Windows and macOS.")

    remove_path(DIST_DIR)
    remove_path(BUILD_DIR)
    remove_path(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    run(pyinstaller_command())

    asset_path = RELEASE_DIR / current_asset_name()
    if system == "Windows":
        archive_windows(asset_path)
    else:
        archive_macos(asset_path)

    print(f"Created release asset: {asset_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
