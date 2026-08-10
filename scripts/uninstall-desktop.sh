#!/usr/bin/env bash
# Remove the blankfloat application launcher created by install-desktop.sh.
set -euo pipefail

APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$APPS_DIR/blankfloat.desktop"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
DESKTOP_DIR="${DESKTOP_DIR:-$HOME/Desktop}"
DESKTOP_COPY="$DESKTOP_DIR/blankfloat.desktop"

removed=0

if [[ -f "$DESKTOP_FILE" ]]; then
  rm -f "$DESKTOP_FILE"
  echo "앱 바로가기 해제: $DESKTOP_FILE"
  removed=1
fi

if [[ -f "$DESKTOP_COPY" ]]; then
  rm -f "$DESKTOP_COPY"
  echo "바탕화면 바로가기 해제: $DESKTOP_COPY"
  removed=1
fi

if [[ "$removed" -eq 0 ]]; then
  echo "바로가기 없음"
  exit 0
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS_DIR" 2>/dev/null || true
fi
