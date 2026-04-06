from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


APP_NAME = "DNS Switcher"
APP_SLUG = "DNS-Switcher"
APP_BUNDLE_ID = "io.github.glorp01.dnsswitcher"
WINDOWS_INSTALLER_NAME = f"{APP_SLUG}-Setup-x64.exe"
REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"
BUILD_DIR = REPO_ROOT / "build" / "pyinstaller"
INSTALLER_BUILD_DIR = REPO_ROOT / "build" / "installer"
RELEASE_DIR = REPO_ROOT / "release"
WINDOWS_ISS = REPO_ROOT / "packaging" / "windows" / "dns_switcher.iss"


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


def app_version() -> str:
    source = (REPO_ROOT / "dns_switcher_app.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION = "([^"]+)"$', source, re.MULTILINE)
    if not match:
        raise SystemExit("Could not determine APP_VERSION from dns_switcher_app.py.")
    return match.group(1)


def current_asset_name() -> str:
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        return WINDOWS_INSTALLER_NAME

    if system == "Darwin":
        if machine in {"arm64", "aarch64"}:
            return f"{APP_SLUG}-macos-apple-silicon.dmg"
        return f"{APP_SLUG}-macos-intel.dmg"

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
            APP_BUNDLE_ID,
            str(REPO_ROOT / "dns_switcher_app.py"),
        ]

    raise SystemExit(f"Unsupported build platform: {system}")


def find_inno_setup_compiler() -> str:
    candidates = [
        shutil.which("iscc"),
        shutil.which("ISCC"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise SystemExit("Inno Setup compiler was not found. Install Inno Setup 6 or run the GitHub Actions workflow on Windows.")


def build_windows_installer(asset_path: Path) -> None:
    executable = DIST_DIR / f"{APP_NAME}.exe"
    if not executable.exists():
        raise SystemExit(f"Expected build output was not found: {executable}")

    compiler = find_inno_setup_compiler()
    command = [
        compiler,
        f"/DMyAppVersion={app_version()}",
        f"/DMyAppExe={executable}",
        f"/DMyOutputDir={RELEASE_DIR}",
        f"/DMyOutputBaseFilename={asset_path.stem}",
        str(WINDOWS_ISS),
    ]
    run(command)


def build_macos_dmg(asset_path: Path) -> None:
    app_bundle = DIST_DIR / f"{APP_NAME}.app"
    if not app_bundle.exists():
        raise SystemExit(f"Expected build output was not found: {app_bundle}")

    staging_dir = INSTALLER_BUILD_DIR / "dmg-staging"
    remove_path(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    app_copy = staging_dir / app_bundle.name
    shutil.copytree(app_bundle, app_copy)

    applications_link = staging_dir / "Applications"
    if applications_link.exists() or applications_link.is_symlink():
        applications_link.unlink()
    applications_link.symlink_to("/Applications")

    run(
        [
            "hdiutil",
            "create",
            "-volname",
            APP_NAME,
            "-srcfolder",
            str(staging_dir),
            "-ov",
            "-format",
            "UDZO",
            str(asset_path),
        ]
    )


def main() -> int:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        raise SystemExit("Release builds are only supported on Windows and macOS.")

    remove_path(DIST_DIR)
    remove_path(BUILD_DIR)
    remove_path(INSTALLER_BUILD_DIR)
    remove_path(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    run(pyinstaller_command())

    asset_path = RELEASE_DIR / current_asset_name()
    if system == "Windows":
        build_windows_installer(asset_path)
    else:
        build_macos_dmg(asset_path)

    if not asset_path.exists():
        raise SystemExit(f"Release asset was not created: {asset_path}")

    print(f"Created release asset: {asset_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
