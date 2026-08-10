#!/usr/bin/env bash
# Remove the GNOME custom keybindings created by install-hotkey.sh.
set -euo pipefail

SLOT="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/blankfloat/"
MULTI_SLOT="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/blankfloat-multi/"

current="$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)"
updated="$(python3 - "$current" "$SLOT" "$MULTI_SLOT" <<'PY'
import ast, sys
current, slot, multi = sys.argv[1], sys.argv[2], sys.argv[3]
drop = {slot, multi}
try:
    items = [i for i in ast.literal_eval(current) if i not in drop]
except (ValueError, SyntaxError):
    items = []
print("[" + ", ".join(f"'{i}'" for i in items) + "]")
PY
)"

gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$updated"
dconf reset -f "$SLOT" 2>/dev/null || true
dconf reset -f "$MULTI_SLOT" 2>/dev/null || true

echo "핫키 해제 완료"
