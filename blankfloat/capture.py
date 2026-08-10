"""Region capture.

On GNOME Wayland, interactive portal / flameshot often fail after permission
prompts (``InteractiveScreenshot didn't return a file``). The reliable path is
a non-interactive full portal shot plus a Tk crop UI (``portal_region``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PORTAL_TIMEOUT = 200


class CaptureError(RuntimeError):
    pass


class CaptureCancelled(CaptureError):
    pass


def capture_dir() -> Path:
    bases = []
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        bases.append(Path(runtime))
    bases.append(Path(tempfile.gettempdir()))
    last_error: OSError | None = None
    for base in bases:
        path = base / "blankfloat"
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError as exc:
            last_error = exc
    raise OSError(f"캡처 디렉터리를 만들 수 없습니다: {last_error}")


def _new_target() -> Path:
    return capture_dir() / f"capture-{int(time.time() * 1000)}.png"


def _try_portal_region(target: Path) -> bool:
    """Full portal screenshot + Tk drag-to-crop (GNOME Wayland primary)."""
    proc = subprocess.run(
        [sys.executable, "-m", "blankfloat.portal_region", str(target)],
        capture_output=True,
        text=True,
        timeout=PORTAL_TIMEOUT,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    if proc.returncode == 0 and target.exists() and target.stat().st_size > 0:
        return True
    if proc.returncode == 2:
        raise CaptureCancelled("캡처를 취소했습니다.")
    raise CaptureError((proc.stderr or "portal region capture failed").strip())


def _try_portal(target: Path) -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "blankfloat.portal_screenshot", str(target)],
        capture_output=True,
        text=True,
        timeout=PORTAL_TIMEOUT,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    if proc.returncode == 0 and target.exists():
        return True
    if proc.returncode == 2:
        raise CaptureCancelled("캡처를 취소했습니다.")
    raise CaptureError((proc.stderr or "portal screenshot failed").strip())


def _try_flameshot(target: Path) -> bool:
    if not shutil.which("flameshot"):
        return False
    proc = subprocess.run(
        [
            "flameshot",
            "gui",
            "--path",
            str(target),
            "--accept-on-select",
        ],
        capture_output=True,
        text=True,
        timeout=PORTAL_TIMEOUT,
    )
    if proc.returncode == 0 and target.exists() and target.stat().st_size > 0:
        return True
    text = f"{proc.stderr or ''}\n{proc.stdout or ''}".strip()
    lowered = text.lower()
    if "unable to capture" in lowered:
        raise CaptureError(text or "flameshot unable to capture screen")
    if proc.returncode != 0 and not target.exists():
        raise CaptureCancelled("캡처를 취소했습니다.")
    raise CaptureError(text or "flameshot failed")


def _try_gnome_screenshot(target: Path) -> bool:
    if not shutil.which("gnome-screenshot"):
        return False
    proc = subprocess.run(
        ["gnome-screenshot", "-a", "-f", str(target)],
        capture_output=True,
        text=True,
        timeout=PORTAL_TIMEOUT,
    )
    if proc.returncode == 0 and target.exists():
        return True
    raise CaptureCancelled("캡처를 취소했습니다.")


def _try_grim_slurp(target: Path) -> bool:
    if not (shutil.which("grim") and shutil.which("slurp")):
        return False
    region = subprocess.run(["slurp"], capture_output=True, text=True, timeout=PORTAL_TIMEOUT)
    if region.returncode != 0 or not region.stdout.strip():
        raise CaptureCancelled("캡처를 취소했습니다.")
    proc = subprocess.run(
        ["grim", "-g", region.stdout.strip(), str(target)],
        capture_output=True,
        text=True,
        timeout=PORTAL_TIMEOUT,
    )
    if proc.returncode == 0 and target.exists():
        return True
    raise CaptureError((proc.stderr or "grim failed").strip())


def _try_spectacle(target: Path) -> bool:
    if not shutil.which("spectacle"):
        return False
    proc = subprocess.run(
        ["spectacle", "-r", "-b", "-n", "-o", str(target)],
        capture_output=True,
        text=True,
        timeout=PORTAL_TIMEOUT,
    )
    if proc.returncode == 0 and target.exists():
        return True
    raise CaptureCancelled("캡처를 취소했습니다.")


BACKENDS = (
    ("portal-region", _try_portal_region),
    ("flameshot", _try_flameshot),
    ("xdg-portal", _try_portal),
    ("gnome-screenshot", _try_gnome_screenshot),
    ("grim+slurp", _try_grim_slurp),
    ("spectacle", _try_spectacle),
)


def capture_region() -> Path:
    """Let the user pick a region and return the saved PNG path."""
    target = _new_target()
    errors: list[str] = []

    for name, backend in BACKENDS:
        try:
            if backend(target):
                return target
        except CaptureCancelled:
            raise
        except FileNotFoundError:
            errors.append(f"{name}: not installed")
        except subprocess.TimeoutExpired:
            errors.append(f"{name}: timed out")
        except CaptureError as exc:
            errors.append(f"{name}: {exc}")

    detail = "; ".join(errors) if errors else "no capture backend available"
    raise CaptureError(f"영역 캡처 실패 ({detail})")


def cleanup_old_captures(keep: int = 20) -> None:
    files = sorted(capture_dir().glob("capture-*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in files[keep:]:
        try:
            stale.unlink()
        except OSError:
            pass
