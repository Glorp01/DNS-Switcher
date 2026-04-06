# DNS Switcher

`DNS Switcher` is a cross-platform desktop app for switching IPv4 DNS settings on Windows and macOS.

It now includes:

- A dashboard-style Tkinter UI
- A built-in activity console
- Windows adapter support through PowerShell + `netsh`
- macOS network service support through `networksetup`
- One-click DNS presets plus custom IPv4 DNS entry
- GitHub release packaging for Windows and macOS

## Features

- Detects Windows adapters or macOS network services
- Shows current DNS mode and the active/manual IPv4 DNS servers it can detect
- Applies presets like Cloudflare, Google, Quad9, OpenDNS, AdGuard, and Control D
- Lets you set custom preferred and alternate IPv4 DNS servers
- Restores automatic DNS from DHCP or system-managed settings
- Flushes the DNS cache after a change when supported

## Requirements

- Python 3.10+
- Tkinter available in your Python install
- Windows or macOS

No third-party runtime Python packages are required.

## Run From Source

Windows:

```powershell
py dns_switcher.pyw
```

Or double-click:

`Launch DNS Switcher.bat`

macOS:

```bash
python3 dns_switcher_app.py
```

Optional macOS source launcher:

```bash
chmod +x "Launch DNS Switcher.command"
open "Launch DNS Switcher.command"
```

## Install The Latest Release

### macOS

Install the latest release from GitHub in Terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/Glorp01/DNS-Switcher/main/installers/install-macos.sh | bash
```

The script downloads the correct release asset for Intel or Apple Silicon and installs `DNS Switcher.app` into `/Applications` when writable, otherwise `~/Applications`.

### Windows

Install the latest release from PowerShell:

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/Glorp01/DNS-Switcher/main/installers/install-windows.ps1 -OutFile install-dns-switcher.ps1
powershell -ExecutionPolicy Bypass -File .\install-dns-switcher.ps1
```

That downloads the latest Windows release asset and installs `DNS Switcher.exe` into `%LOCALAPPDATA%\DNS Switcher`.

## Optional Python Install

You can also install it as a local Python package:

```bash
python3 -m pip install .
```

Then launch it with:

```bash
dns-switcher
```

## Permission Model

- Windows: reading adapter info works as a normal user. Applying DNS changes requires administrator rights, and the app can relaunch itself with UAC.
- macOS: reading service info works as a normal user. Applying DNS changes uses the system administrator password prompt through AppleScript.

## Quick Smoke Test

This only inspects available adapters or services and prints JSON.

Windows:

```powershell
py dns_switcher.pyw --self-test
```

macOS:

```bash
python3 dns_switcher_app.py --self-test
```

## GitHub Release Workflow

This repo includes a GitHub Actions workflow at `.github/workflows/release.yml`.

It builds:

- `DNS-Switcher-windows-x64.zip`
- `DNS-Switcher-macos-intel.zip`
- `DNS-Switcher-macos-apple-silicon.zip`

To publish downloadable assets on GitHub:

```bash
git tag v2.0.0
git push origin v2.0.0
```

Pushing a tag that starts with `v` triggers the workflow and uploads the release files to the matching GitHub release.

## Local Release Build

If you want to build release assets yourself:

```bash
python3 -m pip install -r requirements-build.txt
python3 scripts/build_release.py
```

The packaged asset is written into the `release/` directory.

## Project Layout

- `dns_switcher_app.py` contains the main cross-platform app
- `dns_switcher.pyw` is the Windows launcher wrapper
- `Launch DNS Switcher.command` is a simple macOS source launcher
- `scripts/build_release.py` creates packaged release assets
- `installers/` contains terminal install scripts for GitHub releases
- `.github/workflows/release.yml` builds Windows and macOS release files
