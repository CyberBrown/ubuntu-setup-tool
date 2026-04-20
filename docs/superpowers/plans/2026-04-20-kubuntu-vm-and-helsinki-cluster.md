# Kubuntu VM on Snoochie + Helsinki Proxmox Cluster — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a Kubuntu 24.04 desktop VM on Snoochie (Proxmox) that's SSH/RDP-reachable via Tailscale with the `ubuntu-setup-tool` repo pre-cloned for Chris to run immediately; then provision Proxmox on Boochies and join it to the existing `helsinki` cluster; then document the new flow in the repo README.

**Architecture:** Infrastructure-as-scripts in `scripts/proxmox/` (templated `user-data`, seed-ISO builder, VM-create wrapper) that the repo can reuse for future VMs. Cluster uses a Hetzner vSwitch (VLAN 4000, MTU 1400) for corosync ring0 with public IPs as ring1 fallback. A QDevice on the existing `sandstorm-helsinki-1` LXC breaks 2-node quorum ties. See `docs/superpowers/specs/2026-04-20-kubuntu-vm-and-helsinki-cluster-design.md` for the full design.

**Tech Stack:** Proxmox VE 8.4, Ubuntu Server 24.04 + `kubuntu-desktop`, cloud-init (NoCloud autoinstall), Hetzner Robot API, Tailscale, corosync, xrdp.

**Environment facts (captured 2026-04-20):**
- Snoochie: `65.21.205.247`, PVE 8.4.18, cluster `helsinki` (1 node), storage `local` + `local-lvm` (841 GiB free), bridges `vmbr0` (public) + `vmbr1` (10.10.10.0/24 NAT). Root password in Proton Pass (`Snoochie Proxmox — root (current)`).
- Boochies: `135.181.215.247`, HEL1-DC3, port 8006 closed (PVE not installed). Hetzner server #2974693.
- Robot API creds: Proton Pass `Hetzner Robot — API/webservice`.
- Tailscale auth key: Proton Pass `Tailscale — autoinstall auth key (reusable, preauth)`.
- Chris's SSH public key (on monsta-mash agent): `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIETlcNE03TtZBPLfMJcJY0RRXdiuBstQIXDOLB5ZanOW brown.cy@gmail.com`.
- `pass-cli` is authenticated on monsta-mash (PAT `monsta-mash`). If the session drops, run `pass-cli logout --force && pass-cli login --pat <pat from ~/.claude/credentials.local.md>`.

**"Testing" in this plan** means verification commands with exact expected output — not unit tests. Each task ends with a concrete check before the next one starts.

**Commit cadence:** Commit after each repo-side task. Infrastructure-only tasks (running `qm`, `pvecm`, etc.) have no repo artifacts to commit; they're verified in-line and moved past.

---

## File Structure

Repo-side files this plan creates or modifies:

- Create: `scripts/proxmox/user-data.template` — cloud-init autoinstall user-data template with placeholders `{{SSH_KEY}}`, `{{TAILSCALE_KEY}}`, `{{USERNAME}}`, `{{HOSTNAME}}`, `{{PASSWORD_HASH}}`.
- Create: `scripts/proxmox/meta-data.template` — NoCloud meta-data template (just `instance-id` + `local-hostname`).
- Create: `scripts/proxmox/make-seed.sh` — bash script that substitutes placeholders and builds a seed ISO with `cloud-localds` (or `genisoimage` fallback).
- Create: `scripts/proxmox/create-vm.sh` — wraps the `qm create` + `qm start` one-liner, with variables at the top.
- Create: `scripts/proxmox/README.md` — one-page "how to use these scripts" reference, linked from the main README.
- Modify: `README.md` — rename `## Quick Start` section to `## USB install`, add `## Network install (Proxmox)` section right after it, cross-link them.

Infrastructure-side artifacts (live on the Proxmox hosts, not in the repo):

- `/var/lib/vz/template/iso/ubuntu-24.04-live-server.iso` on snoochie — Ubuntu Server ISO.
- `/var/lib/vz/template/iso/kubuntu-ws-seed.iso` on snoochie — autoinstall seed ISO (generated on snoochie by uploading and running `make-seed.sh`).
- VM 200 `kubuntu-ws` on snoochie.
- Proxmox VE 8 on Boochies.
- vSwitch `helsinki-cluster` (VLAN 4000) in Hetzner, attached to both servers.
- QDevice package on CT 100 (`sandstorm-helsinki-1`).

---

## Phase 1 — Repo-side scaffolding (Tasks 1–4)

The scripts have to exist before we use them. We build and commit them first so the README can reference real files and so the VM-creation recipe is reproducible.

### Task 1: Create `scripts/proxmox/user-data.template`

**Files:**
- Create: `scripts/proxmox/user-data.template`

- [ ] **Step 1: Write the template**

Create `scripts/proxmox/user-data.template` with this exact content:

```yaml
#cloud-config
autoinstall:
  version: 1
  locale: en_US.UTF-8
  keyboard:
    layout: us
  identity:
    hostname: {{HOSTNAME}}
    username: {{USERNAME}}
    password: "{{PASSWORD_HASH}}"
  ssh:
    install-server: true
    allow-pw: false
    authorized-keys:
      - {{SSH_KEY}}
  storage:
    layout:
      name: direct
  packages:
    - openssh-server
    - git
    - python3
    - python3-pip
    - curl
    - ca-certificates
    - gnupg
    - xrdp
    - qemu-guest-agent
  late-commands:
    - curtin in-target --target=/target -- bash -c 'curl -fsSL https://tailscale.com/install.sh | sh'
    - curtin in-target --target=/target -- tailscale up --authkey={{TAILSCALE_KEY}} --hostname={{HOSTNAME}} --ssh
    - curtin in-target --target=/target -- bash -c 'DEBIAN_FRONTEND=noninteractive apt-get install -y kubuntu-desktop'
    - curtin in-target --target=/target -- systemctl set-default graphical.target
    - curtin in-target --target=/target -- adduser {{USERNAME}} ssl-cert
    - curtin in-target --target=/target -- systemctl enable xrdp
    - curtin in-target --target=/target -- sudo -u {{USERNAME}} git clone https://github.com/CyberBrown/ubuntu-setup-tool /home/{{USERNAME}}/ubuntu-setup-tool
    - curtin in-target --target=/target -- chown -R {{USERNAME}}:{{USERNAME}} /home/{{USERNAME}}/ubuntu-setup-tool
  user-data:
    disable_root: true
    timezone: Europe/Helsinki
```

- [ ] **Step 2: Verify the file exists and has no unreplaced placeholders besides the intentional ones**

Run:
```bash
grep -oE '{{[A-Z_]+}}' scripts/proxmox/user-data.template | sort -u
```

Expected output (exactly these five placeholders, in any order):
```
{{HOSTNAME}}
{{PASSWORD_HASH}}
{{SSH_KEY}}
{{TAILSCALE_KEY}}
{{USERNAME}}
```

- [ ] **Step 3: Commit**

```bash
git add scripts/proxmox/user-data.template
git commit -m "feat(proxmox): add cloud-init autoinstall user-data template

Subiquity/NoCloud user-data template with placeholders for SSH key,
Tailscale auth key, username, hostname, and password hash. Installs
openssh, xrdp, qemu-guest-agent, and kubuntu-desktop, joins Tailscale,
and clones ubuntu-setup-tool into the user's home.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Create `scripts/proxmox/meta-data.template`

**Files:**
- Create: `scripts/proxmox/meta-data.template`

- [ ] **Step 1: Write the template**

Create `scripts/proxmox/meta-data.template` with:

```yaml
instance-id: {{HOSTNAME}}-1
local-hostname: {{HOSTNAME}}
```

- [ ] **Step 2: Commit**

```bash
git add scripts/proxmox/meta-data.template
git commit -m "feat(proxmox): add NoCloud meta-data template

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Create `scripts/proxmox/make-seed.sh`

**Files:**
- Create: `scripts/proxmox/make-seed.sh`

- [ ] **Step 1: Write the script**

Create `scripts/proxmox/make-seed.sh` with this exact content:

```bash
#!/usr/bin/env bash
# make-seed.sh — build a cloud-init NoCloud seed ISO from templates.
#
# Usage (on the Proxmox host):
#   HOSTNAME=kubuntu-ws \
#   USERNAME=chris \
#   SSH_KEY="ssh-ed25519 AAAAC3... user@host" \
#   TAILSCALE_KEY=tskey-auth-... \
#   PASSWORD_HASH='$6$...' \
#   OUTPUT=/var/lib/vz/template/iso/kubuntu-ws-seed.iso \
#   ./make-seed.sh
#
# Requires genisoimage (preinstalled on Proxmox) or cloud-image-utils.

set -euo pipefail

: "${HOSTNAME:?HOSTNAME is required}"
: "${USERNAME:?USERNAME is required}"
: "${SSH_KEY:?SSH_KEY is required}"
: "${TAILSCALE_KEY:?TAILSCALE_KEY is required}"
: "${PASSWORD_HASH:?PASSWORD_HASH is required}"
: "${OUTPUT:?OUTPUT is required}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

render() {
  local template="$1"
  local out="$2"
  sed \
    -e "s|{{HOSTNAME}}|${HOSTNAME}|g" \
    -e "s|{{USERNAME}}|${USERNAME}|g" \
    -e "s|{{SSH_KEY}}|${SSH_KEY}|g" \
    -e "s|{{TAILSCALE_KEY}}|${TAILSCALE_KEY}|g" \
    -e "s|{{PASSWORD_HASH}}|${PASSWORD_HASH}|g" \
    "$template" > "$out"
}

render "$SCRIPT_DIR/user-data.template" "$WORKDIR/user-data"
render "$SCRIPT_DIR/meta-data.template" "$WORKDIR/meta-data"

# Subiquity expects the autoinstall file at the root of the seed ISO
# as well; it follows /autoinstall.yaml when datasource is NoCloud.
cp "$WORKDIR/user-data" "$WORKDIR/autoinstall.yaml"

if command -v cloud-localds >/dev/null 2>&1; then
  cloud-localds "$OUTPUT" "$WORKDIR/user-data" "$WORKDIR/meta-data"
else
  genisoimage -output "$OUTPUT" \
    -volid cidata \
    -joliet -rock \
    "$WORKDIR/user-data" "$WORKDIR/meta-data" "$WORKDIR/autoinstall.yaml" \
    >/dev/null 2>&1
fi

echo "Wrote $OUTPUT"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/proxmox/make-seed.sh
```

- [ ] **Step 3: Smoke-test locally (placeholders substitute correctly)**

Run:
```bash
HOSTNAME=test USERNAME=test SSH_KEY=test-key TAILSCALE_KEY=tskey-test \
  PASSWORD_HASH='$6$test' OUTPUT=/tmp/test-seed.iso \
  ./scripts/proxmox/make-seed.sh 2>&1
```

Expected: single line `Wrote /tmp/test-seed.iso`. `ls -la /tmp/test-seed.iso` shows a file of at least 300 KB.

Clean up:
```bash
rm /tmp/test-seed.iso
```

- [ ] **Step 4: Commit**

```bash
git add scripts/proxmox/make-seed.sh
git commit -m "feat(proxmox): add seed-ISO builder script

Renders user-data.template and meta-data.template with env-var values
and builds a cloud-init NoCloud seed ISO using cloud-localds or
genisoimage. Requires HOSTNAME, USERNAME, SSH_KEY, TAILSCALE_KEY,
PASSWORD_HASH, and OUTPUT env vars.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Create `scripts/proxmox/create-vm.sh`

**Files:**
- Create: `scripts/proxmox/create-vm.sh`

- [ ] **Step 1: Write the script**

Create `scripts/proxmox/create-vm.sh`:

```bash
#!/usr/bin/env bash
# create-vm.sh — create and start a Proxmox VM suitable for the
# ubuntu-setup-tool autoinstall flow.
#
# Usage (on the Proxmox host):
#   VMID=200 NAME=kubuntu-ws BRIDGE=vmbr1 \
#   IP=10.10.10.200/24 GATEWAY=10.10.10.1 \
#   ISO=local:iso/ubuntu-24.04-live-server.iso \
#   SEED=local:iso/kubuntu-ws-seed.iso \
#   STORAGE=local-lvm DISK_GB=120 MEMORY_MB=16384 CORES=6 \
#   ./create-vm.sh

set -euo pipefail

: "${VMID:?VMID required}"
: "${NAME:?NAME required}"
: "${BRIDGE:=vmbr1}"
: "${IP:?IP required (e.g. 10.10.10.200/24)}"
: "${GATEWAY:?GATEWAY required}"
: "${ISO:?ISO required}"
: "${SEED:?SEED required}"
: "${STORAGE:=local-lvm}"
: "${DISK_GB:=120}"
: "${MEMORY_MB:=16384}"
: "${CORES:=6}"

if qm status "$VMID" >/dev/null 2>&1; then
  echo "VM $VMID already exists — refusing to overwrite" >&2
  exit 1
fi

qm create "$VMID" \
  --name "$NAME" \
  --memory "$MEMORY_MB" \
  --cores "$CORES" \
  --cpu host \
  --bios ovmf \
  --machine q35 \
  --efidisk0 "${STORAGE}:1,format=raw,efitype=4m" \
  --scsihw virtio-scsi-single \
  --scsi0 "${STORAGE}:${DISK_GB},discard=on,ssd=1" \
  --ide2 "${ISO},media=cdrom" \
  --ide3 "${SEED},media=cdrom" \
  --net0 "virtio,bridge=${BRIDGE},firewall=0" \
  --ipconfig0 "ip=${IP},gw=${GATEWAY}" \
  --agent enabled=1 \
  --vga qxl \
  --serial0 socket \
  --ostype l26 \
  --boot "order=ide2;scsi0"

qm start "$VMID"
echo "Started VM $VMID ($NAME). Watch noVNC in the Proxmox web UI."
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/proxmox/create-vm.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/proxmox/create-vm.sh
git commit -m "feat(proxmox): add VM-create wrapper script

Wraps the qm create incantation for an autoinstall-seeded Ubuntu
Server VM with OVMF/q35, virtio-scsi, qxl+SPICE, and a second
CD-ROM for the cloud-init NoCloud seed. Refuses to clobber an
existing VMID.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2 — Provision the Kubuntu VM on Snoochie (Tasks 5–10)

These tasks run on snoochie via SSH. There's no repo commit at the end of each — they're infrastructure operations verified by output of the next command.

**Helper: SSH wrapper**

All snoochie commands below are meant to be run as:
```bash
sshpass -p "$(pass-cli item view --vault-name Claude --item-title 'Snoochie Proxmox — root (current)' --field password)" \
  ssh -o StrictHostKeyChecking=accept-new root@65.21.205.247 '<command>'
```

For brevity, the tasks show only `<command>`. Wrap them yourself. If your SSH agent has passwordless access set up after first login, you may drop sshpass.

### Task 5: Upload Ubuntu Server 24.04 ISO to snoochie

- [ ] **Step 1: Download the ISO to `local:iso` on snoochie**

On snoochie:
```bash
cd /var/lib/vz/template/iso
wget -q --show-progress https://releases.ubuntu.com/24.04/ubuntu-24.04.3-live-server-amd64.iso -O ubuntu-24.04-live-server.iso
```

- [ ] **Step 2: Verify**

```bash
ls -la /var/lib/vz/template/iso/ubuntu-24.04-live-server.iso
pvesm list local --content iso | grep ubuntu-24.04
```

Expected: file ~2.7 GB, listed by `pvesm`.

---

### Task 6: Copy repo scripts to snoochie and build the seed ISO

- [ ] **Step 1: Mint Chris's SSH key variable on monsta-mash**

On monsta-mash:
```bash
SSH_KEY_VAL="$(ssh-add -L | grep brown.cy@gmail.com)"
echo "$SSH_KEY_VAL"
```

Expected: one line starting `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIETlcNE03TtZBPLfMJcJY0RRXdiuBstQIXDOLB5ZanOW brown.cy@gmail.com`.

- [ ] **Step 2: Generate a password hash for the `chris` user (fallback login if SSH ever breaks)**

On monsta-mash:
```bash
read -s CHRIS_VM_PW
PW_HASH="$(openssl passwd -6 "$CHRIS_VM_PW")"
echo "$PW_HASH"
```

Pick a memorable password and paste when prompted. Save to Proton Pass:
```bash
pass-cli item create login --vault-name Claude \
  --title "kubuntu-ws — chris user password" \
  --username "chris" \
  --password "$CHRIS_VM_PW" \
  --url "ssh://chris@kubuntu-ws"
unset CHRIS_VM_PW
```

- [ ] **Step 3: Fetch the Tailscale auth key**

```bash
TS_KEY="$(pass-cli item view --vault-name Claude --item-title 'Tailscale — autoinstall auth key (reusable, preauth)' --field password)"
```

- [ ] **Step 4: Copy the `scripts/proxmox/` tree to snoochie**

```bash
cd ~/projects/ubuntu-setup-tool
SNOOCHIE_PW="$(pass-cli item view --vault-name Claude --item-title 'Snoochie Proxmox — root (current)' --field password)"
sshpass -p "$SNOOCHIE_PW" rsync -av scripts/proxmox/ root@65.21.205.247:/root/proxmox-scripts/
```

Expected: three files transferred.

- [ ] **Step 5: Build the seed ISO on snoochie**

```bash
sshpass -p "$SNOOCHIE_PW" ssh root@65.21.205.247 "
HOSTNAME=kubuntu-ws \
USERNAME=chris \
SSH_KEY='$SSH_KEY_VAL' \
TAILSCALE_KEY='$TS_KEY' \
PASSWORD_HASH='$PW_HASH' \
OUTPUT=/var/lib/vz/template/iso/kubuntu-ws-seed.iso \
bash /root/proxmox-scripts/make-seed.sh
"
```

(Double quotes on the outer string so the local shell expands `$SSH_KEY_VAL` etc. before `ssh` ships the command; single quotes on each value protect spaces.)

- [ ] **Step 6: Verify the seed is present in the ISO storage**

```bash
sshpass -p "$SNOOCHIE_PW" ssh root@65.21.205.247 'pvesm list local --content iso | grep kubuntu-ws-seed'
```

Expected: one line ending `kubuntu-ws-seed.iso`.

- [ ] **Step 7: Clean shell history of the key**

```bash
history -d $(history | tail -n 20 | grep TAILSCALE_KEY | head -1 | awk '{print $1}') 2>/dev/null || true
unset TS_KEY PW_HASH
```

---

### Task 7: Create and start VM 200

- [ ] **Step 1: Create the VM**

```bash
sshpass -p "$SNOOCHIE_PW" ssh root@65.21.205.247 "
VMID=200 NAME=kubuntu-ws BRIDGE=vmbr1 \
IP=10.10.10.200/24 GATEWAY=10.10.10.1 \
ISO=local:iso/ubuntu-24.04-live-server.iso \
SEED=local:iso/kubuntu-ws-seed.iso \
STORAGE=local-lvm DISK_GB=120 MEMORY_MB=16384 CORES=6 \
bash /root/proxmox-scripts/create-vm.sh
"
```

Expected final line: `Started VM 200 (kubuntu-ws). Watch noVNC in the Proxmox web UI.`

- [ ] **Step 2: Open noVNC (manual)**

In a browser: `https://65.21.205.247:8006` → Datacenter → snoochie → 200 (kubuntu-ws) → Console. You should see Subiquity booting. If it drops to the live installer prompt instead of auto-running, check `/var/log/installer/autoinstall-user-data` inside the installer shell — usually means the seed ISO wasn't picked up.

- [ ] **Step 3: Monitor install progress**

```bash
sshpass -p "$SNOOCHIE_PW" ssh root@65.21.205.247 'qm status 200; qm config 200 | head -20'
```

Expected: `status: running`.

Install takes ~20–30 min (Ubuntu base ~10 min + `kubuntu-desktop` ~10–15 min). Poll every 5 min.

---

### Task 8: Wait for autoinstall completion and verify first boot

- [ ] **Step 1: Wait for VM to shutdown (autoinstall's final stage powers off)**

Poll:
```bash
sshpass -p "$SNOOCHIE_PW" ssh root@65.21.205.247 'qm status 200'
```

Expected eventually: `status: stopped`.

- [ ] **Step 2: Detach install ISO and seed ISO, boot from disk only**

```bash
sshpass -p "$SNOOCHIE_PW" ssh root@65.21.205.247 '
  qm set 200 --ide2 none,media=cdrom
  qm set 200 --ide3 none,media=cdrom
  qm set 200 --boot order=scsi0
  qm start 200
'
```

- [ ] **Step 3: Wait for Tailscale to come online**

On monsta-mash, poll:
```bash
tailscale status | grep kubuntu-ws
```

Expected within ~2 min of boot: one line showing `kubuntu-ws` with a 100.x.y.z address and `active` or `idle`.

- [ ] **Step 4: Verify SSH works over Tailscale**

```bash
ssh chris@kubuntu-ws 'hostname && whoami && ls ~/ubuntu-setup-tool/setup.py && cat /etc/os-release | head -2'
```

Expected:
```
kubuntu-ws
chris
/home/chris/ubuntu-setup-tool/setup.py
PRETTY_NAME="Ubuntu 24.04.X LTS"
...
```

- [ ] **Step 5: Verify xrdp is listening**

```bash
ssh chris@kubuntu-ws 'ss -ltn | grep :3389'
```

Expected: one LISTEN line on `*:3389`.

- [ ] **Step 6: Verify KDE Plasma is installed**

```bash
ssh chris@kubuntu-ws 'dpkg -l kubuntu-desktop | tail -1'
```

Expected line starts with `ii  kubuntu-desktop`.

---

### Task 9: Smoke-test RDP and the setup tool from monsta-mash

- [ ] **Step 1: Connect via RDP (manual)**

On monsta-mash, open your preferred RDP client (Remmina, `xfreerdp`, `rdesktop`). Target: `kubuntu-ws` (Tailscale MagicDNS) or the 100.x IP. Username `chris`, password from the Proton Pass entry created in Task 6 Step 2. You should see a KDE Plasma session.

- [ ] **Step 2: From the KDE session, open Konsole and launch the tool**

```bash
cd ~/ubuntu-setup-tool
python3 setup.py
```

Expected: the TUI main menu. Exit with `q` or Ctrl-C.

- [ ] **Step 3: Save Proton Pass entry for the VM itself**

On monsta-mash:
```bash
pass-cli item create login --vault-name Claude \
  --title "kubuntu-ws (VM 200 on snoochie) — chris" \
  --username "chris" \
  --password "<see 'kubuntu-ws — chris user password' entry>" \
  --url "ssh://chris@kubuntu-ws" \
  --url "rdp://chris@kubuntu-ws:3389"
```

(You can reference the existing password entry — this one is just the connection record.)

At this point Chris can stop here and use the VM. The next phases are the cluster + README work.

---

## Phase 3 — Install Proxmox on Boochies (Tasks 10–13)

### Task 10: Enable Hetzner rescue mode for Boochies and reboot

- [ ] **Step 1: Pull Hetzner Robot creds**

On monsta-mash:
```bash
ROBOT_USER="$(pass-cli item view --vault-name Claude --item-title 'Hetzner Robot — API/webservice' --field username)"
ROBOT_PASS="$(pass-cli item view --vault-name Claude --item-title 'Hetzner Robot — API/webservice' --field password)"
```

- [ ] **Step 2: Upload monsta-mash's SSH public key to Hetzner (for rescue login)**

Check whether the key is already registered:
```bash
curl -s -u "$ROBOT_USER:$ROBOT_PASS" https://robot-ws.your-server.de/key | python3 -m json.tool | grep -A2 brown.cy
```

If not present, register it:
```bash
SSH_PUB="$(ssh-add -L | grep brown.cy@gmail.com)"
curl -s -u "$ROBOT_USER:$ROBOT_PASS" \
  -X POST \
  --data-urlencode "name=monsta-mash-brown.cy" \
  --data-urlencode "data=$SSH_PUB" \
  https://robot-ws.your-server.de/key | python3 -m json.tool
```

Note the fingerprint from the response — you'll pass it as `authorized_key` below.

- [ ] **Step 3: Activate rescue on Boochies, authorized by that key**

```bash
SERVER_NUM=2974693
FP="<fingerprint from step 2>"
curl -s -u "$ROBOT_USER:$ROBOT_PASS" \
  -X POST \
  --data-urlencode "os=linux" \
  --data-urlencode "arch=64" \
  --data-urlencode "authorized_key[]=$FP" \
  https://robot-ws.your-server.de/boot/$SERVER_NUM/rescue | python3 -m json.tool
```

Expected: JSON with `"active": true` and `"password": null` (password-less rescue via your key).

- [ ] **Step 4: Reboot Boochies**

```bash
curl -s -u "$ROBOT_USER:$ROBOT_PASS" \
  -X POST \
  --data-urlencode "type=hw" \
  https://robot-ws.your-server.de/reset/$SERVER_NUM | python3 -m json.tool
```

Expected: `"type": "hw"`.

- [ ] **Step 5: Wait for rescue SSH**

Poll every 15s (takes 3–8 min for a hardware reset + rescue boot):
```bash
until nc -z -w 3 135.181.215.247 22; do sleep 15; done
ssh -o StrictHostKeyChecking=accept-new root@135.181.215.247 'cat /etc/motd | head -5; uname -a'
```

Expected: Hetzner rescue MOTD, kernel `Linux rescue ...`.

---

### Task 11: Install Debian 12 with `installimage`

- [ ] **Step 1: Generate an installimage config on the rescue box**

SSH into Boochies rescue, then:
```bash
cat > /tmp/install.conf <<'EOF'
DRIVE1 /dev/nvme0n1
DRIVE2 /dev/nvme1n1
SWRAID 1
SWRAIDLEVEL 1
BOOTLOADER grub
HOSTNAME boochies
PART /boot ext3 1024M
PART lvm vg0 all
LV vg0 root / ext4 30G
LV vg0 swap swap swap 8G
IMAGE /root/.oldroot/nfs/install/../images/Debian-1204-bookworm-amd64-base.tar.gz
EOF
```

(If `ls /dev/nvme*n1` shows different device names, update `DRIVE1/DRIVE2`. If there's only one disk, remove the `SWRAID`, `SWRAIDLEVEL`, and `DRIVE2` lines.)

- [ ] **Step 2: Run installimage non-interactively**

```bash
/root/.oldroot/nfs/install/installimage -a -c /tmp/install.conf
```

Expected: "100% completed" and "Installation complete." No errors.

- [ ] **Step 3: Reboot out of rescue**

```bash
reboot
```

- [ ] **Step 4: Wait for SSH on installed Debian**

From monsta-mash:
```bash
# known_hosts entry for rescue will be stale
ssh-keygen -R 135.181.215.247
until nc -z -w 3 135.181.215.247 22; do sleep 15; done
ssh -o StrictHostKeyChecking=accept-new root@135.181.215.247 'hostname && cat /etc/os-release | head -2'
```

Expected: `boochies`, `PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"`.

---

### Task 12: Install Proxmox VE 8 on Boochies

Run all of these as root on Boochies.

- [ ] **Step 1: Add hostname to `/etc/hosts` mapped to the public IP**

```bash
ssh root@135.181.215.247 '
  grep -q "135.181.215.247 boochies" /etc/hosts || echo "135.181.215.247 boochies.your-server.de boochies" >> /etc/hosts
  grep -v "127.0.1.1" /etc/hosts > /tmp/hosts.new && mv /tmp/hosts.new /etc/hosts
  hostnamectl set-hostname boochies
'
```

- [ ] **Step 2: Add Proxmox no-subscription repo and its GPG key**

```bash
ssh root@135.181.215.247 '
  wget -qO /etc/apt/trusted.gpg.d/proxmox-release-bookworm.gpg https://enterprise.proxmox.com/debian/proxmox-release-bookworm.gpg
  echo "deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription" > /etc/apt/sources.list.d/pve-no-subscription.list
  apt update
'
```

Expected: `apt update` succeeds with the new repo listed.

- [ ] **Step 3: Install PVE kernel and reboot**

```bash
ssh root@135.181.215.247 'DEBIAN_FRONTEND=noninteractive apt install -y proxmox-default-kernel'
ssh root@135.181.215.247 'reboot'
```

- [ ] **Step 4: Wait and verify PVE kernel is running**

```bash
until nc -z -w 3 135.181.215.247 22; do sleep 15; done
ssh root@135.181.215.247 'uname -r'
```

Expected: kernel ends in `-pve`.

- [ ] **Step 5: Install Proxmox packages**

```bash
ssh root@135.181.215.247 '
  DEBIAN_FRONTEND=noninteractive apt install -y proxmox-ve postfix open-iscsi chrony
  apt remove -y os-prober || true
'
```

Postfix will prompt: answer "Local only" with default settings via debconf (`DEBIAN_FRONTEND=noninteractive` + default selections picks Local only).

- [ ] **Step 6: Reboot into PVE stack**

```bash
ssh root@135.181.215.247 'reboot'
```

- [ ] **Step 7: Verify Proxmox is up**

```bash
until nc -z -w 3 135.181.215.247 8006; do sleep 15; done
curl -sk https://135.181.215.247:8006 | grep -o '<title>.*</title>'
```

Expected: `<title>Proxmox Virtual Environment</title>`.

---

### Task 13: Set and save Boochies root password; configure Boochies `vmbr0` + `vmbr1`

- [ ] **Step 1: Set a strong root password on Boochies and save it**

On monsta-mash:
```bash
NEW_PW="$(openssl rand -base64 18 | tr -d '=+/' | head -c 20)"
ssh root@135.181.215.247 "echo 'root:$NEW_PW' | chpasswd"
pass-cli item create login --vault-name Claude \
  --title "Boochies Proxmox — root (current)" \
  --username "root" \
  --password "$NEW_PW" \
  --url "https://135.181.215.247:8006" \
  --url "ssh://root@135.181.215.247"
unset NEW_PW
```

- [ ] **Step 2: Configure `vmbr0` (public) and `vmbr1` (NAT) on Boochies**

Back up and replace `/etc/network/interfaces`:

```bash
ssh root@135.181.215.247 '
  cp /etc/network/interfaces /etc/network/interfaces.bak.$(date +%s)
  # detect primary interface
  PRI=$(ip -o link show | awk -F": " '"'"'$2 !~ /^(lo|vmbr|veth|tap)/ {print $2; exit}'"'"')
  cat > /etc/network/interfaces <<EOF
auto lo
iface lo inet loopback
iface lo inet6 loopback

auto ${PRI}
iface ${PRI} inet manual

auto vmbr0
iface vmbr0 inet static
    address 135.181.215.247/26
    gateway 135.181.215.193
    bridge-ports ${PRI}
    bridge-stp off
    bridge-fd 0

iface vmbr0 inet6 static
    address 2a01:4f9:3a:2de9::2/64
    gateway fe80::1

auto vmbr1
iface vmbr1 inet static
    address 10.10.20.1/24
    bridge-ports none
    bridge-stp off
    bridge-fd 0
    post-up   iptables -t nat -A POSTROUTING -s 10.10.20.0/24 -o vmbr0 -j MASQUERADE
    post-down iptables -t nat -D POSTROUTING -s 10.10.20.0/24 -o vmbr0 -j MASQUERADE
EOF
'
```

**Before reloading:** the gateway value above (`135.181.215.193`) is a guess from the /26 netmask. Confirm by running `ip r | grep default` on Boochies first and use whatever gateway is shown there. If the gateway differs from `.193`, edit the file accordingly.

- [ ] **Step 3: Apply and verify connectivity**

```bash
ssh root@135.181.215.247 'ifreload -a && ip -br a | grep -E "vmbr0|vmbr1"'
```

Expected: both bridges UP with the addresses shown. Follow-up:
```bash
ssh root@135.181.215.247 'ping -c 3 1.1.1.1'
```

Expected: 0% packet loss.

---

## Phase 4 — Cluster join via vSwitch (Tasks 14–17)

### Task 14: Create Hetzner vSwitch and attach both servers

- [ ] **Step 1: Create vSwitch via Robot API**

```bash
curl -s -u "$ROBOT_USER:$ROBOT_PASS" \
  -X POST \
  --data-urlencode "name=helsinki-cluster" \
  --data-urlencode "vlan=4000" \
  https://robot-ws.your-server.de/vswitch | python3 -m json.tool
```

Expected: JSON with an `id`. Save it: `VSWITCH_ID=<id>`.

- [ ] **Step 2: Attach Snoochie (#2972994) and Boochies (#2974693)**

```bash
for NUM in 2972994 2974693; do
  curl -s -u "$ROBOT_USER:$ROBOT_PASS" \
    -X POST \
    --data-urlencode "server[]=$NUM" \
    https://robot-ws.your-server.de/vswitch/$VSWITCH_ID/server | python3 -m json.tool
done
```

Expected: no error body. Hetzner's backend attaches the servers to the VLAN (takes 5–15 min to propagate).

- [ ] **Step 3: Wait and confirm attachment**

```bash
until curl -s -u "$ROBOT_USER:$ROBOT_PASS" \
  https://robot-ws.your-server.de/vswitch/$VSWITCH_ID | \
  python3 -c 'import sys,json; d=json.load(sys.stdin); print([s["status"] for s in d["server"]])' | grep -v processing
do sleep 30; done
```

Expected eventually: `['ready', 'ready']`.

---

### Task 15: Configure `vmbr2` on both hosts for the cluster network

- [ ] **Step 1: On snoochie, add vmbr2**

Append to `/etc/network/interfaces` on snoochie:

```bash
ssh root@65.21.205.247 '
cat >> /etc/network/interfaces <<EOF

auto eno1.4000
iface eno1.4000 inet manual
    mtu 1400

auto vmbr2
iface vmbr2 inet static
    address 10.0.0.1/24
    bridge-ports eno1.4000
    bridge-stp off
    bridge-fd 0
    mtu 1400
EOF
ifreload -a
ip -br a show vmbr2
'
```

(Replace `eno1` with whatever snoochie's physical NIC is — confirm with `ip -o link` first.)

Expected: `vmbr2 UP 10.0.0.1/24`.

- [ ] **Step 2: On boochies, add vmbr2**

Identical block but address `10.0.0.2/24` and using Boochies's physical NIC name:

```bash
ssh root@135.181.215.247 '
PRI=$(ip -o link show | awk -F": " '"'"'$2 !~ /^(lo|vmbr|veth|tap)/ {print $2; exit}'"'"')
cat >> /etc/network/interfaces <<EOF

auto ${PRI}.4000
iface ${PRI}.4000 inet manual
    mtu 1400

auto vmbr2
iface vmbr2 inet static
    address 10.0.0.2/24
    bridge-ports ${PRI}.4000
    bridge-stp off
    bridge-fd 0
    mtu 1400
EOF
ifreload -a
ip -br a show vmbr2
'
```

Expected: `vmbr2 UP 10.0.0.2/24`.

- [ ] **Step 3: Verify L2 connectivity with MTU 1400**

From snoochie:
```bash
ssh root@65.21.205.247 'ping -c 3 -M do -s 1372 10.0.0.2'
```

Expected: 0% packet loss at that size. `-s 1372` + 28 bytes of ICMP/IP overhead = 1400.

---

### Task 16: Join Boochies to the `helsinki` cluster

- [ ] **Step 1: Exchange root SSH keys between the two hosts**

`pvecm add` internally opens an SSH session from Boochies back to Snoochie; it needs to succeed without an interactive prompt.

From monsta-mash:
```bash
BOOCHIES_ROOT_KEY="$(ssh root@135.181.215.247 'test -f /root/.ssh/id_ed25519 || ssh-keygen -t ed25519 -N "" -f /root/.ssh/id_ed25519; cat /root/.ssh/id_ed25519.pub')"
sshpass -p "$SNOOCHIE_PW" ssh root@65.21.205.247 "grep -qF '$BOOCHIES_ROOT_KEY' /root/.ssh/authorized_keys 2>/dev/null || echo '$BOOCHIES_ROOT_KEY' >> /root/.ssh/authorized_keys"
```

Verify:
```bash
ssh root@135.181.215.247 'ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@10.0.0.1 hostname'
```

Expected: `snoochie`.

- [ ] **Step 2: From Boochies, join the cluster**

```bash
ssh root@135.181.215.247 'pvecm add 10.0.0.1 --link0 10.0.0.2 --link1 135.181.215.247 --use_ssh 1'
```

Expected tail:
```
Cluster joined. Quorum reached.
```

- [ ] **Step 3: Verify from both sides**

```bash
ssh root@65.21.205.247 'pvecm status'
ssh root@135.181.215.247 'pvecm status'
```

Expected:
- `Nodes: 2`
- `Quorate: Yes`
- Two ring addresses under each node (10.0.0.x and the public IP).

---

### Task 17: Set up QDevice for quorum tiebreaking

- [ ] **Step 1: Install `corosync-qnetd` inside CT 100 on snoochie**

```bash
ssh root@65.21.205.247 'pct exec 100 -- apt update && pct exec 100 -- apt install -y corosync-qnetd'
```

- [ ] **Step 2: Find CT 100's IP on vmbr1**

```bash
ssh root@65.21.205.247 'pct exec 100 -- ip -4 addr show | grep "inet 10.10.10"'
```

Expected one line like `inet 10.10.10.X/24`. Record X.

- [ ] **Step 3: Install `corosync-qdevice` on both cluster nodes**

```bash
ssh root@65.21.205.247 'apt install -y corosync-qdevice'
ssh root@135.181.215.247 'apt install -y corosync-qdevice'
```

- [ ] **Step 4: Configure QDevice**

```bash
ssh root@65.21.205.247 "pvecm qdevice setup 10.10.10.X --force"
```

(where X is from Step 2)

- [ ] **Step 5: Verify total votes is now 3**

```bash
ssh root@65.21.205.247 'pvecm status | grep -A10 Quorum'
```

Expected:
```
Quorate:          Yes
Nodes:            2
Expected votes:   3
Total votes:      3
```

with `Qdevice` listed in the membership.

---

## Phase 5 — README update (Tasks 18–19)

### Task 18: Add `scripts/proxmox/README.md` and update the repo README

**Files:**
- Create: `scripts/proxmox/README.md`
- Modify: `README.md` (rename "## Quick Start" to "## USB install", add new "## Network install (Proxmox)" section)

- [ ] **Step 1: Create `scripts/proxmox/README.md`**

```markdown
# Proxmox autoinstall helpers

Scripts for provisioning an Ubuntu-based workstation VM on a Proxmox
node that comes up with `ubuntu-setup-tool` already cloned, Tailscale
already joined, and xrdp/openssh listening.

## Files

| File | Purpose |
|------|---------|
| `user-data.template` | cloud-init autoinstall user-data (Subiquity). Placeholders: `{{SSH_KEY}}`, `{{TAILSCALE_KEY}}`, `{{USERNAME}}`, `{{HOSTNAME}}`, `{{PASSWORD_HASH}}`. |
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
OUTPUT=/var/lib/vz/template/iso/kubuntu-ws-seed.iso \
bash /root/proxmox-scripts/make-seed.sh

# 3. Create & start VM
VMID=200 NAME=kubuntu-ws BRIDGE=vmbr1 \
IP=10.10.10.200/24 GATEWAY=10.10.10.1 \
ISO=local:iso/ubuntu-24.04-live-server.iso \
SEED=local:iso/kubuntu-ws-seed.iso \
bash /root/proxmox-scripts/create-vm.sh

# 4. Watch install via noVNC in Proxmox web UI (~25 min)
# 5. Once VM shuts down, detach ISOs and reboot from disk
qm set 200 --ide2 none,media=cdrom --ide3 none,media=cdrom
qm set 200 --boot order=scsi0
qm start 200
```

## Notes

- Ubuntu Server ISO is used (not Kubuntu) because Kubuntu's live ISO ships Calamares, which doesn't support headless autoinstall. We install `kubuntu-desktop` as a late-command — first boot takes ~25 min (10 min base install + 15 min KDE meta-package).
- The seed ISO is attached as a second CD-ROM (`ide3`). Subiquity finds it via the NoCloud datasource.
- Tailscale joins with `--ssh`, enabling Tailscale SSH from any tagged tailnet peer.
- Change `DISK_GB`, `MEMORY_MB`, `CORES`, `BRIDGE`, `IP`, `GATEWAY` via env vars when calling `create-vm.sh`.
```

- [ ] **Step 2: Read the current `README.md`**

```bash
sed -n '1,80p' README.md
```

- [ ] **Step 3: Edit `README.md`**

Change the existing `## Quick Start` heading to `## USB install`, then insert a new `## Network install (Proxmox)` section immediately after the USB section. The final README layout should be:

```markdown
# Ubuntu Setup Tool

Post-installation configurator for Ubuntu 24.04 LTS. Provides a terminal UI for installing apps, configuring accounts, and setting up a development environment on fresh Ubuntu installs.

## USB install

Use this flow when installing on bare metal from scratch.

### Phase 1: Prepare USB Boot Drive
(... existing content unchanged ...)

### Phase 2: Install Ubuntu
(... existing content unchanged ...)

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

(Why Ubuntu Server and not Kubuntu? Kubuntu's live ISO uses Calamares, which isn't scriptable. We install `kubuntu-desktop` as a late-command so you still get KDE Plasma on first login.)

### 3. Build the cloud-init seed ISO

Still on the Proxmox host:

```bash
HOSTNAME=kubuntu-ws \
USERNAME=chris \
SSH_KEY="ssh-ed25519 AAAAC3... you@host" \
TAILSCALE_KEY=tskey-auth-... \
PASSWORD_HASH="$(openssl passwd -6 'some-strong-password')" \
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

Watch the install via noVNC in the Proxmox web UI. Total install time ≈ 25 minutes (Ubuntu Server base + `kubuntu-desktop`).

### 5. After the install completes

The VM powers itself off when Subiquity finishes. Detach the ISOs and boot from disk:

```bash
qm set 200 --ide2 none,media=cdrom --ide3 none,media=cdrom
qm set 200 --boot order=scsi0
qm start 200
```

### 6. Connect and run the setup tool

Once `tailscale status` (on any peer tailnet node) shows the new VM online:

```bash
ssh <username>@<hostname>
cd ~/ubuntu-setup-tool
python3 setup.py
```

Or RDP to `<hostname>:3389` for a KDE Plasma desktop session.

See [`scripts/proxmox/README.md`](scripts/proxmox/README.md) for more detail on the helper scripts.

## Modules
(... unchanged ...)
```

The key edits to make:

1. Rename heading `## Quick Start` → `## USB install`, and add one-line intro "Use this flow when installing on bare metal from scratch."
2. Insert the entire `## Network install (Proxmox)` block shown above, between the USB section and `## Modules`.

Make these edits using `Edit`, not a full `Write` (the rest of the README is unchanged).

- [ ] **Step 4: Verify Markdown structure**

```bash
grep -E '^## ' README.md
```

Expected output (in order):
```
## USB install
## Network install (Proxmox)
## Modules
## State Tracking
## Adding Shell Scripts
## Surface Linux
## Keyboard Remapping (Planned)
## Dynamic URL Resolution
## Project Structure
```

- [ ] **Step 5: Commit**

```bash
git add README.md scripts/proxmox/README.md
git commit -m "docs: split README into USB install + Network (Proxmox) install flows

Renames the existing 'Quick Start' section to 'USB install' to make
the dual-flow intent explicit, and adds a 'Network install (Proxmox)'
section that walks through using the new scripts/proxmox/ helpers to
provision an autoinstalled Ubuntu+KDE VM that comes up ready to run
setup.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 19: Push all repo changes

- [ ] **Step 1: Push to origin/main**

```bash
git push
```

Expected: all commits from tasks 1–4 and 18 pushed to `origin/main`.

---

## Acceptance (run all after Task 19)

- [ ] `ssh chris@kubuntu-ws 'ls ~/ubuntu-setup-tool/setup.py'` prints the file path
- [ ] RDP from monsta-mash to `kubuntu-ws:3389` shows a KDE Plasma login/session
- [ ] `tailscale status | grep kubuntu-ws` shows the VM active
- [ ] `curl -sk https://135.181.215.247:8006` returns the Proxmox login page
- [ ] `ssh root@65.21.205.247 'pvecm status'` shows `Nodes: 2`, `Total votes: 3`, `Quorate: Yes`
- [ ] `grep -E '^## (USB install|Network install)' README.md` prints both headings
- [ ] `ls scripts/proxmox/` shows `user-data.template`, `meta-data.template`, `make-seed.sh`, `create-vm.sh`, `README.md`
