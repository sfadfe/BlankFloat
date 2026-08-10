#!/usr/bin/env bash
# Install a user autostart entry so the blankfloat daemon is warm at login.
# Hotkeys (install-hotkey.sh) poke this daemon over a Unix socket; without it
# every shortcut cold-starts the full Tk app.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="$REPO_ROOT/bin/blankfloat"
DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
DESKTOP="$DIR/blankfloat.desktop"

chmod +x "$LAUNCHER"
mkdir -p "$DIR"

cat >"$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=blankfloat
Comment=blankfloat typer + capture daemon
Exec=$LAUNCHER
Icon=utilities-terminal
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
StartupNotify=false
EOF

echo "autostart 등록: $DESKTOP"
echo "  Exec=$LAUNCHER"
echo "해제: scripts/uninstall-autostart.sh"
echo "지금 세션에서 바로 쓰려면: $LAUNCHER &"
