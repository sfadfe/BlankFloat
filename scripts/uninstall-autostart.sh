#!/usr/bin/env bash
# Remove the blankfloat autostart desktop entry.
set -euo pipefail

DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
DESKTOP="$DIR/blankfloat.desktop"

if [[ -f "$DESKTOP" ]]; then
  rm -f "$DESKTOP"
  echo "autostart 해제: $DESKTOP"
else
  echo "autostart 항목 없음: $DESKTOP"
fi
