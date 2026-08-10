#!/usr/bin/env bash
# Install a user application launcher (.desktop) for blankfloat.
# Shows up in the GNOME app grid / dash. Pass --desktop to also put a
# copy on the Desktop folder.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="$REPO_ROOT/bin/blankfloat"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$APPS_DIR/blankfloat.desktop"
ON_DESKTOP=0

for arg in "$@"; do
  case "$arg" in
    --desktop|-d) ON_DESKTOP=1 ;;
    -h|--help)
      echo "Usage: $0 [--desktop]"
      echo "  (default) ~/.local/share/applications/blankfloat.desktop"
      echo "  --desktop  also copy to Desktop folder"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (try --help)" >&2
      exit 1
      ;;
  esac
done

chmod +x "$LAUNCHER"
mkdir -p "$APPS_DIR"

cat >"$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=blankfloat
Comment=typer + answer card daemon
Exec=$LAUNCHER
Icon=utilities-terminal
Terminal=false
Categories=Utility;
StartupNotify=false
Keywords=screenshot;capture;type;
EOF

# Mark trusted so GNOME/Nautilus will launch it without an extra prompt.
if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
fi
chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS_DIR" 2>/dev/null || true
fi

echo "앱 바로가기 등록: $DESKTOP_FILE"
echo "  Exec=$LAUNCHER"

if [[ "$ON_DESKTOP" -eq 1 ]]; then
  DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
  DESKTOP_DIR="${DESKTOP_DIR:-$HOME/Desktop}"
  mkdir -p "$DESKTOP_DIR"
  cp -f "$DESKTOP_FILE" "$DESKTOP_DIR/blankfloat.desktop"
  chmod +x "$DESKTOP_DIR/blankfloat.desktop"
  if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_DIR/blankfloat.desktop" metadata::trusted true 2>/dev/null || true
  fi
  echo "바탕화면 바로가기: $DESKTOP_DIR/blankfloat.desktop"
fi

echo "해제: scripts/uninstall-desktop.sh"
echo "지금 실행: $LAUNCHER &"
