"""Interactive screenshot through the XDG desktop portal.

Runs as its own process (``python3 -m blankfloat.portal_screenshot OUT.png``) so the
GLib main loop it needs never has to coexist with the Tk main loop.

Exit codes: 0 captured, 2 cancelled by the user, 1 error.
"""

from __future__ import annotations

import os
import shutil
import sys
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT_IFACE = "org.freedesktop.portal.Screenshot"
REQUEST_IFACE = "org.freedesktop.portal.Request"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CANCELLED = 2

TIMEOUT_SECONDS = 180


def _uri_to_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme and parsed.scheme != "file":
        raise RuntimeError(f"unsupported screenshot uri: {uri}")
    return Path(unquote(parsed.path or uri))


def _parent_window() -> str:
    """GNOME 46+ rejects an empty parent_window for Screenshot.

    A non-empty no-parent handle (``wayland:`` / ``x11:``) is accepted by the
    portal and avoids ``Failed to associate portal window with parent window ''``.
    """
    session = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
    if session == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
        return "wayland:"
    display = os.environ.get("DISPLAY")
    if display:
        return f"x11:{display}"
    return "wayland:"


def take_screenshot(out_path: Path, interactive: bool = True) -> int:
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    token = "blankfloat_" + uuid.uuid4().hex[:12]
    sender = bus.get_unique_name().lstrip(":").replace(".", "_")
    request_path = f"{PORTAL_PATH}/request/{sender}/{token}"

    loop = GLib.MainLoop()
    state: dict[str, object] = {"code": None, "uri": None}

    def on_response(_conn, _sender, _path, _iface, _signal, params):
        code, results = params.unpack()
        state["code"] = code
        state["uri"] = results.get("uri")
        loop.quit()

    subscription = bus.signal_subscribe(
        PORTAL_BUS,
        REQUEST_IFACE,
        "Response",
        request_path,
        None,
        Gio.DBusSignalFlags.NONE,
        on_response,
    )

    # modal=False: blankfloat already hides itself; a modal grab can make the
    # GNOME capture UI feel like an instant cancel on some Wayland sessions.
    options = {
        "handle_token": GLib.Variant("s", token),
        "interactive": GLib.Variant("b", interactive),
        "modal": GLib.Variant("b", False),
    }
    parent = _parent_window()

    try:
        bus.call_sync(
            PORTAL_BUS,
            PORTAL_PATH,
            SCREENSHOT_IFACE,
            "Screenshot",
            GLib.Variant("(sa{sv})", (parent, options)),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

        def on_timeout():
            state["code"] = "timeout"
            loop.quit()
            return False

        timer = GLib.timeout_source_new_seconds(TIMEOUT_SECONDS)
        timer.set_callback(lambda *_: on_timeout())
        timer.attach(loop.get_context())

        loop.run()
        timer.destroy()
    finally:
        bus.signal_unsubscribe(subscription)

    code = state["code"]
    if code == "timeout":
        print("portal screenshot timed out", file=sys.stderr)
        return EXIT_ERROR
    # XDG portal Response: 0 success, 1 user cancelled, 2 ended otherwise.
    if code == 1:
        return EXIT_CANCELLED
    if code != 0:
        print(f"portal screenshot ended with response code {code}", file=sys.stderr)
        return EXIT_ERROR

    uri = state["uri"]
    if not uri:
        print("portal returned no uri", file=sys.stderr)
        return EXIT_ERROR

    source = _uri_to_path(str(uri))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, out_path)
    _discard_temp_copy(source)
    return EXIT_OK


def _discard_temp_copy(source: Path) -> None:
    """Drop the portal's scratch file, never anything the user might keep."""
    temp_roots = ("/tmp", "/var/tmp", "/run")
    if not str(source).startswith(temp_roots):
        return
    try:
        source.unlink()
    except OSError:
        pass


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python3 -m blankfloat.portal_screenshot OUT.png", file=sys.stderr)
        return EXIT_ERROR
    interactive = "--full" not in argv[2:]
    try:
        return take_screenshot(Path(argv[1]), interactive=interactive)
    except Exception as exc:  # surfaced to the parent process as stderr text
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    import gi

    gi.require_version("Gio", "2.0")
    sys.exit(main(sys.argv))
