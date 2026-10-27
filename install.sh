#!/usr/bin/env bash
# Installs Modern Islands into ~/.config/waybar.
# Your current waybar folder is moved to ~/.config/waybar.bak-<date> first.

set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${XDG_CONFIG_HOME:-$HOME/.config}/waybar"

if [ -e "$DEST" ]; then
    BACKUP="$DEST.bak-$(date +%Y%m%d-%H%M%S)"
    mv "$DEST" "$BACKUP"
    echo "Old config moved to $BACKUP"
fi

mkdir -p "$DEST/scripts"
cp "$SRC/config.jsonc" "$SRC/style.css" "$DEST/"
cp "$SRC"/scripts/*.py "$DEST/scripts/"
chmod +x "$DEST"/scripts/*.py

if pgrep -x waybar >/dev/null; then
    pkill -x waybar
    sleep 0.5
fi
(waybar >/dev/null 2>&1 &)
echo "Modern Islands installed."
