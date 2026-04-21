#!/usr/bin/env python3
"""
Ubuntu Setup Tool - Post-installation configurator
Run after fresh Ubuntu 24.04 LTS install to configure system, install apps, and set up accounts.
"""

import subprocess
import sys
import os
import json
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ── Bootstrap: ensure rich is available ──────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Confirm, Prompt
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.text import Text
    from rich.columns import Columns
    from rich.markup import escape
except ImportError:
    print("Installing required dependency: rich")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich", "--quiet"])
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Confirm, Prompt
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.text import Text
    from rich.columns import Columns
    from rich.markup import escape

console = Console()

# ── State management ─────────────────────────────────────────────────────────
STATE_FILE = Path.home() / ".ubuntu-setup-state.json"

# ── Autostart (XDG) ──────────────────────────────────────────────────────────
AUTOSTART_FILE = Path.home() / ".config/autostart/ubuntu-setup-tool.desktop"

def _autostart_desktop_contents() -> str:
    script_path = Path(__file__).resolve()
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Ubuntu Setup Tool\n"
        "Comment=Post-installation configurator\n"
        f"Exec=x-terminal-emulator -e {script_path}\n"
        "Icon=system-run\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "Categories=System;\n"
    )

def autostart_enabled() -> bool:
    return AUTOSTART_FILE.exists()

def set_autostart(enabled: bool) -> None:
    if enabled:
        AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART_FILE.write_text(_autostart_desktop_contents())
    else:
        AUTOSTART_FILE.unlink(missing_ok=True)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"completed": [], "skipped": [], "failed": []}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def mark_done(state: dict, task_id: str):
    if task_id not in state["completed"]:
        state["completed"].append(task_id)
    save_state(state)

def mark_failed(state: dict, task_id: str):
    if task_id not in state["failed"]:
        state["failed"].append(task_id)
    save_state(state)

# ── Helpers ──────────────────────────────────────────────────────────────────
def run(cmd: str, check: bool = True, capture: bool = False, env: dict = None) -> subprocess.CompletedProcess:
    """Run a shell command with optional environment overrides."""
    merged_env = {**os.environ, **(env or {})}
    return subprocess.run(
        cmd, shell=True, check=check, capture_output=capture,
        text=True, env=merged_env
    )

def run_quiet(cmd: str) -> bool:
    """Run a command silently, return True on success."""
    result = run(cmd, check=False, capture=True)
    return result.returncode == 0

def is_installed(cmd_name: str) -> bool:
    return shutil.which(cmd_name) is not None

def apt_install(*packages: str):
    pkg_list = " ".join(packages)
    run(f"sudo apt install -y {pkg_list}")

def snap_install(package: str, classic: bool = False):
    flag = "--classic" if classic else ""
    run(f"sudo snap install {package} {flag}")

def flatpak_install(app_id: str):
    run(f"flatpak install -y flathub {app_id}")

def is_surface() -> bool:
    """Detect if running on a Microsoft Surface device."""
    try:
        result = run("cat /sys/devices/virtual/dmi/id/product_name", capture=True, check=False)
        return "surface" in result.stdout.lower()
    except Exception:
        return False

def detect_gpu() -> str:
    """Detect GPU vendor."""
    result = run("lspci | grep -iE 'vga|3d|display'", capture=True, check=False)
    output = result.stdout.lower()
    if "nvidia" in output:
        return "nvidia"
    elif "amd" in output or "radeon" in output:
        return "amd"
    elif "intel" in output:
        return "intel"
    return "unknown"


# ── Download URL Registry & DE-powered resolver ─────────────────────────────
# Apps with unstable download URLs get resolved at runtime via DE LLM call.
# Fallback URLs are used if DE is unreachable.

DOWNLOAD_REGISTRY = {
    "cursor": {
        "fallback": "https://downloader.cursor.sh/linux/appImage/x64",
        "description": "Cursor AI code editor AppImage for Linux x64",
    },
    "discord": {
        "fallback": "https://discord.com/api/download?platform=linux&format=deb",
        "description": "Discord .deb package for Linux x64",
    },
    "proton_pass": {
        "fallback": "https://proton.me/download/PassDesktop/linux/x64/ProtonPass.deb",
        "description": "Proton Pass .deb package for Linux x64",
    },
    "proton_vpn": {
        "fallback": "https://repo.protonvpn.com/debian/dists/stable/main/binary-all/protonvpn-stable-release_1.0.6_all.deb",
        "description": "Proton VPN stable release .deb for Debian/Ubuntu",
    },
    "vscode": {
        "fallback": "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64",
        "description": "Visual Studio Code .deb package for Linux x64",
    },
    "chrome": {
        "fallback": "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb",
        "description": "Google Chrome stable .deb for amd64",
    },
    "kando": {
        "fallback": "https://github.com/kando-menu/kando/releases/latest/download/kando_amd64.deb",
        "description": "Kando radial menu .deb for amd64",
    },
    "sunshine": {
        "fallback": "https://github.com/LizardByte/Sunshine/releases/latest/download/sunshine-ubuntu-24.04-amd64.deb",
        "description": "Sunshine game streaming server .deb for Ubuntu 24.04 amd64",
    },
    "cloudflared": {
        "fallback": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb",
        "description": "Cloudflare Tunnel daemon .deb for Linux amd64",
    },
}

# URL cache file — persists resolved URLs across runs
URL_CACHE_FILE = Path.home() / ".ubuntu-setup-url-cache.json"

def _load_url_cache() -> dict:
    if URL_CACHE_FILE.exists():
        try:
            return json.loads(URL_CACHE_FILE.read_text())
        except Exception:
            pass
    return {}

def _save_url_cache(cache: dict):
    URL_CACHE_FILE.write_text(json.dumps(cache, indent=2))

def resolve_download_url(app_id: str) -> str:
    """
    Resolve the current download URL for an app.
    
    Strategy:
    1. Check URL cache (valid for 24h)
    2. Try DE intake worker with LLM call to find current URL
    3. Fall back to hardcoded URL
    """
    registry_entry = DOWNLOAD_REGISTRY.get(app_id)
    if not registry_entry:
        raise ValueError(f"Unknown app_id: {app_id}")

    cache = _load_url_cache()

    # Check cache (24h TTL)
    import time
    cached = cache.get(app_id)
    if cached and (time.time() - cached.get("ts", 0)) < 86400:
        return cached["url"]

    # Try DE LLM resolution
    try:
        resolved = _de_resolve_url(app_id, registry_entry["description"])
        if resolved:
            cache[app_id] = {"url": resolved, "ts": time.time()}
            _save_url_cache(cache)
            return resolved
    except Exception as e:
        console.print(f"[dim]  DE URL resolution failed for {app_id}: {e}. Using fallback.[/dim]")

    return registry_entry["fallback"]


def _de_resolve_url(app_id: str, description: str) -> Optional[str]:
    """
    Call DE intake worker to resolve the latest download URL via LLM.
    Returns the URL string or None on failure.
    """
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "task": f"Find the current official download URL for: {description}. "
                f"Return ONLY the direct download URL, nothing else. "
                f"The URL should be for the latest stable release. "
                f"If the URL uses a redirect (like /latest/download/), that's fine.",
        "metadata": {
            "source": "ubuntu-setup-tool",
            "app_id": app_id,
            "type": "url_resolve",
        }
    })

    req = urllib.request.Request(
        "https://intake.distributedelectrons.com/intake",
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            # DE returns the result in various formats — extract URL
            url = result.get("url") or result.get("result", "")
            if url.startswith("http"):
                return url.strip()
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        pass

    return None


def get_url(app_id: str) -> str:
    """Convenience wrapper — resolve URL with console feedback."""
    console.print(f"[dim]  Resolving download URL for {app_id}...[/dim]")
    url = resolve_download_url(app_id)
    console.print(f"[dim]  → {url}[/dim]")
    return url

# ── Selection UI ─────────────────────────────────────────────────────────────
def select_items(title: str, items: list[tuple[str, str, bool]]) -> list[str]:
    """
    Interactive selector. items = [(id, label, default_selected), ...]
    Returns list of selected ids.
    """
    selected = {item[0]: item[2] for item in items}

    while True:
        console.clear()
        table = Table(title=title, show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("", width=3)
        table.add_column("Item", style="white")

        for i, (item_id, label, _) in enumerate(items, 1):
            check = "[green]✓[/green]" if selected[item_id] else "[dim]·[/dim]"
            table.add_row(str(i), check, label)

        console.print(table)
        console.print("\n[dim]Toggle: number | 'a' = all | 'n' = none | 'go' = proceed | 'q' = cancel[/dim]")

        choice = Prompt.ask("›").strip().lower()

        if choice == "go":
            return [item_id for item_id, sel in selected.items() if sel]
        elif choice == "q":
            return []
        elif choice == "a":
            selected = {k: True for k in selected}
        elif choice == "n":
            selected = {k: False for k in selected}
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                item_id = items[idx][0]
                selected[item_id] = not selected[item_id]


def run_tasks(task_list: list[tuple[str, str, callable]], state: dict):
    """Run a list of (task_id, description, func) with progress tracking."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        overall = progress.add_task("Overall", total=len(task_list))

        for task_id, desc, func in task_list:
            if task_id in state["completed"]:
                console.print(f"  [dim]⏭  {desc} (already done)[/dim]")
                progress.advance(overall)
                continue

            progress.update(overall, description=desc)
            try:
                func()
                mark_done(state, task_id)
                console.print(f"  [green]✓[/green] {desc}")
            except Exception as e:
                mark_failed(state, task_id)
                console.print(f"  [red]✗[/red] {desc}: {escape(str(e))}")
            progress.advance(overall)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 0: Surface Linux (optional)
# ══════════════════════════════════════════════════════════════════════════════
def module_surface_linux(state: dict):
    console.print(Panel("[bold]Surface Linux Kernel[/bold]\nInstall custom kernel for Microsoft Surface hardware", style="blue"))

    surface_detected = is_surface()
    if surface_detected:
        console.print("[yellow]⚡ Surface device detected![/yellow]")
    else:
        console.print("[dim]No Surface device detected. You can still install if needed.[/dim]")

    if not Confirm.ask("Install linux-surface kernel?", default=surface_detected):
        return

    tasks = [
        ("surface_gpg", "Import linux-surface GPG key", lambda: run(
            "wget -qO - https://raw.githubusercontent.com/linux-surface/linux-surface/master/pkg/keys/surface.asc | "
            "gpg --dearmor | sudo dd of=/etc/apt/trusted.gpg.d/linux-surface.gpg"
        )),
        ("surface_repo", "Add linux-surface repository", lambda: run(
            'echo "deb [arch=amd64] https://pkg.surfacelinux.com/debian release main" | '
            'sudo tee /etc/apt/sources.list.d/linux-surface.list'
        )),
        ("surface_update", "Update package lists", lambda: run("sudo apt update")),
        ("surface_kernel", "Install surface kernel", lambda: apt_install(
            "linux-image-surface", "linux-headers-surface", "libwacom-surface",
            "iptsd"
        )),
        ("surface_secureboot", "Install secureboot MOK", lambda: run(
            "sudo apt install -y linux-surface-secureboot-mok"
        )),
        ("surface_microcode", "Install CPU microcode", lambda: run(
            "sudo apt install -y intel-microcode || sudo apt install -y amd64-microcode"
        )),
        ("surface_grub", "Update bootloader", lambda: run("sudo update-grub")),
    ]

    # Check for offline packages first
    offline_dir = Path(__file__).parent / "surface-linux" / "debs"
    if offline_dir.exists() and list(offline_dir.glob("*.deb")):
        console.print("[green]Found offline surface-linux packages[/green]")
        tasks = [
            ("surface_offline", "Install surface kernel (offline)", lambda: run(
                f"sudo dpkg -i {offline_dir}/*.deb && sudo apt install -f -y"
            )),
            ("surface_secureboot", "Install secureboot MOK", lambda: run(
                "sudo apt install -y linux-surface-secureboot-mok"
            )),
            ("surface_microcode", "Install CPU microcode", lambda: run(
                "sudo apt install -y intel-microcode || sudo apt install -y amd64-microcode"
            )),
            ("surface_grub", "Update bootloader", lambda: run("sudo update-grub")),
        ]

    run_tasks(tasks, state)
    console.print("\n[yellow]⚠  Reboot required for surface kernel to take effect.[/yellow]")
    console.print("[dim]Verify with: uname -a (should contain 'surface')[/dim]")


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 1: Kitty Terminal
# ══════════════════════════════════════════════════════════════════════════════
def module_kitty(state: dict):
    console.print(Panel("[bold]Kitty Terminal[/bold]", style="blue"))

    tasks = [
        ("kitty_install", "Install Kitty", lambda: run(
            "curl -L https://sw.kovidgoyal.net/kitty/installer.sh | sh /dev/stdin launch=n"
        )),
        ("kitty_symlinks", "Create symlinks", lambda: run(
            "sudo ln -sf ~/.local/kitty.app/bin/kitty /usr/local/bin/kitty && "
            "sudo ln -sf ~/.local/kitty.app/bin/kitten /usr/local/bin/kitten"
        )),
        ("kitty_desktop", "Register desktop entry", lambda: run(
            "cp ~/.local/kitty.app/share/applications/kitty.desktop ~/.local/share/applications/ && "
            "cp ~/.local/kitty.app/share/applications/kitty-open.desktop ~/.local/share/applications/ && "
            "sed -i 's|Icon=kitty|Icon=$HOME/.local/kitty.app/share/icons/hicolor/256x256/apps/kitty.png|g' "
            "~/.local/share/applications/kitty*.desktop"
        )),
        ("kitty_default", "Set as default terminal", lambda: run(
            "sudo update-alternatives --install /usr/bin/x-terminal-emulator x-terminal-emulator "
            "$(which kitty) 50 && "
            "sudo update-alternatives --set x-terminal-emulator $(which kitty)"
        )),
    ]
    run_tasks(tasks, state)

    # Theme selection
    console.print("\n[cyan]Kitty themes — pick one:[/cyan]")
    themes = [
        ("gruvbox_dark", "Gruvbox Dark", True),
        ("catppuccin_mocha", "Catppuccin Mocha", False),
        ("tokyo_night", "Tokyo Night", False),
        ("dracula", "Dracula", False),
        ("nord", "Nord", False),
        ("one_dark", "One Dark", False),
        ("solarized_dark", "Solarized Dark", False),
        ("rose_pine", "Rosé Pine", False),
    ]
    selected = select_items("Kitty Theme", themes)
    if selected:
        theme = selected[0]
        console.print(f"Setting theme: {theme}")
        run(f"kitten themes --reload-in=all {theme.replace('_', ' ').title()}", check=False)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 2: Updates and Drivers
# ══════════════════════════════════════════════════════════════════════════════
def module_updates(state: dict):
    console.print(Panel("[bold]System Updates & Drivers[/bold]", style="blue"))

    gpu = detect_gpu()
    console.print(f"Detected GPU: [cyan]{gpu}[/cyan]")

    tasks = [
        ("apt_update", "Update package lists", lambda: run("sudo apt update")),
        ("apt_upgrade", "Upgrade installed packages", lambda: run("sudo apt upgrade -y")),
        ("apt_autoremove", "Remove unused packages", lambda: run("sudo apt autoremove -y")),
    ]

    if gpu == "nvidia":
        tasks.append(("nvidia_drivers", "Install NVIDIA drivers",
                       lambda: run("sudo ubuntu-drivers install --gpgpu")))
    elif gpu == "amd":
        tasks.append(("amd_firmware", "Update AMD firmware",
                       lambda: apt_install("firmware-amd-graphics")))

    tasks.append(("fwupd", "Check firmware updates", lambda: run(
        "sudo fwupdmgr get-updates && sudo fwupdmgr update || true"
    )))

    run_tasks(tasks, state)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 3: Web Browsers
# ══════════════════════════════════════════════════════════════════════════════
def module_browsers(state: dict):
    console.print(Panel("[bold]Web Browsers[/bold]", style="blue"))

    browsers = [
        ("firefox", "Firefox (pre-installed)", True),
        ("chrome", "Google Chrome", True),
        ("brave", "Brave", False),
        ("chromium", "Chromium", False),
        ("helium", "Helium (Lighter browser)", False),
    ]
    selected = select_items("Select browsers to install", browsers)
    if not selected:
        return

    tasks = []

    if "chrome" in selected:
        def install_chrome():
            url = get_url("chrome")
            run(f"wget -q -O /tmp/chrome.deb '{url}' && "
                "sudo dpkg -i /tmp/chrome.deb || sudo apt install -f -y && rm /tmp/chrome.deb")
        tasks.append(("chrome", "Install Google Chrome", install_chrome))

    if "brave" in selected:
        tasks.append(("brave", "Install Brave", lambda: run(
            "sudo curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg "
            "https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg && "
            'echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] '
            'https://brave-browser-apt-release.s3.brave.com/ stable main" | '
            "sudo tee /etc/apt/sources.list.d/brave-browser-release.list && "
            "sudo apt update && sudo apt install -y brave-browser"
        )))

    if "chromium" in selected:
        tasks.append(("chromium", "Install Chromium", lambda: apt_install("chromium-browser")))

    if "helium" in selected:
        tasks.append(("helium", "Install Helium", lambda: run(
            "flatpak install -y flathub io.github.nickvision.application || "
            "echo 'Helium not found on Flathub — check manual install'"
        )))

    run_tasks(tasks, state)

    # Browser plugins notice
    console.print("\n[cyan]Browser extensions to install manually:[/cyan]")
    extensions = [
        "uBlock Origin",
        "Dark Reader",
        "Proton Pass",
    ]
    for ext in extensions:
        console.print(f"  • {ext}")

    # Default search engine
    console.print("\n[cyan]Set default search engine:[/cyan]")
    search = select_items("Default Search", [
        ("kagi", "Kagi", True),
        ("ddg", "DuckDuckGo", False),
    ])
    if search:
        console.print(f"[dim]Set {search[0]} as default in each browser's settings.[/dim]")

    console.print("\n[yellow]Note: Set Proton Pass as default password manager in browser settings.[/yellow]")


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 4: Account Setup
# ══════════════════════════════════════════════════════════════════════════════
def module_accounts(state: dict):
    console.print(Panel("[bold]Account Setup[/bold]", style="blue"))

    sections = [
        ("proton", "Proton Suite (Mail, Pass, VPN, Calendar)", True),
        ("github", "GitHub CLI + Auth", True),
        ("cloudflare", "Cloudflare (wrangler + cloudflared)", True),
        ("ssh", "SSH Key Generation", True),
    ]
    selected = select_items("Account Setup", sections)
    if not selected:
        return

    tasks = []

    # ── Proton ───────────────────────────────────────────────────────────
    if "proton" in selected:
        def install_proton_pass():
            url = get_url("proton_pass")
            run(f"wget -q '{url}' -O /tmp/proton-pass.deb && "
                "sudo dpkg -i /tmp/proton-pass.deb || sudo apt install -f -y && rm /tmp/proton-pass.deb")

        def install_proton_vpn():
            url = get_url("proton_vpn")
            run(f"wget -q '{url}' -O /tmp/protonvpn-release.deb && "
                "sudo dpkg -i /tmp/protonvpn-release.deb && sudo apt update && "
                "sudo apt install -y proton-vpn-gnome-desktop && rm /tmp/protonvpn-release.deb")

        tasks.extend([
            ("proton_mail", "Install Proton Mail (Flatpak)", lambda: flatpak_install("me.proton.Mail")),
            ("proton_pass", "Install Proton Pass", install_proton_pass),
            ("proton_vpn", "Install Proton VPN", install_proton_vpn),
            ("proton_calendar_note", "Proton Calendar (web-only)", lambda: console.print(
                "[dim]  Proton Calendar is web-only. Bookmark: https://calendar.proton.me[/dim]"
            )),
            ("proton_drive_note", "Proton Drive (placeholder)", lambda: console.print(
                "[dim]  Proton Drive Linux client is not yet available. Watch: https://proton.me/drive[/dim]"
            )),
        ])

    # ── GitHub CLI ────────────────────────────────────────────────────────
    if "github" in selected:
        tasks.extend([
            ("gh_install", "Install GitHub CLI", lambda: run(
                "(type -p wget >/dev/null || sudo apt install -y wget) && "
                "sudo mkdir -p -m 755 /etc/apt/keyrings && "
                "wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg | "
                "sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null && "
                "sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg && "
                'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] '
                'https://cli.github.com/packages stable main" | '
                "sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && "
                "sudo apt update && sudo apt install -y gh"
            )),
            ("gh_auth", "Authenticate GitHub CLI", lambda: run("gh auth login")),
        ])

    # ── Cloudflare ────────────────────────────────────────────────────────
    if "cloudflare" in selected:
        def install_cloudflared():
            url = get_url("cloudflared")
            run(f"wget -q '{url}' -O /tmp/cloudflared.deb && "
                "sudo dpkg -i /tmp/cloudflared.deb && rm /tmp/cloudflared.deb")

        tasks.extend([
            ("wrangler", "Install Wrangler (via bun)", lambda: run("bun install -g wrangler || npm install -g wrangler")),
            ("wrangler_auth", "Authenticate Wrangler", lambda: run("wrangler login")),
            ("cloudflared", "Install cloudflared", install_cloudflared),
            ("cloudflared_auth", "Authenticate cloudflared", lambda: run("cloudflared tunnel login")),
        ])

    # ── SSH Keys ──────────────────────────────────────────────────────────
    if "ssh" in selected:
        def setup_ssh():
            email = Prompt.ask("Email for SSH key", default="chris@solamp.io")
            key_path = Path.home() / ".ssh" / "id_ed25519"
            if key_path.exists():
                console.print("[yellow]SSH key already exists. Skipping generation.[/yellow]")
            else:
                run(f'ssh-keygen -t ed25519 -C "{email}" -f {key_path} -N ""')
            run("eval $(ssh-agent -s) && ssh-add ~/.ssh/id_ed25519", check=False)

            if is_installed("gh"):
                if Confirm.ask("Add SSH key to GitHub?"):
                    hostname = run("hostname", capture=True).stdout.strip()
                    run(f"gh ssh-key add ~/.ssh/id_ed25519.pub --title '{hostname}'", check=False)

        tasks.append(("ssh_setup", "Generate SSH keys", setup_ssh))

    run_tasks(tasks, state)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 5: Developer Utilities
# ══════════════════════════════════════════════════════════════════════════════
def module_dev_utils(state: dict):
    console.print(Panel("[bold]Developer Utilities[/bold]", style="blue"))

    tools = [
        ("nvm", "NVM + Node + NPM", True),
        ("bun", "Bun", True),
        ("yarn", "Yarn", False),
        ("pnpm", "pnpm", False),
        ("brew", "Homebrew", True),
        ("wget", "wget", True),
        ("git", "Git", True),
        ("claude_code", "Claude Code", True),
        ("gemini_cli", "Gemini CLI", True),
    ]
    selected = select_items("Developer Utilities", tools)
    if not selected:
        return

    tasks = []

    if "git" in selected:
        tasks.append(("git", "Install git", lambda: apt_install("git")))

    if "wget" in selected:
        tasks.append(("wget", "Install wget", lambda: apt_install("wget", "curl")))

    if "nvm" in selected:
        tasks.extend([
            ("nvm", "Install NVM", lambda: run(
                "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash"
            )),
            ("node_lts", "Install Node LTS", lambda: run(
                'export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && '
                "nvm install --lts && nvm use --lts"
            )),
        ])

    if "bun" in selected:
        tasks.append(("bun", "Install Bun", lambda: run("curl -fsSL https://bun.sh/install | bash")))

    if "yarn" in selected:
        tasks.append(("yarn", "Install Yarn", lambda: run("npm install -g yarn || corepack enable")))

    if "pnpm" in selected:
        tasks.append(("pnpm", "Install pnpm", lambda: run("curl -fsSL https://get.pnpm.io/install.sh | sh -")))

    if "brew" in selected:
        tasks.append(("brew", "Install Homebrew", lambda: run(
            '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        )))

    if "claude_code" in selected:
        tasks.append(("claude_code", "Install Claude Code", lambda: run(
            "bun install -g @anthropic-ai/claude-code || npm install -g @anthropic-ai/claude-code"
        )))

    if "gemini_cli" in selected:
        tasks.append(("gemini_cli", "Install Gemini CLI", lambda: run(
            "bun install -g @anthropic-ai/gemini-cli || "
            "npm install -g @google/gemini-cli"
        )))

    run_tasks(tasks, state)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 6: Flatpak
# ══════════════════════════════════════════════════════════════════════════════
def module_flatpak(state: dict):
    console.print(Panel("[bold]Flatpak Setup[/bold]", style="blue"))

    tasks = [
        ("flatpak_install", "Install Flatpak", lambda: apt_install("flatpak")),
        ("flatpak_flathub", "Add Flathub repository", lambda: run(
            "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
        )),
        ("gnome_software_flatpak", "Install GNOME Software Flatpak plugin", lambda: apt_install(
            "gnome-software-plugin-flatpak"
        )),
        ("flatseal", "Install Flatseal", lambda: flatpak_install("com.github.tchx84.Flatseal")),
    ]

    run_tasks(tasks, state)
    console.print("[dim]Flathub (Bazaar) is now available in GNOME Software.[/dim]")


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 7: Quality of Life
# ══════════════════════════════════════════════════════════════════════════════
def module_qol(state: dict):
    console.print(Panel("[bold]Quality of Life[/bold]", style="blue"))

    items = [
        ("gnome_tweaks", "GNOME Tweaks + Extensions", True),
        ("kde_connect", "KDE Connect", True),
        ("scripts", "Shell scripts (rterm, yolo, spark, etc.)", True),
        ("wallpaper", "Set wallpaper", True),
        ("kando", "Kando (radial menu)", True),
        ("system_tools", "System Monitor + Disk Utility", True),
        ("terminal_tools", "yazi, zellij, btop, nvtop, starship", True),
        ("lazy_tools", "lazygit, lazydocker", True),
        ("volume", "Volume control (pavucontrol)", True),
        ("sunshine", "Sunshine + Moonlight (remote gaming)", False),
    ]
    selected = select_items("QoL Improvements", items)
    if not selected:
        return

    tasks = []

    if "gnome_tweaks" in selected:
        tasks.append(("gnome_tweaks", "Install GNOME Tweaks + Extensions", lambda: apt_install(
            "gnome-tweaks", "gnome-shell-extensions", "gnome-shell-extension-manager"
        )))

    if "kde_connect" in selected:
        tasks.append(("kde_connect", "Install KDE Connect", lambda: apt_install(
            "gnome-shell-extension-gsconnect"
        )))

    if "scripts" in selected:
        def install_scripts():
            scripts_dir = Path.home() / ".local" / "bin"
            scripts_dir.mkdir(parents=True, exist_ok=True)

            # Source scripts from the setup tool's bundled scripts directory
            bundled = Path(__file__).parent / "scripts"
            if bundled.exists():
                for script in bundled.iterdir():
                    if script.is_file():
                        dest = scripts_dir / script.name
                        shutil.copy2(script, dest)
                        dest.chmod(0o755)
                        console.print(f"  Installed: {script.name}")
            else:
                console.print("[yellow]  No bundled scripts found. Copy scripts to ./scripts/ directory.[/yellow]")

            # Ensure ~/.local/bin is in PATH
            bashrc = Path.home() / ".bashrc"
            path_line = 'export PATH="$HOME/.local/bin:$PATH"'
            if path_line not in bashrc.read_text():
                with open(bashrc, "a") as f:
                    f.write(f"\n# Added by ubuntu-setup\n{path_line}\n")

        tasks.append(("scripts", "Install shell scripts", install_scripts))

    if "wallpaper" in selected:
        tasks.append(("wallpaper", "Open wallpaper website", lambda: run(
            "xdg-open 'https://wallhaven.cc/search?categories=100&purity=110&sorting=toplist' &", check=False
        )))

    if "kando" in selected:
        def install_kando():
            url = get_url("kando")
            run(f"wget -q '{url}' -O /tmp/kando.deb && "
                "sudo dpkg -i /tmp/kando.deb || sudo apt install -f -y && rm /tmp/kando.deb")
        tasks.append(("kando", "Install Kando", install_kando))

    if "system_tools" in selected:
        tasks.append(("system_tools", "Install system tools", lambda: apt_install(
            "gnome-system-monitor", "gnome-disk-utility"
        )))

    if "terminal_tools" in selected:
        def install_terminal_tools():
            apt_install("btop")
            # nvtop
            apt_install("nvtop")
            # yazi via cargo or binary
            run("curl -fsSL https://github.com/sxyazi/yazi/releases/latest/download/yazi-x86_64-unknown-linux-gnu.zip "
                "-o /tmp/yazi.zip && unzip -o /tmp/yazi.zip -d /tmp/yazi && "
                "sudo mv /tmp/yazi/yazi-x86_64-unknown-linux-gnu/yazi /usr/local/bin/ && "
                "rm -rf /tmp/yazi /tmp/yazi.zip", check=False)
            # zellij
            run("curl -fsSL https://github.com/zellij-org/zellij/releases/latest/download/zellij-x86_64-unknown-linux-musl.tar.gz "
                "| sudo tar xz -C /usr/local/bin", check=False)
            # starship
            run("curl -sS https://starship.rs/install.sh | sh -s -- -y")
            # Add starship init to bashrc
            bashrc = Path.home() / ".bashrc"
            if "starship init" not in bashrc.read_text():
                with open(bashrc, "a") as f:
                    f.write('\n# Starship prompt\neval "$(starship init bash)"\n')

        tasks.append(("terminal_tools", "Install terminal tools", install_terminal_tools))

    if "lazy_tools" in selected:
        def install_lazy():
            # lazygit
            run("LAZYGIT_VERSION=$(curl -s 'https://api.github.com/repos/jesseduffield/lazygit/releases/latest' | "
                "grep -Po '\"tag_name\": \"v\\K[^\"]*') && "
                "curl -Lo /tmp/lazygit.tar.gz "
                "\"https://github.com/jesseduffield/lazygit/releases/latest/download/lazygit_${LAZYGIT_VERSION}_Linux_x86_64.tar.gz\" && "
                "sudo tar xf /tmp/lazygit.tar.gz -C /usr/local/bin lazygit && rm /tmp/lazygit.tar.gz")
            # lazydocker
            run("curl https://raw.githubusercontent.com/jesseduffield/lazydocker/master/scripts/install_update_linux.sh | bash")

        tasks.append(("lazy_tools", "Install lazygit + lazydocker", install_lazy))

    if "volume" in selected:
        tasks.append(("volume", "Install volume control", lambda: apt_install("pavucontrol")))

    if "sunshine" in selected:
        def install_sunshine():
            url = get_url("sunshine")
            run(f"wget -q '{url}' -O /tmp/sunshine.deb && "
                "sudo dpkg -i /tmp/sunshine.deb || sudo apt install -f -y && rm /tmp/sunshine.deb")

        tasks.extend([
            ("sunshine", "Install Sunshine", install_sunshine),
            ("moonlight", "Install Moonlight", lambda: flatpak_install("com.moonlight_stream.Moonlight")),
        ])

    run_tasks(tasks, state)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 8: Code / Development
# ══════════════════════════════════════════════════════════════════════════════
def module_code(state: dict):
    console.print(Panel("[bold]Code & Development[/bold]", style="blue"))

    items = [
        ("cursor", "Cursor", True),
        ("vscode", "VS Code", True),
        ("python", "Python + Miniconda3 + venv", True),
        ("repos", "CyberBrown repos (claude-mcp-manager, backup-manager)", True),
        ("tmux", "tmux", True),
        ("docker", "Docker", True),
    ]
    selected = select_items("Code Tools", items)
    if not selected:
        return

    tasks = []

    if "cursor" in selected:
        def install_cursor():
            os.makedirs(os.path.expanduser("~/Applications"), exist_ok=True)
            url = get_url("cursor")
            run(f"wget -q '{url}' -O ~/Applications/Cursor.AppImage && "
                "chmod +x ~/Applications/Cursor.AppImage")
        tasks.append(("cursor", "Install Cursor", install_cursor))

    if "vscode" in selected:
        def install_vscode():
            url = get_url("vscode")
            run(f"wget -q '{url}' -O /tmp/vscode.deb && "
                "sudo dpkg -i /tmp/vscode.deb || sudo apt install -f -y && rm /tmp/vscode.deb")
        tasks.append(("vscode", "Install VS Code", install_vscode))

    if "python" in selected:
        tasks.extend([
            ("python_deps", "Install Python build deps", lambda: apt_install(
                "python3", "python3-pip", "python3-venv", "python3-dev"
            )),
            ("miniconda", "Install Miniconda3", lambda: run(
                "wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh && "
                "bash /tmp/miniconda.sh -b -p $HOME/miniconda3 && "
                "rm /tmp/miniconda.sh && "
                "$HOME/miniconda3/bin/conda init bash"
            )),
        ])

    if "repos" in selected:
        def clone_repos():
            repos_dir = Path.home() / "repos"
            repos_dir.mkdir(exist_ok=True)
            for repo in ["claude-mcp-manager", "backup-manager"]:
                dest = repos_dir / repo
                if not dest.exists():
                    run(f"gh repo clone CyberBrown/{repo} {dest}", check=False)
                else:
                    console.print(f"  [dim]{repo} already cloned[/dim]")

        tasks.append(("repos", "Clone CyberBrown repos", clone_repos))

    if "tmux" in selected:
        tasks.append(("tmux", "Install tmux", lambda: apt_install("tmux")))

    if "docker" in selected:
        tasks.extend([
            ("docker_install", "Install Docker", lambda: run(
                "sudo apt install -y ca-certificates curl && "
                "sudo install -m 0755 -d /etc/apt/keyrings && "
                "sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && "
                "sudo chmod a+r /etc/apt/keyrings/docker.asc && "
                'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] '
                'https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | '
                "sudo tee /etc/apt/sources.list.d/docker.list > /dev/null && "
                "sudo apt update && "
                "sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
            )),
            ("docker_user", "Add user to docker group", lambda: run(
                f"sudo usermod -aG docker {os.environ['USER']}"
            )),
        ])

    run_tasks(tasks, state)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 9: Applications
# ══════════════════════════════════════════════════════════════════════════════
def module_apps(state: dict):
    console.print(Panel("[bold]Applications[/bold]", style="blue"))

    apps = [
        ("libreoffice", "LibreOffice", True),
        ("gimp", "GIMP", True),
        ("blender", "Blender", True),
        ("resolve", "DaVinci Resolve", False),
        ("steam", "Steam", True),
        ("vlc", "VLC", True),
        ("winamp", "Winamp (Qmmp)", True),
        ("clock", "GNOME Clock", True),
        ("gwenview", "Gwenview (image viewer)", True),
        ("ark", "Ark (archive manager)", True),
        ("freefilesync", "FreeFileSync", False),
        ("czkawka", "Czkawka (duplicate finder)", True),
        ("discord", "Discord", True),
        ("filezilla", "FileZilla", True),
        ("obs", "OBS Studio", True),
    ]
    selected = select_items("Applications", apps)
    if not selected:
        return

    tasks = []

    install_map = {
        "libreoffice": ("libreoffice_install", "Install LibreOffice", lambda: apt_install("libreoffice")),
        "gimp": ("gimp_install", "Install GIMP", lambda: apt_install("gimp")),
        "blender": ("blender_install", "Install Blender", lambda: snap_install("blender", classic=True)),
        "resolve": ("resolve_install", "DaVinci Resolve", lambda: console.print(
            "[yellow]  DaVinci Resolve requires manual download from: https://www.blackmagicdesign.com/products/davinciresolve[/yellow]"
        )),
        "steam": ("steam_install", "Install Steam", lambda: run(
            "sudo dpkg --add-architecture i386 && sudo apt update && "
            "sudo apt install -y steam-installer"
        )),
        "vlc": ("vlc_install", "Install VLC", lambda: apt_install("vlc")),
        "winamp": ("winamp_install", "Install Qmmp (Winamp-style player)", lambda: apt_install("qmmp")),
        "clock": ("clock_install", "Install GNOME Clock", lambda: apt_install("gnome-clocks")),
        "gwenview": ("gwenview_install", "Install Gwenview", lambda: apt_install("gwenview")),
        "ark": ("ark_install", "Install Ark", lambda: apt_install("ark")),
        "freefilesync": ("freefilesync_install", "Install FreeFileSync", lambda: run(
            "wget -q 'https://freefilesync.org/download/FreeFileSync_Latest_Linux.tar.gz' -O /tmp/ffs.tar.gz && "
            "tar xf /tmp/ffs.tar.gz -C /tmp && "
            "sudo /tmp/FreeFileSync*/FreeFileSync*.run --accept-licenses --confirm-command install && "
            "rm -rf /tmp/FreeFileSync* /tmp/ffs.tar.gz",
            check=False
        )),
        "czkawka": ("czkawka_install", "Install Czkawka", lambda: flatpak_install("com.github.qarmin.czkawka")),
        "discord": ("discord_install", "Install Discord", lambda: (
            run(f"wget -q '{get_url('discord')}' -O /tmp/discord.deb && "
                "sudo dpkg -i /tmp/discord.deb || sudo apt install -f -y && rm /tmp/discord.deb")
        )),
        "filezilla": ("filezilla_install", "Install FileZilla", lambda: apt_install("filezilla")),
        "obs": ("obs_install", "Install OBS Studio", lambda: run(
            "sudo add-apt-repository -y ppa:obsproject/obs-studio && "
            "sudo apt update && sudo apt install -y obs-studio"
        )),
    }

    for app_id in selected:
        if app_id in install_map:
            tasks.append(install_map[app_id])

    run_tasks(tasks, state)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN MENU
# ══════════════════════════════════════════════════════════════════════════════
MODULES = [
    ("surface", "Surface Linux Kernel", module_surface_linux),
    ("kitty", "Kitty Terminal", module_kitty),
    ("updates", "Updates & Drivers", module_updates),
    ("browsers", "Web Browsers", module_browsers),
    ("accounts", "Account Setup", module_accounts),
    ("dev_utils", "Developer Utilities", module_dev_utils),
    ("flatpak", "Flatpak", module_flatpak),
    ("qol", "Quality of Life", module_qol),
    ("code", "Code & Development", module_code),
    ("apps", "Applications", module_apps),
]


def show_banner():
    console.print(Panel(
        "[bold cyan]Ubuntu Setup Tool[/bold cyan]\n"
        "[dim]Post-installation configurator for Ubuntu 24.04 LTS[/dim]\n"
        "[dim]Run modules individually or all at once[/dim]",
        style="cyan",
        width=60,
    ))


def main_menu():
    state = load_state()

    while True:
        console.clear()
        show_banner()

        # Show module status
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", style="dim", width=4)
        table.add_column("Module", style="white")
        table.add_column("Status", width=12)

        for i, (mod_id, label, _) in enumerate(MODULES, 1):
            # Count completed tasks in this module
            completed = [t for t in state["completed"] if t.startswith(mod_id) or t in state["completed"]]
            status = "[green]done[/green]" if completed else "[dim]pending[/dim]"
            table.add_row(str(i), label, status)

        console.print(table)
        console.print()
        autostart_label = "[green]on[/green]" if autostart_enabled() else "[dim]off[/dim]"
        console.print(f"[dim]Launch on startup: {autostart_label} — toggle with 's'[/dim]")
        console.print("[dim]Enter module number, 'all' to run everything, 'reset' to clear state, or 'q' to quit[/dim]")

        choice = Prompt.ask("›").strip().lower()

        if choice == "q":
            console.print("[cyan]Setup complete. Enjoy your new system! 🚀[/cyan]")
            break
        elif choice == "all":
            for mod_id, label, func in MODULES:
                func(state)
                state = load_state()  # reload after each module
        elif choice == "reset":
            if Confirm.ask("Reset all progress?"):
                STATE_FILE.unlink(missing_ok=True)
                state = load_state()
        elif choice == "s":
            new_state = not autostart_enabled()
            set_autostart(new_state)
            console.print(
                f"[green]Launch on startup {'enabled' if new_state else 'disabled'}.[/green]"
            )
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(MODULES):
                mod_id, label, func = MODULES[idx]
                func(state)
                state = load_state()
                Prompt.ask("\n[dim]Press Enter to continue[/dim]")


if __name__ == "__main__":
    if os.geteuid() == 0:
        console.print("[red]Don't run this as root. The script will use sudo when needed.[/red]")
        sys.exit(1)
    main_menu()
