# Ubuntu Setup Tool

Post-installation configurator for Ubuntu 24.04 LTS. Provides a terminal UI for installing apps, configuring accounts, and setting up a development environment on fresh Ubuntu installs.

## Quick Start

### Phase 1: Prepare USB Boot Drive

1. Download the Ubuntu 24.04 LTS ISO (or run `bash prepare-usb.sh` to download it)
2. Flash the ISO to a USB drive using [balenaEtcher](https://etcher.balena.io/)
3. Copy this entire `ubuntu-setup-tool/` folder to the USB (or a second USB)

### Phase 2: Install Ubuntu

1. Boot from USB → Install Ubuntu 24.04 LTS with default settings
2. Complete first-boot setup (user account, timezone, etc.)

### Phase 3: Run Setup Tool

```bash
# From USB or cloned repo:
cd ubuntu-setup-tool
python3 setup.py

# Or bootstrap from scratch:
bash get-started.sh

# Or one-liner from GitHub:
curl -fsSL https://raw.githubusercontent.com/CyberBrown/ubuntu-setup-tool/main/get-started.sh | bash
```

## Modules

| # | Module | Description |
|---|--------|-------------|
| 0 | Surface Linux | Optional kernel for Microsoft Surface devices (auto-detected) |
| 1 | Kitty | GPU-accelerated terminal with theme selection |
| 2 | Updates & Drivers | System updates, GPU drivers, firmware |
| 3 | Web Browsers | Firefox, Chrome, Brave, Chromium, Helium + extension reminders |
| 4 | Account Setup | Proton suite, GitHub CLI, Cloudflare, SSH keys |
| 5 | Dev Utilities | NVM/Node, Bun, Yarn, pnpm, Brew, Claude Code, Gemini CLI |
| 6 | Flatpak | Flatpak + Flathub + Flatseal |
| 7 | QoL | Keybindings, GNOME tweaks, shell scripts, terminal tools |
| 8 | Code | Cursor, VS Code, Python/Miniconda, Docker, tmux |
| 9 | Apps | LibreOffice, GIMP, Blender, OBS, Discord, VLC, and more |

## State Tracking

Progress is saved to `~/.ubuntu-setup-state.json`. If the tool is interrupted, it will skip already-completed tasks on next run. Use the "reset" command in the main menu to start fresh.

## Adding Shell Scripts

Place scripts in the `scripts/` directory before running the tool. They'll be copied to `~/.local/bin/` during the QoL module. Expected scripts:

- `rterm` — Remote terminal shortcut
- `yolo` — Quick commit and push
- `spark` — SSH to DGX Spark
- `get-started` — Session startup
- `wrap-up` — Session cleanup

## Surface Linux

The tool supports both online and offline installation of the linux-surface kernel:

- **Online**: Adds the linux-surface apt repository and installs packages
- **Offline**: If `.deb` packages are present in `surface-linux/debs/`, installs from local files

Run `prepare-usb.sh` with the surface option to pre-download packages for offline install.

## Keyboard Remapping (Planned)

Keyboard remapping is deferred to a future release. The goal is unified Ctrl+C/V for copy/paste across all apps (terminal and GUI) using a compositor-level tool like `keyd` or `xremap`, avoiding the current mess where some apps use Ctrl+V and others require Ctrl+Shift+V.

## Dynamic URL Resolution

Apps with unstable download URLs (Cursor, Discord, Proton, VS Code, etc.) use a dynamic resolver:

1. Checks a local cache (`~/.ubuntu-setup-url-cache.json`, 24h TTL)
2. Sends a task to Distributed Electrons (`intake.distributedelectrons.com`) to find the current URL via LLM
3. Falls back to a hardcoded URL if DE is unreachable

This means the setup tool stays functional even as vendors change their download paths. The `DOWNLOAD_REGISTRY` in `setup.py` lists all dynamically-resolved apps.

## Project Structure

```
ubuntu-setup-tool/
├── setup.py              # Main TUI application
├── prepare-usb.sh        # USB preparation script
├── get-started.sh        # Bootstrap script
├── README.md
├── scripts/              # Shell scripts to install
│   └── (rterm, yolo, spark, etc.)
├── configs/              # Config templates
│   └── (kitty.conf, starship.toml, etc.)
├── surface-linux/
│   └── debs/             # Offline surface-linux packages
└── downloads/            # Downloaded ISO and packages
```
