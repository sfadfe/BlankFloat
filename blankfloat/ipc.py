"""Tiny unix-socket IPC so a global hotkey can poke a running instance.

Wayland compositors do not let applications grab global hotkeys, so the hotkey is
registered with GNOME (see scripts/install-hotkey.sh) and runs
``blankfloat capture`` / ``blankfloat multi``, which send commands here.
"""

from __future__ import annotations

import os
import socket
import tempfile
import threading
from pathlib import Path
from typing import Callable


def socket_path() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(base) / "blankfloat.sock"


def send(command: str, timeout: float = 1.0) -> str | None:
    """Return the reply from a running instance, or None if nothing is listening."""
    path = socket_path()
    if not path.exists():
        return None
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(path))
        client.sendall(command.encode("utf-8"))
        return client.recv(64).decode("utf-8", "replace")
    except OSError:
        return None
    finally:
        client.close()


class Server:
    """Listens on the socket and hands commands to a callback."""

    def __init__(self, handler: Callable[[str], str]):
        self.handler = handler
        self.path = socket_path()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self.path.exists():
            # Stale socket from a crashed instance.
            if send("ping") is None:
                self.path.unlink(missing_ok=True)
            else:
                raise RuntimeError("blankfloat가 이미 실행 중입니다.")

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(self.path))
        self._sock.listen(4)
        self._sock.settimeout(0.5)
        self.path.chmod(0o600)
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while self._running and self._sock:
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                try:
                    data = conn.recv(64).decode("utf-8", "replace").strip()
                    conn.sendall(self.handler(data).encode("utf-8"))
                except OSError:
                    pass

    def stop(self) -> None:
        self._running = False
        if self._sock:
            self._sock.close()
            self._sock = None
        self.path.unlink(missing_ok=True)
