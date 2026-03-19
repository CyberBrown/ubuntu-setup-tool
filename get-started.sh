#!/usr/bin/env bash
#
# get-started.sh — Bootstrap script for fresh Ubuntu install
#
# Run this after installing Ubuntu to kick off the setup tool.
# Can be run from the USB or downloaded from a repo.
#
# Usage:
#   bash get-started.sh
#   OR
#   curl -fsSL https://raw.githubusercontent.com/CyberBrown/ubuntu-setup-tool/main/get-started.sh | bash
#
set -euo pipefail

echo "══════════════════════════════════════════════════════"
echo "  Ubuntu Setup Tool - Bootstrap"
echo "══════════════════════════════════════════════════════"

# Ensure we have the basics
sudo apt update -qq
sudo apt install -y -qq python3 python3-pip git wget curl

# If we're running from the repo/USB, just launch
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/setup.py" ]; then
    echo "Found setup tool in $SCRIPT_DIR"
    cd "$SCRIPT_DIR"
    python3 setup.py
    exit 0
fi

# Otherwise, clone and run
SETUP_DIR="$HOME/ubuntu-setup-tool"
if [ -d "$SETUP_DIR" ]; then
    echo "Setup tool already cloned at $SETUP_DIR"
    cd "$SETUP_DIR"
    git pull --quiet
else
    echo "Cloning setup tool..."
    git clone https://github.com/CyberBrown/ubuntu-setup-tool.git "$SETUP_DIR"
    cd "$SETUP_DIR"
fi

python3 setup.py
