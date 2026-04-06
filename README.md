# DNS Switcher

`DNS Switcher` is a small cross-platform desktop app for switching IPv4 DNS settings on Windows and macOS.

It now includes:

- A cleaner dashboard-style Tkinter UI
- A built-in activity console for recent actions
- Windows adapter support through PowerShell + `netsh`
- macOS network service support through `networksetup`
- One-click public DNS presets plus custom IPv4 DNS entry

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

No third-party Python packages are required.

## Run It

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

## Optional Install

You can also install it as a local package from this folder:

```bash
pip install .
```

Then launch it with:

```bash
dns-switcher
```

## Permission Model

- Windows: reading adapter info works as a normal user. Applying DNS changes requires administrator rights, and the app can relaunch itself with UAC.
- macOS: reading service info works as a normal user. Applying DNS changes uses the system administrator password prompt through AppleScript.

## Quick Smoke Test

This only inspects available adapters/services and prints JSON.

Windows:

```powershell
py dns_switcher.pyw --self-test
```

macOS:

```bash
python3 dns_switcher_app.py --self-test
```

## Project Layout

- `dns_switcher_app.py` contains the main cross-platform app
- `dns_switcher.pyw` is a thin Windows launcher wrapper
- `pyproject.toml` makes the repo easier to install and share on GitHub
