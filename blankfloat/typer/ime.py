#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Input-method helpers for per-script auto-typing (fcitx5 / ibus)."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass


Mode = str  # "hangul" | "latin"


def char_script(ch: str) -> str:
    """Classify one character: hangul / latin / neutral."""
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:  # syllables
        return "hangul"
    if 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:  # jamo
        return "hangul"
    if ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
        return "latin"
    return "neutral"


def script_runs(text: str) -> list[tuple[Mode, str]]:
    """Split text into (hangul|latin, chunk) runs.

    Neutral chars (digits, punctuation, whitespace) attach to the previous
    language run. Leading neutrals attach to the first language run, or to
    latin if the whole string is neutral.
    """
    if not text:
        return []

    runs: list[tuple[Mode, str]] = []
    kind: Mode | None = None
    buf: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        nonlocal kind, buf
        if kind is not None and buf:
            runs.append((kind, "".join(buf)))
        kind = None
        buf = []

    for ch in text:
        script = char_script(ch)
        if script == "neutral":
            if kind is None:
                pending.append(ch)
            else:
                buf.append(ch)
            continue
        if kind is None:
            kind = script
            buf.extend(pending)
            pending.clear()
            buf.append(ch)
        elif kind == script:
            buf.append(ch)
        else:
            flush()
            kind = script
            buf.append(ch)

    if kind is None:
        return [("latin", "".join(pending))] if pending else []
    flush()
    return runs


def _run(cmd: list[str], timeout: float = 1.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@dataclass
class ImeSnapshot:
    backend: str
    name: str | None


class ImeController:
    """Switch Hangul/Latin input methods around typing segments."""

    def __init__(
        self,
        *,
        hangul_name: str | None = None,
        latin_name: str | None = None,
        settle_secs: float = 0.08,
    ) -> None:
        self.settle_secs = settle_secs
        self._backend = self._detect_backend()
        self._hangul = hangul_name or os.environ.get(
            "BLANKFLOAT_IME_HANGUL",
            "hangul" if self._backend == "fcitx5" else "hangul",
        )
        self._latin = latin_name or os.environ.get(
            "BLANKFLOAT_IME_LATIN",
            "keyboard-us" if self._backend == "fcitx5" else "xkb:us::eng",
        )
        self._last: Mode | None = None

    @property
    def backend(self) -> str | None:
        return self._backend

    @staticmethod
    def _detect_backend() -> str | None:
        override = os.environ.get("BLANKFLOAT_IME", "").strip().lower()
        if override in {"off", "none", "0"}:
            return None
        if override in {"fcitx5", "fcitx", "ibus"}:
            return "fcitx5" if override.startswith("fcitx") else "ibus"

        im = (
            os.environ.get("GTK_IM_MODULE", "")
            + " "
            + os.environ.get("QT_IM_MODULE", "")
            + " "
            + os.environ.get("XMODIFIERS", "")
        ).lower()
        if "fcitx" in im and shutil.which("fcitx5-remote"):
            check = _run(["fcitx5-remote", "--check"])
            if check.returncode == 0:
                return "fcitx5"
        if shutil.which("fcitx5-remote"):
            check = _run(["fcitx5-remote", "--check"])
            if check.returncode == 0:
                return "fcitx5"
        if shutil.which("ibus"):
            # ibus is often installed even when unused; require a live bus reply.
            probe = _run(["ibus", "engine"])
            if probe.returncode == 0 and probe.stdout.strip():
                return "ibus"
        return None

    def current_name(self) -> str | None:
        if self._backend == "fcitx5":
            proc = _run(["fcitx5-remote", "-n"])
            name = (proc.stdout or "").strip()
            return name or None
        if self._backend == "ibus":
            proc = _run(["ibus", "engine"])
            name = (proc.stdout or "").strip()
            return name or None
        return None

    def snapshot(self) -> ImeSnapshot | None:
        if self._backend is None:
            return None
        return ImeSnapshot(backend=self._backend, name=self.current_name())

    def restore(self, snap: ImeSnapshot | None) -> None:
        if snap is None or not snap.name:
            return
        self._set_name(snap.name)
        self._last = None

    def set_mode(self, mode: Mode) -> None:
        if self._backend is None:
            return
        if mode == self._last:
            return
        name = self._hangul if mode == "hangul" else self._latin
        self._set_name(name)
        self._last = mode
        if self.settle_secs > 0:
            time.sleep(self.settle_secs)

    def _set_name(self, name: str) -> None:
        if self._backend == "fcitx5":
            _run(["fcitx5-remote", "-s", name])
            return
        if self._backend == "ibus":
            _run(["ibus", "engine", name])
