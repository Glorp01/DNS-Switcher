# DNS Switcher

A small Windows desktop app for switching IPv4 DNS servers on your PC.

It uses:

- `Tkinter` for the UI
- PowerShell to read adapter and DNS state
- Windows DNS commands to apply static DNS or restore automatic DNS

## What it does

- Detects your Windows network adapters
- Shows the current IPv4 DNS mode and active DNS servers
- Applies one-click presets like Cloudflare, Google, Quad9, OpenDNS, AdGuard, and Control D
- Lets you enter your own custom IPv4 DNS servers
- Restores automatic IPv4 DNS from DHCP
- Flushes the DNS cache after a change

## Run it

From this folder:

```powershell
py dns_switcher.pyw
```

Or double-click:

`Launch DNS Switcher.bat`

## Important

- This app is for Windows only.
- Reading adapter info works as a normal user.
- Changing DNS requires administrator privileges.
- If you start it normally, it can relaunch itself with elevation when you try to apply a change.

## Quick smoke test

This does not change your DNS settings:

```powershell
py dns_switcher.pyw --self-test
```
