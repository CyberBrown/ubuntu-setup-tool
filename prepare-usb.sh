#!/usr/bin/env bash
#
# prepare-usb.sh — Prepare a USB drive with Ubuntu 24.04 LTS + setup tool
#
# Prerequisites:
#   - balenaEtcher installed (or use dd)
#   - USB drive (16GB+ recommended)
#   - Internet connection for downloading ISO
#
# Usage:
#   1. Run this script to download everything needed
#   2. Flash Ubuntu ISO to USB with balenaEtcher
#   3. Copy setup-tool/ to a second partition or separate USB
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOWNLOAD_DIR="$SCRIPT_DIR/downloads"
SURFACE_DIR="$SCRIPT_DIR/surface-linux/debs"

echo "══════════════════════════════════════════════════════"
echo "  Ubuntu 24.04 LTS USB Preparation"
echo "══════════════════════════════════════════════════════"

mkdir -p "$DOWNLOAD_DIR" "$SURFACE_DIR"

# ── Step 1: Download Ubuntu ISO ──────────────────────────────────────────────
ISO_URL="https://releases.ubuntu.com/24.04/ubuntu-24.04.2-desktop-amd64.iso"
ISO_FILE="$DOWNLOAD_DIR/ubuntu-24.04.2-desktop-amd64.iso"

if [ -f "$ISO_FILE" ]; then
    echo "✓ Ubuntu ISO already downloaded"
else
    echo "⏳ Downloading Ubuntu 24.04 LTS ISO..."
    wget -c "$ISO_URL" -O "$ISO_FILE"
    echo "✓ ISO downloaded"
fi

# ── Step 2: Download surface-linux packages (optional) ───────────────────────
echo ""
read -p "Download surface-linux packages for offline install? (y/N) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "⏳ Downloading surface-linux packages..."
    
    # Add surface repo temporarily to download packages
    TMP_GPG=$(mktemp)
    wget -qO - https://raw.githubusercontent.com/linux-surface/linux-surface/master/pkg/keys/surface.asc | \
        gpg --dearmor > "$TMP_GPG"
    
    # Download packages without installing
    # We use apt-get download in a temp directory
    pushd "$SURFACE_DIR" > /dev/null
    
    # Create a temporary apt configuration
    TMP_APT=$(mktemp -d)
    mkdir -p "$TMP_APT/etc/apt/sources.list.d" "$TMP_APT/var/lib/apt/lists" \
             "$TMP_APT/var/cache/apt/archives" "$TMP_APT/etc/apt/trusted.gpg.d"
    
    cp "$TMP_GPG" "$TMP_APT/etc/apt/trusted.gpg.d/linux-surface.gpg"
    echo "deb [arch=amd64] https://pkg.surfacelinux.com/debian release main" > \
        "$TMP_APT/etc/apt/sources.list.d/linux-surface.list"
    
    echo "  Fetching package lists..."
    apt-get -o Dir="$TMP_APT" -o Dir::Etc::SourceList=/dev/null \
        -o Dir::Etc::SourceParts="$TMP_APT/etc/apt/sources.list.d" \
        update 2>/dev/null || true
    
    echo "  Downloading kernel packages..."
    apt-get download \
        -o Dir::Cache="$TMP_APT/var/cache/apt" \
        -o Dir::Etc::SourceList=/dev/null \
        -o Dir::Etc::SourceParts="$TMP_APT/etc/apt/sources.list.d" \
        -o Dir::State::Lists="$TMP_APT/var/lib/apt/lists" \
        linux-image-surface linux-headers-surface libwacom-surface iptsd 2>/dev/null || {
            echo "  ⚠  Could not download all surface packages. They can be installed online later."
        }
    
    popd > /dev/null
    rm -rf "$TMP_APT" "$TMP_GPG"
    
    PKG_COUNT=$(ls "$SURFACE_DIR"/*.deb 2>/dev/null | wc -l)
    echo "✓ Downloaded $PKG_COUNT surface-linux packages"
else
    echo "⏭  Skipping surface-linux packages (can install online later)"
fi

# ── Step 3: Summary ──────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  NEXT STEPS"
echo "══════════════════════════════════════════════════════"
echo ""
echo "  1. FLASH THE ISO:"
echo "     Open balenaEtcher → Select: $ISO_FILE"
echo "     → Select your USB drive → Flash"
echo ""
echo "  2. COPY SETUP TOOL TO USB:"
echo "     After flashing, the USB will have a writable partition."
echo "     Copy the entire ubuntu-setup-tool/ folder to it:"
echo "       cp -r $SCRIPT_DIR /media/\$USER/<USB_LABEL>/"
echo ""
echo "     OR use a second USB/drive for the setup tool."
echo ""
echo "  3. INSTALL UBUNTU:"
echo "     Boot from USB → Install Ubuntu 24.04 LTS normally"
echo ""
echo "  4. RUN SETUP TOOL:"
echo "     After install, open terminal and run:"
echo "       cd /path/to/ubuntu-setup-tool"
echo "       python3 setup.py"
echo ""
echo "══════════════════════════════════════════════════════"
