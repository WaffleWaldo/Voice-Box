#!/usr/bin/env bash
# Install EchoFlow system dependencies on Arch Linux / CachyOS.
set -euo pipefail

PACMAN_PKGS=(
    python
    gtk4
    gtk4-layer-shell
    python-gobject
    python-numpy
    python-httpx
    wl-clipboard
    wtype
    pipewire
)

AUR_PKG="python-faster-whisper"

echo "==> Installing pacman packages..."
sudo pacman -S --needed "${PACMAN_PKGS[@]}"

# Detect AUR helper
if command -v paru &>/dev/null; then
    AUR_HELPER=paru
elif command -v yay &>/dev/null; then
    AUR_HELPER=yay
else
    echo ""
    echo "No AUR helper found (paru or yay)."
    echo "Install $AUR_PKG manually from the AUR, then re-run make install."
    exit 1
fi

echo ""
echo "==> Installing AUR package ($AUR_PKG) via $AUR_HELPER..."
"$AUR_HELPER" -S --needed "$AUR_PKG"

echo ""
echo "All dependencies installed. Run 'make install' next."
