from __future__ import annotations

import ctypes
import ipaddress
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import messagebox, ttk


APP_TITLE = "DNS Switcher"
WINDOW_SIZE = "680x620"
BACKGROUND = "#F5F1E8"
SURFACE = "#FFFDF9"
ACCENT = "#0F766E"
ACCENT_DARK = "#115E59"
WARNING = "#C2410C"
TEXT = "#1F2937"
MUTED = "#6B7280"
BORDER = "#D6D3D1"

POWERSHELL = (
    shutil.which("powershell.exe")
    or shutil.which("pwsh.exe")
    or shutil.which("pwsh")
    or shutil.which("powershell")
)


class BackendError(RuntimeError):
    """Raised when Windows networking commands fail."""


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
    def label(self) -> str:
        joined = " / ".join(self.servers)
        return f"{self.name}\n{joined}\n{self.description}"


@dataclass
class AdapterInfo:
    interface_index: int
    alias: str
    status: str
    description: str
    guid: str
    dns_mode: str
    active_servers: list[str]
    manual_servers: list[str]
    dhcp_servers: list[str]

    @property
    def display_name(self) -> str:
        return f"{self.alias} ({self.status})"

    @property
    def current_servers(self) -> list[str]:
        if self.dns_mode == "Manual" and self.manual_servers:
            return self.manual_servers
        if self.dns_mode == "Automatic" and self.dhcp_servers:
            return self.dhcp_servers
        return self.active_servers


PRESETS = [
    DnsPreset("Cloudflare", "1.1.1.1", "1.0.0.1", "Fast public DNS"),
    DnsPreset("Google", "8.8.8.8", "8.8.4.4", "Widely available"),
    DnsPreset("Quad9", "9.9.9.9", "149.112.112.112", "Security-focused"),
    DnsPreset("OpenDNS", "208.67.222.222", "208.67.220.220", "Cisco public DNS"),
    DnsPreset("AdGuard", "94.140.14.14", "94.140.15.15", "Blocks many ads"),
    DnsPreset("Control D", "76.76.2.0", "76.76.10.0", "Privacy-friendly"),
]


def ensure_windows() -> None:
    if os.name != "nt":
        raise SystemExit(f"{APP_TITLE} only runs on Windows.")


def is_admin() -> bool:
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


def normalize_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_string_list(value: Any) -> list[str]:
    return [str(item) for item in normalize_json_list(value) if str(item).strip()]


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


def run_netsh(arguments: list[str]) -> str:
    return run_command(["netsh", *arguments])


def run_powershell_json(script: str) -> Any:
    output = run_powershell(script)
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise BackendError(f"Failed to parse PowerShell output: {output}") from exc


def load_adapters() -> list[AdapterInfo]:
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
        interface_index = [int]$adapter.ifIndex
        alias = $adapter.InterfaceAlias
        status = [string]$adapter.Status
        description = $adapter.InterfaceDescription
        guid = [string]$adapter.InterfaceGuid
        dns_mode = if ($manualServers.Count -gt 0) { "Manual" } elseif ($dhcpServers.Count -gt 0) { "Automatic" } else { "Unknown" }
        active_servers = $activeServers
        manual_servers = $manualServers
        dhcp_servers = $dhcpServers
    }
}

$rows | ConvertTo-Json -Compress -Depth 4
"""
    raw_rows = normalize_json_list(run_powershell_json(script))
    adapters: list[AdapterInfo] = []
    for row in raw_rows:
        adapters.append(
            AdapterInfo(
                interface_index=int(row["interface_index"]),
                alias=str(row["alias"]),
                status=str(row["status"]),
                description=str(row["description"]),
                guid=str(row["guid"]),
                dns_mode=str(row["dns_mode"]),
                active_servers=normalize_string_list(row.get("active_servers")),
                manual_servers=normalize_string_list(row.get("manual_servers")),
                dhcp_servers=normalize_string_list(row.get("dhcp_servers")),
            )
        )
    return adapters


def set_dns_servers(interface_index: int, servers: list[str]) -> None:
    run_netsh(
        [
            "interface",
            "ipv4",
            "set",
            "dnsservers",
            f"name={interface_index}",
            "source=static",
            f"address={servers[0]}",
            "validate=yes",
        ]
    )
    for order, server in enumerate(servers[1:], start=2):
        run_netsh(
            [
                "interface",
                "ipv4",
                "add",
                "dnsservers",
                f"name={interface_index}",
                f"address={server}",
                f"index={order}",
                "validate=yes",
            ]
        )
    flush_dns_cache()


def reset_dns_servers(interface_index: int) -> None:
    run_netsh(
        [
            "interface",
            "ipv4",
            "set",
            "dnsservers",
            f"name={interface_index}",
            "source=dhcp",
        ]
    )
    flush_dns_cache()


def flush_dns_cache() -> None:
    try:
        run_command(["ipconfig", "/flushdns"])
    except BackendError:
        pass


def validate_ipv4(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("DNS server values cannot be empty.")
    try:
        return str(ipaddress.IPv4Address(value))
    except ipaddress.AddressValueError as exc:
        raise ValueError(f"'{value}' is not a valid IPv4 address.") from exc


def self_test() -> int:
    adapters = load_adapters()
    payload = {
        "adapter_count": len(adapters),
        "adapters": [
            {
                "alias": adapter.alias,
                "status": adapter.status,
                "dns_mode": adapter.dns_mode,
                "servers": adapter.current_servers,
            }
            for adapter in adapters
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


class DNSApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.minsize(640, 580)
        self.root.configure(bg=BACKGROUND)

        self.adapters: list[AdapterInfo] = []
        self.adapter_lookup: dict[str, AdapterInfo] = {}

        self.admin_text = tk.StringVar()
        self.adapter_var = tk.StringVar()
        self.adapter_status_var = tk.StringVar(value="Status: -")
        self.adapter_mode_var = tk.StringVar(value="DNS Mode: -")
        self.adapter_servers_var = tk.StringVar(value="Current DNS: -")
        self.footer_var = tk.StringVar(value="Loading adapters...")
        self.primary_var = tk.StringVar()
        self.secondary_var = tk.StringVar()

        self._configure_style()
        self._build_ui()
        self.refresh_adapters(initial=True)

    def _configure_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("App.TFrame", background=BACKGROUND)
        style.configure("Header.TLabel", background=BACKGROUND, foreground=TEXT, font=("Segoe UI Semibold", 22))
        style.configure("Muted.TLabel", background=BACKGROUND, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("CardText.TLabel", background=SURFACE, foreground=TEXT)
        style.configure("Footer.TLabel", background=BACKGROUND, foreground=MUTED)
        style.configure("Primary.TButton", background=ACCENT, foreground="white", padding=(10, 9), borderwidth=0)
        style.map("Primary.TButton", background=[("active", ACCENT_DARK)])
        style.configure("Warn.TButton", background=WARNING, foreground="white", padding=(10, 9), borderwidth=0)
        style.map("Warn.TButton", background=[("active", "#9A3412")])
        style.configure("Small.TButton", padding=(8, 6))
        style.configure("TCombobox", padding=6)
        style.configure("TLabelframe", background=SURFACE, foreground=TEXT)
        style.configure("TLabelframe.Label", background=SURFACE, foreground=TEXT, font=("Segoe UI Semibold", 11))

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, style="App.TFrame", padding=18)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)

        header = ttk.Frame(container, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text=APP_TITLE, style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="A simple panel for switching IPv4 DNS on your Windows adapters.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.admin_banner = tk.Label(
            header,
            text="",
            font=("Segoe UI Semibold", 10),
            padx=10,
            pady=7,
            anchor="w",
        )
        self.admin_banner.grid(row=0, column=1, rowspan=2, sticky="e")

        panel = ttk.LabelFrame(container, text="DNS Panel", padding=16)
        panel.grid(row=1, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)

        selector_row = ttk.Frame(panel, style="App.TFrame")
        selector_row.grid(row=0, column=0, sticky="ew")
        selector_row.columnconfigure(0, weight=1)

        ttk.Label(selector_row, text="Adapter", style="CardText.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(selector_row, text="Refresh", style="Small.TButton", command=self.refresh_adapters).grid(
            row=0, column=1, sticky="e"
        )

        self.adapter_combo = ttk.Combobox(panel, textvariable=self.adapter_var, state="readonly")
        self.adapter_combo.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        self.adapter_combo.bind("<<ComboboxSelected>>", self._on_adapter_selected)

        info_frame = tk.Frame(panel, bg="#FAF7F2", highlightbackground=BORDER, highlightthickness=1, bd=0)
        info_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        info_frame.columnconfigure(0, weight=1)

        self.adapter_name_label = tk.Label(
            info_frame,
            text="No adapter selected",
            bg="#FAF7F2",
            fg=TEXT,
            font=("Segoe UI Semibold", 15),
            anchor="w",
            padx=12,
            pady=(12, 4),
        )
        self.adapter_name_label.grid(row=0, column=0, sticky="ew")

        self.adapter_description_label = tk.Label(
            info_frame,
            text="",
            bg="#FAF7F2",
            fg=MUTED,
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
            wraplength=570,
            padx=12,
            pady=(0, 8),
        )
        self.adapter_description_label.grid(row=1, column=0, sticky="ew")

        ttk.Label(info_frame, textvariable=self.adapter_status_var, style="CardText.TLabel").grid(
            row=2, column=0, sticky="w", padx=12, pady=(0, 4)
        )
        ttk.Label(info_frame, textvariable=self.adapter_mode_var, style="CardText.TLabel").grid(
            row=3, column=0, sticky="w", padx=12, pady=(0, 4)
        )
        ttk.Label(info_frame, textvariable=self.adapter_servers_var, style="CardText.TLabel").grid(
            row=4, column=0, sticky="w", padx=12, pady=(0, 12)
        )

        preset_card = ttk.LabelFrame(panel, text="Presets", padding=12)
        preset_card.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        preset_card.columnconfigure(0, weight=1)
        preset_card.columnconfigure(1, weight=1)

        for index, preset in enumerate(PRESETS):
            button = ttk.Button(
                preset_card,
                text=f"{preset.name}\n{preset.primary} / {preset.secondary}",
                style="Primary.TButton",
                command=lambda chosen=preset: self.apply_preset(chosen),
            )
            row = index // 2
            column = index % 2
            button.grid(row=row, column=column, sticky="ew", padx=6, pady=6)

        custom_card = ttk.LabelFrame(panel, text="Custom IPv4 DNS", padding=12)
        custom_card.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        custom_card.columnconfigure(0, weight=1)
        custom_card.columnconfigure(1, weight=1)

        ttk.Label(custom_card, text="Preferred DNS", style="CardText.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(custom_card, text="Alternate DNS", style="CardText.TLabel").grid(row=0, column=1, sticky="w")

        self.primary_entry = ttk.Entry(custom_card, textvariable=self.primary_var)
        self.primary_entry.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(6, 12))
        self.secondary_entry = ttk.Entry(custom_card, textvariable=self.secondary_var)
        self.secondary_entry.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(6, 12))

        ttk.Button(custom_card, text="Apply Custom DNS", style="Primary.TButton", command=self.apply_custom).grid(
            row=2, column=0, columnspan=2, sticky="ew"
        )

        utility_card = ttk.LabelFrame(panel, text="Actions", padding=12)
        utility_card.grid(row=5, column=0, sticky="ew")
        utility_card.columnconfigure(0, weight=1)
        utility_card.columnconfigure(1, weight=1)

        ttk.Button(
            utility_card,
            text="Restore Automatic DNS",
            style="Warn.TButton",
            command=self.restore_automatic_dns,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ttk.Button(
            utility_card,
            text="Use Current DNS",
            style="Small.TButton",
            command=self.copy_current_to_custom,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ttk.Button(
            utility_card,
            text="Restart as Administrator",
            style="Small.TButton",
            command=self.request_relaunch,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        footer = ttk.Label(container, textvariable=self.footer_var, style="Footer.TLabel")
        footer.grid(row=2, column=0, sticky="ew", pady=(12, 0))

    def log(self, message: str) -> None:
        self.footer_var.set(message)

    def refresh_admin_banner(self) -> None:
        if is_admin():
            self.admin_text.set("Administrator access detected")
            self.admin_banner.configure(text=self.admin_text.get(), bg="#D1FAE5", fg="#065F46")
        else:
            self.admin_text.set("Standard user mode")
            self.admin_banner.configure(text=self.admin_text.get(), bg="#FEF3C7", fg="#92400E")

    def refresh_adapters(self, initial: bool = False) -> None:
        self.refresh_admin_banner()
        current_choice = self.adapter_var.get()
        try:
            self.adapters = load_adapters()
        except BackendError as exc:
            messagebox.showerror(APP_TITLE, f"Could not read network adapters.\n\n{exc}")
            self.log(f"Failed to load adapters: {exc}")
            return

        self.adapter_lookup = {adapter.display_name: adapter for adapter in self.adapters}
        values = [adapter.display_name for adapter in self.adapters]
        self.adapter_combo["values"] = values

        if not values:
            self.adapter_var.set("")
            self._render_adapter(None)
            self.log("No network adapters were found.")
            return

        if current_choice in self.adapter_lookup:
            self.adapter_var.set(current_choice)
        else:
            self.adapter_var.set(values[0])

        self._render_adapter(self.adapter_lookup[self.adapter_var.get()])
        self.log(f"Loaded {len(self.adapters)} adapter(s).")
        if initial and not is_admin():
            self.log("Administrator rights are required before DNS changes can be applied.")

    def _on_adapter_selected(self, _event: object) -> None:
        self._render_adapter(self.selected_adapter)

    @property
    def selected_adapter(self) -> AdapterInfo | None:
        return self.adapter_lookup.get(self.adapter_var.get())

    def _render_adapter(self, adapter: AdapterInfo | None) -> None:
        if not adapter:
            self.adapter_name_label.configure(text="No adapter selected")
            self.adapter_description_label.configure(text="")
            self.adapter_status_var.set("Status: -")
            self.adapter_mode_var.set("DNS Mode: -")
            self.adapter_servers_var.set("Current DNS: -")
            return

        servers = ", ".join(adapter.current_servers) if adapter.current_servers else "No IPv4 DNS servers reported"
        self.adapter_name_label.configure(text=adapter.alias)
        self.adapter_description_label.configure(text=adapter.description)
        self.adapter_status_var.set(f"Status: {adapter.status}")
        self.adapter_mode_var.set(f"DNS Mode: {adapter.dns_mode}")
        self.adapter_servers_var.set(f"Current DNS: {servers}")

    def ensure_elevation(self) -> bool:
        if is_admin():
            return True

        should_restart = messagebox.askyesno(
            APP_TITLE,
            "Changing DNS requires administrator privileges.\n\nRelaunch the app as administrator now?",
        )
        if should_restart and self.request_relaunch():
            self.root.destroy()
        return False

    def request_relaunch(self) -> bool:
        if is_admin():
            messagebox.showinfo(APP_TITLE, "The app is already running as administrator.")
            return False

        if relaunch_as_admin():
            self.log("Relaunch request sent. Accept the Windows UAC prompt to continue.")
            return True

        messagebox.showwarning(APP_TITLE, "Windows did not start the elevated copy.")
        self.log("Relaunch as administrator was cancelled or failed.")
        return False

    def copy_current_to_custom(self) -> None:
        adapter = self.selected_adapter
        if not adapter:
            messagebox.showwarning(APP_TITLE, "Select an adapter first.")
            return

        servers = adapter.current_servers
        self.primary_var.set(servers[0] if len(servers) >= 1 else "")
        self.secondary_var.set(servers[1] if len(servers) >= 2 else "")
        self.log(f"Copied current DNS from {adapter.alias} into the custom fields.")

    def apply_preset(self, preset: DnsPreset) -> None:
        adapter = self.selected_adapter
        if not adapter:
            messagebox.showwarning(APP_TITLE, "Select an adapter first.")
            return
        if not self.ensure_elevation():
            return

        try:
            set_dns_servers(adapter.interface_index, preset.servers)
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
            messagebox.showwarning(APP_TITLE, "Select an adapter first.")
            return
        if not self.ensure_elevation():
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
            set_dns_servers(adapter.interface_index, servers)
        except BackendError as exc:
            messagebox.showerror(APP_TITLE, f"Could not apply the custom DNS servers.\n\n{exc}")
            self.log(f"Failed to apply custom DNS on {adapter.alias}: {exc}")
            return

        self.log(f"Applied custom DNS to {adapter.alias}: {', '.join(servers)}")
        self.refresh_adapters()

    def restore_automatic_dns(self) -> None:
        adapter = self.selected_adapter
        if not adapter:
            messagebox.showwarning(APP_TITLE, "Select an adapter first.")
            return
        if not self.ensure_elevation():
            return

        try:
            reset_dns_servers(adapter.interface_index)
        except BackendError as exc:
            messagebox.showerror(APP_TITLE, f"Could not restore automatic DNS.\n\n{exc}")
            self.log(f"Failed to restore automatic DNS on {adapter.alias}: {exc}")
            return

        self.log(f"Restored automatic DNS on {adapter.alias}.")
        self.refresh_adapters()


def main() -> int:
    ensure_windows()
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        return self_test()

    root = tk.Tk()
    app = DNSApp(root)
    app.log("Ready.")
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
