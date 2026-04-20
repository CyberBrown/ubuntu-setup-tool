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
