from __future__ import annotations

import argparse
import ctypes
import ipaddress
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import messagebox, ttk


APP_TITLE = "DNS Switcher"
APP_VERSION = "2.0.0"
APP_SUBTITLE = "Cross-platform IPv4 DNS dashboard for Windows and macOS"
WINDOW_SIZE = "1200x820"

BACKGROUND = "#EEF4F3"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F6FAF9"
HEADER_BG = "#123B46"
ACCENT = "#0F766E"
ACCENT_DARK = "#115E59"
OUTLINE = "#D6E1DF"
TEXT = "#12212C"
MUTED = "#5F6B76"
SUCCESS_BG = "#D1FAE5"
SUCCESS_FG = "#065F46"
WARNING_BG = "#FEF3C7"
WARNING_FG = "#92400E"
INFO_BG = "#DBEAFE"
INFO_FG = "#1D4ED8"
CONSOLE_BG = "#0F172A"
CONSOLE_TEXT = "#E2E8F0"

IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"
BODY_FONT = "Segoe UI" if IS_WINDOWS else "Avenir Next" if IS_MACOS else "Helvetica"
MONO_FONT = "Cascadia Code" if IS_WINDOWS else "SF Mono" if IS_MACOS else "Courier"

POWERSHELL = (
    shutil.which("powershell.exe")
    or shutil.which("pwsh.exe")
    or shutil.which("pwsh")
    or shutil.which("powershell")
)
NETWORKSETUP = shutil.which("networksetup") or "/usr/sbin/networksetup"
SCUTIL = shutil.which("scutil") or "/usr/sbin/scutil"
IFCONFIG = shutil.which("ifconfig") or "/sbin/ifconfig"
OSASCRIPT = shutil.which("osascript") or "/usr/bin/osascript"
DSCACHEUTIL = shutil.which("dscacheutil") or "/usr/bin/dscacheutil"
KILLALL = shutil.which("killall") or "/usr/bin/killall"
SHELL_BIN = shutil.which("sh") or "/bin/sh"


class BackendError(RuntimeError):
    """Raised when system DNS commands fail."""


@dataclass(frozen=True)
class DnsPreset:
    name: str
    primary: str
    secondary: str
    description: str

    @property
    def servers(self) -> list[str]:
        return [server for server in (self.primary, self.secondary) if server]

    @property
    def summary(self) -> str:
        return " / ".join(self.servers)


@dataclass
class AdapterInfo:
    identifier: str
    alias: str
    status: str
    description: str
    device: str
    dns_mode: str
    active_servers: list[str]
    manual_servers: list[str]
    dhcp_servers: list[str]

    @property
    def current_servers(self) -> list[str]:
        if self.dns_mode == "Manual" and self.manual_servers:
            return self.manual_servers
        if self.dns_mode == "Automatic" and self.dhcp_servers:
            return self.dhcp_servers
        return self.active_servers


@dataclass(frozen=True)
class MacServiceRecord:
    name: str
    hardware_port: str
    device: str
    disabled: bool


PRESETS = [
    DnsPreset("Cloudflare", "1.1.1.1", "1.0.0.1", "Fast public DNS"),
    DnsPreset("Google", "8.8.8.8", "8.8.4.4", "Widely available"),
    DnsPreset("Quad9", "9.9.9.9", "149.112.112.112", "Security-focused"),
    DnsPreset("OpenDNS", "208.67.222.222", "208.67.220.220", "Cisco public DNS"),
    DnsPreset("AdGuard", "94.140.14.14", "94.140.15.15", "Blocks many ads"),
    DnsPreset("Control D", "76.76.2.0", "76.76.10.0", "Privacy-friendly"),
]


def normalize_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in normalize_json_list(value) if str(item).strip()]


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def validate_ipv4(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("DNS server values cannot be empty.")
    try:
        return str(ipaddress.IPv4Address(value))
    except ipaddress.AddressValueError as exc:
        raise ValueError(f"'{value}' is not a valid IPv4 address.") from exc


def is_ipv4_value(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).version == 4
    except ValueError:
        return False


def run_command(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise BackendError(str(exc)) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Unknown command failure").strip()
        raise BackendError(detail)
    return result.stdout.strip()


def run_powershell(script: str) -> str:
    if not POWERSHELL:
        raise BackendError("PowerShell is not available on this system.")
    return run_command([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])


def run_powershell_json(script: str) -> Any:
    output = run_powershell(script)
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise BackendError(f"Failed to parse PowerShell output: {output}") from exc


def command_to_shell(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def run_shell_script(script: str) -> str:
    return run_command([SHELL_BIN, "-lc", script])


def run_applescript_admin(script: str) -> str:
    if not (Path(OSASCRIPT).exists() or shutil.which("osascript")):
        raise BackendError("osascript is required on macOS to request administrator access.")
    applescript = f'do shell script "{escape_applescript(script)}" with administrator privileges'
    return run_command([OSASCRIPT, "-e", applescript])


def is_windows_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    script_path = Path(__file__).resolve()
    params = subprocess.list2cmdline([str(script_path), *sys.argv[1:]])
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        params,
        str(script_path.parent),
        1,
    )
    return result > 32


class PlatformBackend:
    platform_label = "Unsupported"
    entity_label = "connection"
    entity_label_plural = "connections"
    supports_self_relaunch = False

    def is_elevated(self) -> bool:
        return False

    def privilege_badge(self) -> tuple[str, str, str]:
        return ("Read-only session", WARNING_BG, WARNING_FG)

    def privilege_hint(self) -> str:
        return "Administrator rights are required to apply DNS changes."

    def load_adapters(self) -> list[AdapterInfo]:
        raise NotImplementedError

    def apply_dns(self, adapter: AdapterInfo, servers: list[str]) -> None:
        raise NotImplementedError

    def reset_dns(self, adapter: AdapterInfo) -> None:
        raise NotImplementedError

    def request_relaunch(self) -> bool:
        return False


class WindowsBackend(PlatformBackend):
    platform_label = "Windows"
    entity_label = "adapter"
    entity_label_plural = "adapters"
    supports_self_relaunch = True

    def is_elevated(self) -> bool:
        return is_windows_admin()

    def privilege_badge(self) -> tuple[str, str, str]:
        if self.is_elevated():
            return ("Administrator session", SUCCESS_BG, SUCCESS_FG)
        return ("Standard session", WARNING_BG, WARNING_FG)

    def privilege_hint(self) -> str:
        if self.is_elevated():
            return "DNS changes will apply directly to the selected Windows adapter."
        return "Apply actions can relaunch the app as administrator through UAC."

    def load_adapters(self) -> list[AdapterInfo]:
        script = r"""
$adapters = Get-NetAdapter |
    Sort-Object @{Expression={if ($_.Status -eq 'Up') {0} else {1}}}, InterfaceAlias

$rows = foreach ($adapter in $adapters) {
    $guid = ([string]$adapter.InterfaceGuid).Trim('{}').ToLower()
    $regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{$guid}"
    $dnsConfig = if (Test-Path $regPath) { Get-ItemProperty -Path $regPath } else { $null }
    $ipv4 = Get-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue

    $manualServers = @()
    if ($dnsConfig -and $dnsConfig.NameServer) {
        $manualServers = @($dnsConfig.NameServer -split '[,\s]+' | Where-Object { $_ })
    }

    $dhcpServers = @()
    if ($dnsConfig -and $dnsConfig.DhcpNameServer) {
        $dhcpServers = @($dnsConfig.DhcpNameServer -split '[,\s]+' | Where-Object { $_ })
    }

    $activeServers = @()
    if ($ipv4 -and $ipv4.ServerAddresses) {
        $activeServers = @($ipv4.ServerAddresses | Where-Object { $_ })
    }

    [pscustomobject]@{
        identifier = [string]$adapter.ifIndex
        alias = $adapter.InterfaceAlias
        status = [string]$adapter.Status
        description = $adapter.InterfaceDescription
        device = [string]$adapter.InterfaceGuid
        dns_mode = if ($manualServers.Count -gt 0) { "Manual" } elseif ($dhcpServers.Count -gt 0) { "Automatic" } else { "Unknown" }
        active_servers = $activeServers
        manual_servers = $manualServers
        dhcp_servers = $dhcpServers
    }
}

$rows | ConvertTo-Json -Compress -Depth 4
"""
        rows = normalize_json_list(run_powershell_json(script))
        adapters: list[AdapterInfo] = []
        for row in rows:
            adapters.append(
                AdapterInfo(
                    identifier=str(row["identifier"]),
                    alias=str(row["alias"]),
                    status=str(row["status"]),
                    description=str(row["description"]),
                    device=str(row["device"]),
                    dns_mode=str(row["dns_mode"]),
                    active_servers=normalize_string_list(row.get("active_servers")),
                    manual_servers=normalize_string_list(row.get("manual_servers")),
                    dhcp_servers=normalize_string_list(row.get("dhcp_servers")),
                )
            )
        return adapters

    def apply_dns(self, adapter: AdapterInfo, servers: list[str]) -> None:
        run_command(
            [
                "netsh",
                "interface",
                "ipv4",
                "set",
                "dnsservers",
                f"name={adapter.identifier}",
                "source=static",
                f"address={servers[0]}",
                "validate=yes",
            ]
        )
        for order, server in enumerate(servers[1:], start=2):
            run_command(
                [
                    "netsh",
                    "interface",
                    "ipv4",
                    "add",
                    "dnsservers",
                    f"name={adapter.identifier}",
                    f"address={server}",
                    f"index={order}",
                    "validate=yes",
                ]
            )
        self._flush_dns_cache()

    def reset_dns(self, adapter: AdapterInfo) -> None:
        run_command(
            [
                "netsh",
                "interface",
                "ipv4",
                "set",
                "dnsservers",
                f"name={adapter.identifier}",
                "source=dhcp",
            ]
        )
        self._flush_dns_cache()

    def request_relaunch(self) -> bool:
        return relaunch_as_admin()

    def _flush_dns_cache(self) -> None:
        try:
            run_command(["ipconfig", "/flushdns"])
        except BackendError:
            pass


class MacOSBackend(PlatformBackend):
    platform_label = "macOS"
    entity_label = "service"
    entity_label_plural = "services"

    def is_elevated(self) -> bool:
        return hasattr(os, "geteuid") and os.geteuid() == 0

    def privilege_badge(self) -> tuple[str, str, str]:
        if self.is_elevated():
            return ("Root session", SUCCESS_BG, SUCCESS_FG)
        return ("Admin prompt on apply", INFO_BG, INFO_FG)

    def privilege_hint(self) -> str:
        if self.is_elevated():
            return "DNS changes will run directly against the selected macOS service."
        return "Applying changes uses the macOS administrator password prompt through AppleScript."

    def load_adapters(self) -> list[AdapterInfo]:
        services = self._list_services()
        active_by_device = self._load_active_dns_by_device()
        adapters: list[AdapterInfo] = []

        for service in services:
            manual_servers = self._manual_dns_servers(service.name)
            active_servers = manual_servers or active_by_device.get(service.device, [])
            dhcp_servers = [] if manual_servers else active_servers
            dns_mode = "Manual" if manual_servers else "Automatic"
            status = "Disabled" if service.disabled else self._interface_status(service.device)
            description_parts = [part for part in (service.hardware_port, service.device) if part]
            description = " • ".join(description_parts) if description_parts else "macOS network service"
            adapters.append(
                AdapterInfo(
                    identifier=service.name,
                    alias=service.name,
                    status=status,
                    description=description,
                    device=service.device,
                    dns_mode=dns_mode,
                    active_servers=active_servers,
                    manual_servers=manual_servers,
                    dhcp_servers=dhcp_servers,
                )
            )
        return adapters

    def apply_dns(self, adapter: AdapterInfo, servers: list[str]) -> None:
        set_dns = [NETWORKSETUP, "-setdnsservers", adapter.identifier, *servers]
        self._run_admin_sequence([set_dns], include_flush=True)

    def reset_dns(self, adapter: AdapterInfo) -> None:
        reset_dns = [NETWORKSETUP, "-setdnsservers", adapter.identifier, "Empty"]
        self._run_admin_sequence([reset_dns], include_flush=True)

    def _list_services(self) -> list[MacServiceRecord]:
        service_order = self._service_order_map()
        output = run_command([NETWORKSETUP, "-listallnetworkservices"])
        services: list[MacServiceRecord] = []

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("An asterisk"):
                continue
            disabled = line.startswith("*")
            name = line.lstrip("*").strip()
            hardware_port, device = service_order.get(name, ("", ""))
            services.append(
                MacServiceRecord(
                    name=name,
                    hardware_port=hardware_port,
                    device=device,
                    disabled=disabled,
                )
            )
        return services

    def _service_order_map(self) -> dict[str, tuple[str, str]]:
        output = run_command([NETWORKSETUP, "-listnetworkserviceorder"])
        mapping: dict[str, tuple[str, str]] = {}
        current_name = ""

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("An asterisk"):
                continue

            name_match = re.match(r"^\(\d+\)\s+(.*)$", line)
            if name_match:
                current_name = name_match.group(1).lstrip("*").strip()
                continue

            device_match = re.match(r"^\(Hardware Port:\s*(.*),\s*Device:\s*([^)]+)\)$", line)
            if device_match and current_name:
                mapping[current_name] = (device_match.group(1).strip(), device_match.group(2).strip())
        return mapping

    def _manual_dns_servers(self, service_name: str) -> list[str]:
        output = run_command([NETWORKSETUP, "-getdnsservers", service_name])
        automatic_markers = (
            "There aren't any DNS Servers set on",
            "DNS is not supported",
            "Empty",
        )
        if any(marker in output for marker in automatic_markers):
            return []
        servers = [line.strip() for line in output.splitlines() if is_ipv4_value(line.strip())]
        return dedupe_preserve_order(servers)

    def _load_active_dns_by_device(self) -> dict[str, list[str]]:
        output = run_command([SCUTIL, "--dns"])
        by_device: dict[str, list[str]] = {}
        current_device = ""
        current_servers: list[str] = []

        def commit() -> None:
            if current_device and current_servers:
                existing = by_device.setdefault(current_device, [])
                for server in current_servers:
                    if server not in existing:
                        existing.append(server)

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if line.startswith("resolver #"):
                commit()
                current_device = ""
                current_servers = []
                continue
            if line.startswith("if_index :"):
                match = re.search(r"\(([^)]+)\)", line)
                if match:
                    current_device = match.group(1).strip()
                continue
            if "nameserver[" not in line:
                continue
            _, value = line.split(":", 1)
            candidate = value.strip()
            if is_ipv4_value(candidate):
                current_servers.append(candidate)

        commit()
        return by_device

    def _interface_status(self, device: str) -> str:
        if not device:
            return "Unknown"
        try:
            output = run_command([IFCONFIG, device])
        except BackendError:
            return "Unknown"

        match = re.search(r"status:\s+([A-Za-z]+)", output)
        if not match:
            if "UP" in output:
                return "Available"
            return "Unknown"

        value = match.group(1).lower()
        status_map = {
            "active": "Connected",
            "inactive": "Inactive",
        }
        return status_map.get(value, value.capitalize())

    def _run_admin_sequence(self, commands: list[list[str]], include_flush: bool = False) -> None:
        segments = [command_to_shell(command) for command in commands]
        if include_flush:
            segments.append(f"({command_to_shell([DSCACHEUTIL, '-flushcache'])} || true)")
            segments.append(f"({command_to_shell([KILLALL, '-HUP', 'mDNSResponder'])} || true)")
        script = " && ".join(segments)

        if self.is_elevated():
            run_shell_script(script)
            return
        run_applescript_admin(script)


def create_backend() -> PlatformBackend:
    if IS_WINDOWS:
        return WindowsBackend()
    if IS_MACOS:
        return MacOSBackend()
    raise SystemExit(f"{APP_TITLE} currently supports Windows and macOS only.")


def self_test(backend: PlatformBackend) -> int:
    adapters = backend.load_adapters()
    payload = {
        "app": APP_TITLE,
        "version": APP_VERSION,
        "platform": backend.platform_label,
        "elevated": backend.is_elevated(),
        "adapter_count": len(adapters),
        "adapters": [
            {
                "name": adapter.alias,
                "device": adapter.device,
                "status": adapter.status,
                "dns_mode": adapter.dns_mode,
                "servers": adapter.current_servers,
            }
            for adapter in adapters
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


class DNSDashboard:
    def __init__(self, root: tk.Tk, backend: PlatformBackend) -> None:
        self.root = root
        self.backend = backend
        self.root.title(f"{APP_TITLE} {APP_VERSION}")
        self.root.geometry(WINDOW_SIZE)
        self.root.minsize(1020, 720)
        self.root.configure(bg=BACKGROUND)

        self.adapters: list[AdapterInfo] = []
        self.adapter_lookup: dict[str, AdapterInfo] = {}

        self.primary_var = tk.StringVar()
        self.secondary_var = tk.StringVar()
        self.footer_var = tk.StringVar(value="Loading network data...")
        self.selection_name_var = tk.StringVar(value=f"No {backend.entity_label} selected")
        self.selection_description_var = tk.StringVar(value="Select a network entry to inspect its current DNS state.")
        self.selection_status_var = tk.StringVar(value="-")
        self.selection_mode_var = tk.StringVar(value="-")
        self.selection_device_var = tk.StringVar(value="-")
        self.selection_servers_var = tk.StringVar(value="-")
        self.count_var = tk.StringVar(value=f"0 {backend.entity_label_plural}")
        self.subtitle_var = tk.StringVar(value=backend.privilege_hint())

        self._configure_style()
        self._build_ui()
        self.refresh_adapters(initial=True)

    def _configure_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", font=(BODY_FONT, 10))
        style.configure("App.TFrame", background=BACKGROUND)
        style.configure("HeroTitle.TLabel", background=HEADER_BG, foreground="white", font=(BODY_FONT, 28, "bold"))
        style.configure("HeroBody.TLabel", background=HEADER_BG, foreground="#D5E7E5", font=(BODY_FONT, 11))
        style.configure("Footer.TLabel", background=BACKGROUND, foreground=MUTED, font=(BODY_FONT, 10))
        style.configure("Accent.TButton", background=ACCENT, foreground="white", borderwidth=0, padding=(14, 10))
        style.map("Accent.TButton", background=[("active", ACCENT_DARK)])
        style.configure("Outline.TButton", background=SURFACE, foreground=TEXT, bordercolor=OUTLINE, padding=(12, 9))
        style.map("Outline.TButton", background=[("active", SURFACE_ALT)])
        style.configure("Danger.TButton", background=WARNING_FG, foreground="white", borderwidth=0, padding=(14, 10))
        style.map("Danger.TButton", background=[("active", "#7C2D12")])
        style.configure("Dashboard.Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT, rowheight=30, borderwidth=0)
        style.map("Dashboard.Treeview", background=[("selected", "#D7F5F1")], foreground=[("selected", TEXT)])
        style.configure("Dashboard.Treeview.Heading", background=SURFACE_ALT, foreground=MUTED, font=(BODY_FONT, 10, "bold"))
        style.configure("TEntry", fieldbackground="white", padding=8)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=24)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        outer.rowconfigure(2, weight=0)
        outer.rowconfigure(3, weight=0)

        hero = tk.Frame(outer, bg=HEADER_BG, bd=0, highlightthickness=0)
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        hero.columnconfigure(0, weight=1)

        hero_left = tk.Frame(hero, bg=HEADER_BG)
        hero_left.grid(row=0, column=0, sticky="w", padx=22, pady=20)
        ttk.Label(hero_left, text=APP_TITLE, style="HeroTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(hero_left, text=APP_SUBTITLE, style="HeroBody.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(hero_left, textvariable=self.subtitle_var, style="HeroBody.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 0))

        hero_right = tk.Frame(hero, bg=HEADER_BG)
        hero_right.grid(row=0, column=1, sticky="e", padx=22, pady=20)

        self.platform_badge = tk.Label(
            hero_right,
            text=self.backend.platform_label,
            bg="#1E5967",
            fg="white",
            padx=12,
            pady=8,
            font=(BODY_FONT, 10, "bold"),
        )
        self.platform_badge.grid(row=0, column=0, sticky="e")

        self.privilege_badge = tk.Label(
            hero_right,
            text="",
            bg=WARNING_BG,
            fg=WARNING_FG,
            padx=12,
            pady=8,
            font=(BODY_FONT, 10, "bold"),
        )
        self.privilege_badge.grid(row=1, column=0, sticky="e", pady=(10, 0))

        if self.backend.supports_self_relaunch:
            self.relaunch_button = ttk.Button(
                hero_right,
                text="Restart as Administrator",
                style="Outline.TButton",
                command=self.request_relaunch,
            )
            self.relaunch_button.grid(row=2, column=0, sticky="e", pady=(10, 0))
        else:
            self.relaunch_button = None

        content = ttk.Frame(outer, style="App.TFrame")
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=7)
        content.rowconfigure(0, weight=1)

        sidebar_card, sidebar = self._build_card(
            content,
            f"Network {self.backend.entity_label_plural.title()}",
            "Choose where the DNS change should apply.",
        )
        sidebar_card.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(1, weight=1)

        top_row = tk.Frame(sidebar, bg=SURFACE)
        top_row.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top_row.columnconfigure(0, weight=1)
        tk.Label(top_row, textvariable=self.count_var, bg=SURFACE, fg=MUTED, font=(BODY_FONT, 10)).grid(row=0, column=0, sticky="w")
        ttk.Button(top_row, text="Refresh", style="Outline.TButton", command=self.refresh_adapters).grid(row=0, column=1, sticky="e")

        self.adapter_tree = ttk.Treeview(
            sidebar,
            columns=("name", "status", "mode"),
            show="headings",
            selectmode="browse",
            style="Dashboard.Treeview",
        )
        self.adapter_tree.grid(row=1, column=0, sticky="nsew")
        self.adapter_tree.heading("name", text=self.backend.entity_label.title())
        self.adapter_tree.heading("status", text="Status")
        self.adapter_tree.heading("mode", text="DNS Mode")
        self.adapter_tree.column("name", width=180, anchor="w")
        self.adapter_tree.column("status", width=100, anchor="w")
        self.adapter_tree.column("mode", width=100, anchor="w")
        self.adapter_tree.bind("<<TreeviewSelect>>", self._on_adapter_selected)

        tree_scroll = ttk.Scrollbar(sidebar, orient="vertical", command=self.adapter_tree.yview)
        tree_scroll.grid(row=1, column=1, sticky="ns", padx=(8, 0))
        self.adapter_tree.configure(yscrollcommand=tree_scroll.set)

        main = ttk.Frame(content, style="App.TFrame")
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)

        details_card, details = self._build_card(main, "Current Selection", "Live details for the active adapter or service.")
        details_card.grid(row=0, column=0, sticky="ew")
        details.columnconfigure(0, weight=1)
        details.columnconfigure(1, weight=1)

        tk.Label(
            details,
            textvariable=self.selection_name_var,
            bg=SURFACE,
            fg=TEXT,
            font=(BODY_FONT, 20, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(
            details,
            textvariable=self.selection_description_var,
            bg=SURFACE,
            fg=MUTED,
            font=(BODY_FONT, 10),
            anchor="w",
            justify="left",
            wraplength=640,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 14))

        self._build_info_tile(details, "Connection Status", self.selection_status_var, 2, 0)
        self._build_info_tile(details, "DNS Mode", self.selection_mode_var, 2, 1)
        self._build_info_tile(details, "Device", self.selection_device_var, 3, 0)
        self._build_info_tile(details, "Current IPv4 DNS", self.selection_servers_var, 3, 1, wraplength=280)

        actions_row = ttk.Frame(outer, style="App.TFrame")
        actions_row.grid(row=2, column=0, sticky="ew", pady=(20, 0))
        actions_row.columnconfigure(0, weight=1)
        actions_row.columnconfigure(1, weight=1)

        presets_card, presets = self._build_card(actions_row, "Quick Presets", "Choose a public DNS preset for the selected adapter.")
        presets_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        presets.columnconfigure(0, weight=1)
        presets.columnconfigure(1, weight=1)

        for index, preset in enumerate(PRESETS):
            button = tk.Button(
                presets,
                text=f"{preset.name}\n{preset.summary}\n{preset.description}",
                command=lambda chosen=preset: self.apply_preset(chosen),
                bg="#E8F7F4",
                fg=TEXT,
                activebackground="#D1F3EC",
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                justify="left",
                anchor="w",
                padx=14,
                pady=12,
                wraplength=220,
                font=(BODY_FONT, 10, "bold"),
                cursor="hand2",
            )
            row = index // 2
            column = index % 2
            button.grid(row=row, column=column, sticky="nsew", padx=6, pady=6)

        custom_card, custom = self._build_card(actions_row, "Custom DNS", "Type your own IPv4 DNS values, then apply them.")
        custom_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        custom.columnconfigure(0, weight=1)
        custom.columnconfigure(1, weight=1)

        tk.Label(custom, text="Preferred DNS", bg=SURFACE, fg=MUTED, font=(BODY_FONT, 10, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(custom, text="Alternate DNS", bg=SURFACE, fg=MUTED, font=(BODY_FONT, 10, "bold")).grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.primary_entry = ttk.Entry(custom, textvariable=self.primary_var)
        self.primary_entry.grid(row=1, column=0, sticky="ew", pady=(8, 14))
        self.secondary_entry = ttk.Entry(custom, textvariable=self.secondary_var)
        self.secondary_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(8, 14))

        ttk.Button(custom, text="Apply Custom DNS", style="Accent.TButton", command=self.apply_custom).grid(
            row=2, column=0, columnspan=2, sticky="ew"
        )
        ttk.Button(custom, text="Use Current DNS", style="Outline.TButton", command=self.copy_current_to_custom).grid(
            row=3, column=0, sticky="ew", pady=(10, 0)
        )
        ttk.Button(custom, text="Restore Automatic DNS", style="Danger.TButton", command=self.restore_automatic_dns).grid(
            row=3, column=1, sticky="ew", padx=(10, 0), pady=(10, 0)
        )

        console_card, console = self._build_card(outer, "Activity Console", "Recent actions and backend responses.")
        console_card.grid(row=3, column=0, sticky="ew", pady=(20, 0))
        console.columnconfigure(0, weight=1)

        ttk.Button(console, text="Clear Log", style="Outline.TButton", command=self.clear_console).grid(row=0, column=0, sticky="e")
        self.console_text = tk.Text(
            console,
            height=6,
            bg=CONSOLE_BG,
            fg=CONSOLE_TEXT,
            insertbackground=CONSOLE_TEXT,
            relief="flat",
            bd=0,
            wrap="word",
            font=(MONO_FONT, 10),
            padx=12,
            pady=12,
        )
        self.console_text.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.console_text.configure(state="disabled")

        footer = ttk.Label(outer, textvariable=self.footer_var, style="Footer.TLabel")
        footer.grid(row=4, column=0, sticky="ew", pady=(12, 0))

    def _build_card(self, parent: tk.Misc, title: str, subtitle: str) -> tuple[tk.Frame, tk.Frame]:
        card = tk.Frame(parent, bg=SURFACE, highlightbackground=OUTLINE, highlightthickness=1, bd=0)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)
        tk.Label(card, text=title, bg=SURFACE, fg=TEXT, font=(BODY_FONT, 13, "bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=18, pady=(18, 0)
        )
        tk.Label(
            card,
            text=subtitle,
            bg=SURFACE,
            fg=MUTED,
            font=(BODY_FONT, 10),
            anchor="w",
            justify="left",
            wraplength=500,
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(4, 14))
        body = tk.Frame(card, bg=SURFACE)
        body.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))
        body.columnconfigure(0, weight=1)
        return card, body

    def _build_info_tile(
        self,
        parent: tk.Frame,
        title: str,
        variable: tk.StringVar,
        row: int,
        column: int,
        wraplength: int = 220,
    ) -> None:
        tile = tk.Frame(parent, bg=SURFACE_ALT, highlightbackground=OUTLINE, highlightthickness=1, bd=0)
        tile.grid(row=row, column=column, sticky="nsew", padx=(0 if column == 0 else 10, 0), pady=(0, 10))
        tile.columnconfigure(0, weight=1)
        tk.Label(tile, text=title, bg=SURFACE_ALT, fg=MUTED, font=(BODY_FONT, 9, "bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=12, pady=(10, 4)
        )
        tk.Label(
            tile,
            textvariable=variable,
            bg=SURFACE_ALT,
            fg=TEXT,
            font=(BODY_FONT, 11, "bold"),
            anchor="w",
            justify="left",
            wraplength=wraplength,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))

    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.footer_var.set(message)
        self.console_text.configure(state="normal")
        self.console_text.insert("end", f"[{timestamp}] {message}\n")
        self.console_text.see("end")
        self.console_text.configure(state="disabled")

    def clear_console(self) -> None:
        self.console_text.configure(state="normal")
        self.console_text.delete("1.0", "end")
        self.console_text.configure(state="disabled")
        self.footer_var.set("Activity console cleared.")

    def refresh_privilege_banner(self) -> None:
        label, bg, fg = self.backend.privilege_badge()
        self.privilege_badge.configure(text=label, bg=bg, fg=fg)
        self.subtitle_var.set(self.backend.privilege_hint())

    @property
    def selected_adapter(self) -> AdapterInfo | None:
        selection = self.adapter_tree.selection()
        if not selection:
            return None
        return self.adapter_lookup.get(selection[0])

    def refresh_adapters(self, initial: bool = False) -> None:
        self.refresh_privilege_banner()
        previous_selection = self.adapter_tree.selection()
        previous_id = previous_selection[0] if previous_selection else ""

        try:
            self.adapters = self.backend.load_adapters()
        except BackendError as exc:
            messagebox.showerror(APP_TITLE, f"Could not read network {self.backend.entity_label_plural}.\n\n{exc}")
            self.log(f"Failed to load {self.backend.entity_label_plural}: {exc}")
            return

        self.adapter_lookup = {adapter.identifier: adapter for adapter in self.adapters}
        self.count_var.set(f"{len(self.adapters)} {self.backend.entity_label_plural}")

        self.adapter_tree.delete(*self.adapter_tree.get_children())
        for adapter in self.adapters:
            self.adapter_tree.insert(
                "",
                "end",
                iid=adapter.identifier,
                values=(adapter.alias, adapter.status, adapter.dns_mode),
            )

        if not self.adapters:
            self._render_adapter(None)
            self.log(f"No network {self.backend.entity_label_plural} were found.")
            return

        target_id = previous_id if previous_id in self.adapter_lookup else self.adapters[0].identifier
        self.adapter_tree.selection_set(target_id)
        self.adapter_tree.focus(target_id)
        self._render_adapter(self.adapter_lookup[target_id])

        if initial:
            self.log(
                f"Ready on {self.backend.platform_label}. Loaded {len(self.adapters)} {self.backend.entity_label_plural}."
            )
        else:
            self.log(f"Refreshed {len(self.adapters)} {self.backend.entity_label_plural}.")

    def _on_adapter_selected(self, _event: object) -> None:
        self._render_adapter(self.selected_adapter)

    def _render_adapter(self, adapter: AdapterInfo | None) -> None:
        if not adapter:
            self.selection_name_var.set(f"No {self.backend.entity_label} selected")
            self.selection_description_var.set("Select a network entry to inspect its current DNS state.")
            self.selection_status_var.set("-")
            self.selection_mode_var.set("-")
            self.selection_device_var.set("-")
            self.selection_servers_var.set("-")
            return

        servers = ", ".join(adapter.current_servers) if adapter.current_servers else "Automatic / not explicitly reported"
        self.selection_name_var.set(adapter.alias)
        self.selection_description_var.set(adapter.description or f"Selected {self.backend.entity_label}.")
        self.selection_status_var.set(adapter.status)
        self.selection_mode_var.set(adapter.dns_mode)
        self.selection_device_var.set(adapter.device or "System-managed")
        self.selection_servers_var.set(servers)

    def copy_current_to_custom(self) -> None:
        adapter = self.selected_adapter
        if not adapter:
            messagebox.showwarning(APP_TITLE, f"Select a {self.backend.entity_label} first.")
            return

        servers = adapter.current_servers
        self.primary_var.set(servers[0] if len(servers) >= 1 else "")
        self.secondary_var.set(servers[1] if len(servers) >= 2 else "")
        self.log(f"Copied current DNS from {adapter.alias} into the custom fields.")

    def ensure_ready_for_change(self) -> bool:
        if not self.backend.supports_self_relaunch:
            return True
        if self.backend.is_elevated():
            return True

        should_restart = messagebox.askyesno(
            APP_TITLE,
            "Changing DNS on Windows requires administrator privileges.\n\nRestart the app as administrator now?",
        )
        if should_restart and self.request_relaunch():
            self.root.destroy()
        return False

    def request_relaunch(self) -> bool:
        if not self.backend.supports_self_relaunch:
            return False
        if self.backend.is_elevated():
            messagebox.showinfo(APP_TITLE, "The app is already running as administrator.")
            return False
        if self.backend.request_relaunch():
            self.log("Relaunch request sent. Accept the elevation prompt to continue.")
            return True
        messagebox.showwarning(APP_TITLE, "The elevated copy did not start.")
        self.log("Relaunch as administrator was cancelled or failed.")
        return False

    def apply_preset(self, preset: DnsPreset) -> None:
        adapter = self.selected_adapter
        if not adapter:
            messagebox.showwarning(APP_TITLE, f"Select a {self.backend.entity_label} first.")
            return
        if not self.ensure_ready_for_change():
            return

        try:
            self.backend.apply_dns(adapter, preset.servers)
        except BackendError as exc:
            messagebox.showerror(APP_TITLE, f"Could not apply {preset.name}.\n\n{exc}")
            self.log(f"Failed to apply {preset.name} on {adapter.alias}: {exc}")
            return

        self.primary_var.set(preset.primary)
        self.secondary_var.set(preset.secondary)
        self.log(f"Applied {preset.name} to {adapter.alias}.")
        self.refresh_adapters()

    def apply_custom(self) -> None:
        adapter = self.selected_adapter
        if not adapter:
            messagebox.showwarning(APP_TITLE, f"Select a {self.backend.entity_label} first.")
            return
        if not self.ensure_ready_for_change():
            return

        try:
            servers = [validate_ipv4(self.primary_var.get())]
            if self.secondary_var.get().strip():
                secondary = validate_ipv4(self.secondary_var.get())
                if secondary == servers[0]:
                    raise ValueError("Preferred and alternate DNS servers must be different.")
                servers.append(secondary)
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        try:
            self.backend.apply_dns(adapter, servers)
        except BackendError as exc:
            messagebox.showerror(APP_TITLE, f"Could not apply the custom DNS servers.\n\n{exc}")
            self.log(f"Failed to apply custom DNS on {adapter.alias}: {exc}")
            return

        self.log(f"Applied custom DNS to {adapter.alias}: {', '.join(servers)}")
        self.refresh_adapters()

    def restore_automatic_dns(self) -> None:
        adapter = self.selected_adapter
        if not adapter:
            messagebox.showwarning(APP_TITLE, f"Select a {self.backend.entity_label} first.")
            return
        if not self.ensure_ready_for_change():
            return

        try:
            self.backend.reset_dns(adapter)
        except BackendError as exc:
            messagebox.showerror(APP_TITLE, f"Could not restore automatic DNS.\n\n{exc}")
            self.log(f"Failed to restore automatic DNS on {adapter.alias}: {exc}")
            return

        self.log(f"Restored automatic DNS on {adapter.alias}.")
        self.refresh_adapters()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_SUBTITLE)
    parser.add_argument("--self-test", action="store_true", help="Print detected adapters/services as JSON and exit.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    backend = create_backend()

    if args.self_test:
        return self_test(backend)

    root = tk.Tk()
    DNSDashboard(root, backend)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
