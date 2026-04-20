# Ubuntu Setup Tool

Post-installation configurator for Ubuntu 24.04 LTS. Provides a terminal UI for installing apps, configuring accounts, and setting up a development environment on fresh Ubuntu installs.

## USB install

Use this flow when installing on bare metal from scratch.

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

## Network install (Proxmox)

Use this flow when installing into a VM on a Proxmox host. The VM comes up with the setup tool already cloned, Tailscale joined, and xrdp listening — on first login you can jump straight to `python3 setup.py`.

### Prerequisites

- A Proxmox VE 8.x node with an ISO storage (e.g. `local:iso`) and a network bridge the VM should land on (this repo uses `vmbr1` NAT + Tailscale; adjust to taste).
- A Tailscale auth key (reusable + preauth). Create one at https://login.tailscale.com/admin/settings/keys.
- An SSH public key you want to pre-authorize on the VM.

### 1. Copy the helpers to the Proxmox host

From your workstation:

```bash
rsync -av scripts/proxmox/ root@<proxmox-host>:/root/proxmox-scripts/
```

### 2. Download the Ubuntu Server ISO on the Proxmox host

```bash
ssh root@<proxmox-host>
cd /var/lib/vz/template/iso
wget https://releases.ubuntu.com/24.04/ubuntu-24.04.3-live-server-amd64.iso -O ubuntu-24.04-live-server.iso
```

(Why Ubuntu Server and not Kubuntu? Kubuntu's live ISO uses Calamares, which isn't scriptable. We install `kubuntu-desktop` via cloud-init first-boot so you still get KDE Plasma on first login.)

### 3. Build the cloud-init seed ISO

Still on the Proxmox host:

```bash
HOSTNAME=kubuntu-ws \
USERNAME=chris \
SSH_KEY="ssh-ed25519 AAAAC3... you@host" \
TAILSCALE_KEY=tskey-auth-... \
PASSWORD_HASH="$(openssl passwd -6 'some-strong-password')" \
IP_CIDR=10.10.10.200/24 \
GATEWAY=10.10.10.1 \
OUTPUT=/var/lib/vz/template/iso/kubuntu-ws-seed.iso \
bash /root/proxmox-scripts/make-seed.sh
```

### 4. Create and start the VM

```bash
VMID=200 NAME=kubuntu-ws BRIDGE=vmbr1 \
IP=10.10.10.200/24 GATEWAY=10.10.10.1 \
ISO=local:iso/ubuntu-24.04-live-server.iso \
SEED=local:iso/kubuntu-ws-seed.iso \
bash /root/proxmox-scripts/create-vm.sh
```

Open the VM's console in the Proxmox web UI. Subiquity asks **"Continue with autoinstall? (yes\|no)"** once — type `yes` + Enter (the installer requires this confirmation since `autoinstall` isn't on the kernel cmdline of the stock ISO). After that, the VM installs unattended and powers itself off.

### 5. After the install completes

Detach the ISOs and boot from disk:

```bash
qm set 200 --ide2 none,media=cdrom --ide3 none,media=cdrom
qm set 200 --boot order=scsi0
qm start 200
```

On first boot, `/root/first-boot.sh` (installed via cloud-init) runs Tailscale, xrdp, `kubuntu-desktop`, and clones `ubuntu-setup-tool` into `/home/<username>/`. It takes ~20 minutes and logs to `/var/log/first-boot.log`. The VM reboots into a KDE login when finished.

### 6. Connect and run the setup tool

Once `tailscale status` (on any peer tailnet node) shows the new VM online:

```bash
ssh <username>@<hostname>
cd ~/ubuntu-setup-tool
python3 setup.py
```

Or RDP to `<hostname>:3389` for a KDE Plasma desktop session.

See [`scripts/proxmox/README.md`](scripts/proxmox/README.md) for details on the helper scripts.

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
