#!/usr/bin/env bash
# provision-legion.sh — unattended end-to-end provisioner for the
# hot-seat Ubuntu VM template on legion. Runs overnight in tmux.
#
# Phases:
#   1. Download Ubuntu Server ISO if missing
#   2. Shut down the currently-running GPU-holder (win11 VM 203)
#   3. Build the seed ISO from user-data-legion.template
#   4. Create VM $VMID with qxl VGA + install ISOs
#   5. Sleep long enough for Subiquity to render, sendkey "yes"
#   6. Poll until VM powers itself off (autoinstall done)
#   7. Detach ISOs, enable GPU passthrough + hookscript, set boot order
#   8. Start VM, wait for first-boot.sh to complete (marker file via SSH)
#   9. Shut down VM cleanly
#  10. Convert VM to Proxmox template
#
# Run as root on legion. Logs to /var/log/legion-provision.log.

set -euo pipefail
exec > >(tee -a /var/log/legion-provision.log) 2>&1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VMID="${VMID:-210}"
NAME="${NAME:-hot-ubuntu-template}"
USERNAME="${USERNAME:-chris}"
IP_CIDR="${IP_CIDR:-10.0.0.210/24}"
IP="${IP_CIDR%%/*}"
GATEWAY="${GATEWAY:-10.0.0.1}"
STORAGE="${STORAGE:-legion-wdblack}"
MEMORY_MB="${MEMORY_MB:-16384}"
CORES="${CORES:-8}"
DISK_GB="${DISK_GB:-256}"

ISO_DIR="${ISO_DIR:-/var/lib/vz/template/iso}"
ISO_FILE="${ISO_FILE:-ubuntu-24.04-live-server.iso}"
ISO_URL="${ISO_URL:-https://releases.ubuntu.com/24.04/ubuntu-24.04.3-live-server-amd64.iso}"
SEED_FILE="${SEED_FILE:-${NAME}-seed.iso}"

GPU_PCI="${GPU_PCI:-0000:01:00}"
SHUTDOWN_VMID="${SHUTDOWN_VMID:-203}"   # win11, which currently holds the GPU
HOOKSCRIPT="${HOOKSCRIPT:-local:snippets/gpu-passthrough.sh}"

SSH_KEY="${SSH_KEY:?SSH_KEY required (full line: ssh-ed25519 AAAAC... user@host)}"
PASSWORD_HASH="${PASSWORD_HASH:?PASSWORD_HASH required}"
SUNSHINE_PASSWORD="${SUNSHINE_PASSWORD:?SUNSHINE_PASSWORD required}"

log()  { printf '[%(%F %T)T] %s\n' -1 "$*"; }
fail() { log "FAIL: $*"; exit 1; }

vm_stopped() { qm status "$1" 2>/dev/null | grep -q 'status: stopped'; }

###############################################################################
log "=== Phase 1: ensure Ubuntu Server ISO is present ==="
if [ ! -f "$ISO_DIR/$ISO_FILE" ]; then
  log "Downloading $ISO_URL -> $ISO_DIR/$ISO_FILE"
  wget --progress=dot:giga -O "$ISO_DIR/$ISO_FILE" "$ISO_URL"
else
  log "ISO already present at $ISO_DIR/$ISO_FILE"
fi

###############################################################################
log "=== Phase 2: shut down current GPU holder (VM $SHUTDOWN_VMID) ==="
if qm status "$SHUTDOWN_VMID" 2>/dev/null | grep -q 'status: running'; then
  log "VM $SHUTDOWN_VMID is running — issuing ACPI shutdown"
  qm shutdown "$SHUTDOWN_VMID" --timeout 120 || qm stop "$SHUTDOWN_VMID"
  for _ in $(seq 1 60); do
    vm_stopped "$SHUTDOWN_VMID" && break
    sleep 2
  done
  vm_stopped "$SHUTDOWN_VMID" || fail "VM $SHUTDOWN_VMID would not stop"
  log "VM $SHUTDOWN_VMID stopped"
else
  log "VM $SHUTDOWN_VMID is not running"
fi

###############################################################################
log "=== Phase 3: build seed ISO ==="
SEED_PATH="$ISO_DIR/$SEED_FILE"
if [ -f "$SEED_PATH" ]; then
  log "Removing existing seed $SEED_PATH"
  rm -f "$SEED_PATH"
fi

HOSTNAME="$NAME" \
USERNAME="$USERNAME" \
SSH_KEY="$SSH_KEY" \
PASSWORD_HASH="$PASSWORD_HASH" \
SUNSHINE_PASSWORD="$SUNSHINE_PASSWORD" \
IP_CIDR="$IP_CIDR" \
GATEWAY="$GATEWAY" \
TEMPLATE="$SCRIPT_DIR/user-data-legion.template" \
OUTPUT="$SEED_PATH" \
bash "$SCRIPT_DIR/make-seed.sh"
log "Seed built: $SEED_PATH"

###############################################################################
log "=== Phase 4: create VM $VMID ==="
if qm status "$VMID" >/dev/null 2>&1; then
  log "VM $VMID already exists — destroying first"
  qm stop "$VMID" 2>/dev/null || true
  sleep 2
  qm destroy "$VMID" --purge 1 --destroy-unreferenced-disks 1
fi

VMID="$VMID" NAME="$NAME" \
  ISO="local:iso/$ISO_FILE" \
  SEED="local:iso/$SEED_FILE" \
  STORAGE="$STORAGE" DISK_GB="$DISK_GB" MEMORY_MB="$MEMORY_MB" CORES="$CORES" \
  BRIDGE=vmbr0 IP="$IP_CIDR" GATEWAY="$GATEWAY" \
  bash "$SCRIPT_DIR/create-vm-legion.sh"

###############################################################################
log "=== Phase 5: dismiss Subiquity 'yes' prompt ==="
# Subiquity needs ~60s to boot to the prompt. Retry up to 6 times in case the
# first send lands too early.
sleep 90
for attempt in 1 2 3 4 5 6; do
  log "Sending 'yes<Enter>' (attempt $attempt)"
  qm sendkey "$VMID" y
  qm sendkey "$VMID" e
  qm sendkey "$VMID" s
  qm sendkey "$VMID" ret
  sleep 20
  # Once install started the VM writes to disk heavily; detect via cpu/disk
  # stats isn't reliable from bash so we just keep firing until it stops
  # accepting input (VM has moved past prompt).
done

###############################################################################
log "=== Phase 6: wait for autoinstall to complete (VM powers off) ==="
for i in $(seq 1 60); do   # up to 60 * 30s = 30 min
  if vm_stopped "$VMID"; then
    log "VM $VMID powered off after install"
    break
  fi
  log "Autoinstall in progress... (${i}/60)"
  sleep 30
done
vm_stopped "$VMID" || fail "VM $VMID did not power off after install"

###############################################################################
log "=== Phase 7: reconfigure for GPU passthrough + direct boot ==="
qm set "$VMID" --ide2 none,media=cdrom --ide3 none,media=cdrom
qm set "$VMID" --boot order=scsi0
qm set "$VMID" --vga none
qm set "$VMID" --hostpci0 "${GPU_PCI},pcie=1,x-vga=1"
qm set "$VMID" --hookscript "$HOOKSCRIPT"
log "Passthrough enabled for VM $VMID"

###############################################################################
log "=== Phase 8: boot installed system, wait for first-boot.sh to finish ==="
qm start "$VMID"

log "Waiting for SSH on $IP:22..."
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 -o BatchMode=yes"
for i in $(seq 1 60); do
  if ssh $SSH_OPTS "$USERNAME@$IP" true 2>/dev/null; then
    log "SSH reachable"
    break
  fi
  log "Waiting for SSH... (${i}/60)"
  sleep 10
done
ssh $SSH_OPTS "$USERNAME@$IP" true 2>/dev/null || \
  log "WARNING: SSH never became reachable — check VM console"

log "Tailing /var/log/first-boot.log until the completion marker appears..."
for i in $(seq 1 90); do   # up to 90 * 30s = 45 min
  if ssh $SSH_OPTS "$USERNAME@$IP" "sudo test -f /var/lib/first-boot-complete" 2>/dev/null; then
    log "first-boot.sh completion marker detected"
    break
  fi
  ssh $SSH_OPTS "$USERNAME@$IP" "sudo tail -n 2 /var/log/first-boot.log 2>/dev/null" || true
  log "first-boot still running... (${i}/90)"
  sleep 30
done

###############################################################################
log "=== Phase 9: shut VM down cleanly ==="
for i in 1 2 3; do
  if vm_stopped "$VMID"; then break; fi
  qm shutdown "$VMID" --timeout 60 || true
  sleep 10
done
if ! vm_stopped "$VMID"; then
  qm stop "$VMID" || true
  sleep 5
fi

###############################################################################
log "=== Phase 10: convert to Proxmox template ==="
qm template "$VMID" || log "WARNING: qm template failed (VM may already be a template)"

log "=== DONE ==="
log "Template VM $VMID ($NAME) ready. To clone:"
log "  qm clone $VMID 211 --name hot-client-a --full"
log "  qm set 211 --hookscript $HOOKSCRIPT --hostpci0 ${GPU_PCI},pcie=1,x-vga=1"
log "  qm start 211"
