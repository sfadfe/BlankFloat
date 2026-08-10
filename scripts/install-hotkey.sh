#!/usr/bin/env bash
# Register GNOME custom keybindings for blankfloat capture + multi-shot.
# Wayland does not let applications grab global hotkeys, so the shell owns them.
set -euo pipefail

BINDING="${1:-<Control><Shift><Alt>a}"
MULTI_BINDING="${2:-<Control><Shift><Alt>m}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="$REPO_ROOT/bin/blankfloat"
SLOT="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/blankfloat/"
MULTI_SLOT="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/blankfloat-multi/"
SCHEMA="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$SLOT"
MULTI_SCHEMA="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$MULTI_SLOT"

if ! command -v gsettings >/dev/null 2>&1; then
  echo "gsettings가 없습니다. GNOME 세션에서 실행하세요." >&2
  exit 1
fi

chmod +x "$LAUNCHER"

current="$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)"
updated="$(python3 - "$current" "$SLOT" "$MULTI_SLOT" <<'PY'
import ast, sys
current, slot, multi = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    items = list(ast.literal_eval(current))
except (ValueError, SyntaxError):
    items = []
for s in (slot, multi):
    if s not in items:
        items.append(s)
print("[" + ", ".join(f"'{i}'" for i in items) + "]")
PY
)"

gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$updated"

gsettings set "$SCHEMA" name 'blankfloat capture'
gsettings set "$SCHEMA" command "$LAUNCHER capture"
gsettings set "$SCHEMA" binding "$BINDING"

gsettings set "$MULTI_SCHEMA" name 'blankfloat multi'
gsettings set "$MULTI_SCHEMA" command "$LAUNCHER multi"
gsettings set "$MULTI_SCHEMA" binding "$MULTI_BINDING"

echo "핫키 등록 완료:"
echo "  $BINDING -> $LAUNCHER capture"
echo "  $MULTI_BINDING -> $LAUNCHER multi"
echo "해제하려면: scripts/uninstall-hotkey.sh"
