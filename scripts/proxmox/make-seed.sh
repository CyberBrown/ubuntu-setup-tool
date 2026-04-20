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
# Requires genisoimage (preinstalled on Proxmox).

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

genisoimage -output "$OUTPUT" \
  -volid cidata \
  -joliet -rock \
  "$WORKDIR/user-data" "$WORKDIR/meta-data" "$WORKDIR/autoinstall.yaml" \
  >/dev/null 2>&1

echo "Wrote $OUTPUT"
