#!/usr/bin/env bash
# create-vm-legion.sh — create a Proxmox VM on legion for the hot-seat
# pattern. Phase 1: install with qxl VGA (no passthrough) so autoinstall
# can run visibly via noVNC. provision-legion.sh flips it to GPU
# passthrough after install completes.
#
# Usage (on legion as root):
#   VMID=210 NAME=hot-ubuntu-template \
#   ISO=local:iso/ubuntu-24.04-live-server.iso \
#   SEED=local:iso/hot-ubuntu-template-seed.iso \
#   STORAGE=legion-wdblack DISK_GB=256 MEMORY_MB=16384 CORES=8 \
#   BRIDGE=vmbr0 IP=10.0.0.210/24 GATEWAY=10.0.0.1 \
#   ./create-vm-legion.sh

set -euo pipefail

: "${VMID:?VMID required}"
: "${NAME:?NAME required}"
: "${ISO:?ISO required}"
: "${SEED:?SEED required}"
: "${STORAGE:=legion-wdblack}"
: "${DISK_GB:=256}"
: "${MEMORY_MB:=16384}"
: "${CORES:=8}"
: "${BRIDGE:=vmbr0}"
: "${IP:?IP required (e.g. 10.0.0.210/24)}"
: "${GATEWAY:?GATEWAY required}"

if qm status "$VMID" >/dev/null 2>&1; then
  echo "VM $VMID already exists — refusing to overwrite" >&2
  exit 1
fi

qm create "$VMID" \
  --name "$NAME" \
  --memory "$MEMORY_MB" \
  --balloon 4096 \
  --cores "$CORES" \
  --sockets 1 \
  --cpu host \
  --bios ovmf \
  --machine q35 \
  --efidisk0 "${STORAGE}:1,format=raw,efitype=4m,pre-enrolled-keys=1" \
  --tpmstate0 "${STORAGE}:1,version=v2.0" \
  --scsihw virtio-scsi-single \
  --scsi0 "${STORAGE}:${DISK_GB},discard=on,ssd=1,iothread=1" \
  --ide2 "${ISO},media=cdrom" \
  --ide3 "${SEED},media=cdrom" \
  --net0 "virtio,bridge=${BRIDGE},firewall=0" \
  --agent enabled=1 \
  --vga qxl \
  --serial0 socket \
  --ostype l26 \
  --boot "order=ide2;scsi0"

qm start "$VMID"
echo "Started VM $VMID ($NAME) in install mode (qxl VGA, no passthrough)."
