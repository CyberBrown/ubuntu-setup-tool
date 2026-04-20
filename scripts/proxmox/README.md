# Proxmox autoinstall helpers

Scripts for provisioning an Ubuntu-based workstation VM on a Proxmox node that comes up with `ubuntu-setup-tool` already cloned, Tailscale already joined, and xrdp/openssh listening.

## Files

| File | Purpose |
|------|---------|
| `user-data.template` | cloud-init autoinstall user-data (Subiquity). Placeholders: `{{SSH_KEY}}`, `{{TAILSCALE_KEY}}`, `{{USERNAME}}`, `{{HOSTNAME}}`, `{{PASSWORD_HASH}}`, `{{IP_CIDR}}`, `{{GATEWAY}}`. Also ships a `/root/first-boot.sh` script via `write_files` that runs KDE + Tailscale install on first boot of the installed system. |
| `meta-data.template` | NoCloud meta-data. Placeholders: `{{HOSTNAME}}`. |
| `make-seed.sh` | Renders both templates, builds a NoCloud seed ISO at `$OUTPUT`. |
| `create-vm.sh` | Wraps `qm create` + `qm start` for a 6 vCPU / 16 GiB / 120 GiB VM with OVMF + virtio + qxl + SPICE. |

## Usage

On the Proxmox host (after copying this folder to `/root/proxmox-scripts/`):

```bash
# 1. Download Ubuntu Server ISO
cd /var/lib/vz/template/iso
wget https://releases.ubuntu.com/24.04/ubuntu-24.04.3-live-server-amd64.iso -O ubuntu-24.04-live-server.iso

# 2. Build the seed
HOSTNAME=kubuntu-ws \
USERNAME=chris \
SSH_KEY="ssh-ed25519 AAAAC3... you@host" \
TAILSCALE_KEY=tskey-auth-... \
PASSWORD_HASH="$(openssl passwd -6)" \
IP_CIDR=10.10.10.200/24 \
GATEWAY=10.10.10.1 \
OUTPUT=/var/lib/vz/template/iso/kubuntu-ws-seed.iso \
bash /root/proxmox-scripts/make-seed.sh

# 3. Create & start VM
VMID=200 NAME=kubuntu-ws BRIDGE=vmbr1 \
IP=10.10.10.200/24 GATEWAY=10.10.10.1 \
ISO=local:iso/ubuntu-24.04-live-server.iso \
SEED=local:iso/kubuntu-ws-seed.iso \
bash /root/proxmox-scripts/create-vm.sh

# 4. Open the Proxmox web UI noVNC console and type "yes" + Enter at
#    Subiquity's "Continue with autoinstall?" prompt. Then wait for
#    the VM to power itself off (~10-15 min — base packages only).

# 5. Detach ISOs and boot from disk
qm set 200 --ide2 none,media=cdrom --ide3 none,media=cdrom
qm set 200 --boot order=scsi0
qm start 200

# 6. /root/first-boot.sh runs on first boot of the installed system,
#    installing Tailscale, xrdp, qemu-guest-agent, kubuntu-desktop,
#    and cloning ubuntu-setup-tool. Log: /var/log/first-boot.log.
#    The VM reboots into a graphical KDE login when done.
```

## Architecture notes

- **Why split install into autoinstall + first-boot.sh?** Subiquity's `late-commands` run in a chroot of the target filesystem after `restore_apt_config` has reverted sources.list to the stock Ubuntu archives. `apt-get install` inside that chroot is brittle (exit 100 is common for non-trivial packages, and the error context lives in a ramdisk crash file you can't easily extract). Running the heavy installs on first boot of the installed system is more reliable and leaves a readable `/var/log/first-boot.log` on disk for post-mortem.
- **Why Ubuntu Server and not Kubuntu?** Kubuntu's live ISO ships Calamares, which doesn't support headless autoinstall. Ubuntu Server + `kubuntu-desktop` as a first-boot apt install produces an identical-looking KDE workstation and is fully automatable.
- **Why a static IP and not DHCP?** The vmbr1 NAT bridge on Proxmox has no DHCP server by default. DHCP fallback will leave the VM without an IPv4 address → first-boot DNS fails → nothing installs. The `{{IP_CIDR}}` + `{{GATEWAY}}` placeholders bake a static netplan config into the autoinstall.
- **Why two CD-ROMs?** `ide2` holds the Ubuntu live ISO (Subiquity boots from here); `ide3` holds the NoCloud seed ISO (Subiquity reads autoinstall config from here). Both are detached after install completes.
- **Why `shutdown: poweroff` instead of reboot?** Subiquity's default is reboot, but the VM's boot order starts with `ide2;scsi0` — so rebooting lands right back on the live installer. Powering off lets the operator detach the ISOs first and then boot cleanly from disk.
- **Why does the operator have to type "yes"?** Subiquity only auto-runs autoinstall when `autoinstall` is on the kernel command line. The stock Ubuntu Server ISO's GRUB config doesn't include it, and remastering the ISO to add it is more work than one manual Enter press during provisioning. The workaround is one keystroke per VM.

## Troubleshooting

**Autoinstall never runs — installer drops to a live shell.** The seed ISO wasn't picked up. Confirm the `ide3` device is attached to the seed ISO (not empty). From a live installer shell, look under `/cdrom` or `/media` for `user-data`.

**Install completes but the VM has no IPv4.** Usually means `IP_CIDR`/`GATEWAY` didn't match the bridge. SSH in via the Proxmox host (`pct enter` won't work for a VM — use noVNC + `chris` login), then `sudo cat /etc/netplan/` to check what got baked in, and `sudo netplan apply` after editing.

**Tailscale never joins.** Check `/var/log/first-boot.log`. Most common cause is a missing or expired auth key. `sudo tailscale up --authkey=<new-key> --hostname=<name> --ssh` to retry manually.

**KDE login doesn't appear.** The SDDM display manager may not be enabled. `sudo systemctl enable --now sddm` on the VM.
