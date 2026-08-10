#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검은 배경 Tk UI — 흰 테두리 / 입력창 / 확인만."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

BG = "#000000"
FG = "#ffffff"
BORDER = "#ffffff"
BTN_BG = "#000000"
BTN_ACTIVE = "#222222"
COUNTDOWN_SECS = 3


class TyperApp:
    """Always-visible auto-type panel. Builds into ``root`` (Tk or Frame)."""

    def __init__(self, root: tk.Misc | None = None) -> None:
        self._owns_root = root is None
        self.root = root if root is not None else tk.Tk()
        if self._owns_root:
            self.root.title("blankfloat typer")
            self.root.configure(bg=BORDER)
            self.root.geometry("640x420")
            self.root.minsize(320, 200)
            self.root.attributes("-fullscreen", False)

        self._busy = False
        self._keyboard = None
        self._kbd_lock = threading.Lock()
        self._build()
        if self._owns_root:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # Warm uinput in the background so the first Confirm skips most settle.
        self.root.after(150, self._warm_uinput)

    def _warm_uinput(self) -> None:
        def work() -> None:
            try:
                self._ensure_keyboard()
            except Exception:  # noqa: BLE001 — probe only; Confirm shows errors
                pass

        threading.Thread(target=work, daemon=True).start()

    def _ensure_keyboard(self):
        with self._kbd_lock:
            if self._keyboard is None:
                from .uinput_typer import UInputKeyboard

                self._keyboard = UInputKeyboard(settle_secs=1.0)
            kbd = self._keyboard
        return kbd.ensure()

    def close(self) -> None:
        with self._kbd_lock:
            kbd = self._keyboard
            self._keyboard = None
        if kbd is not None:
            kbd.close()

    def _on_close(self) -> None:
        self.close()
        self.root.destroy()

    def _build(self) -> None:
        # 흰 테두리 = 바깥 여백(root bg=white) + 안쪽 검정 패널
        host = self.root
        if self._owns_root:
            host.configure(bg=BORDER)
        panel = tk.Frame(host, bg=BG, highlightthickness=0)
        panel.pack(fill="both", expand=True, padx=2, pady=2)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        self.text = tk.Text(
            panel,
            bg=BG,
            fg=FG,
            insertbackground=FG,
            selectbackground="#333333",
            selectforeground=FG,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Monospace", 11),
            wrap="word",
            undo=True,
            padx=10,
            pady=10,
        )
        self.text.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))

        self.btn = tk.Button(
            panel,
            text="확인",
            command=self._on_confirm,
            bg=BTN_BG,
            fg=FG,
            activebackground=BTN_ACTIVE,
            activeforeground=FG,
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
            padx=20,
            pady=8,
            cursor="hand2",
        )
        self.btn.grid(row=1, column=0, sticky="e", padx=8, pady=(4, 8))

        self.text.focus_set()
        host.bind("<Control-Return>", lambda _e: self._on_confirm())

    def _on_confirm(self) -> None:
        if self._busy:
            return
        text = self.text.get("1.0", "end-1c")
        if not text.strip():
            return

        self._busy = True
        self.btn.configure(state="disabled")
        # Hide while countdown/typing so the panel does not steal focus.
        self.root.withdraw()

        def work() -> None:
            err: Exception | None = None
            try:
                from .uinput_typer import type_payload

                ui = self._ensure_keyboard()
                type_payload(text, countdown_secs=COUNTDOWN_SECS, ui=ui)
            except Exception as exc:  # noqa: BLE001 — UI 에 표시
                err = exc
            self.root.after(0, lambda: self._done(err))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, err: Exception | None) -> None:
        self._busy = False
        self.btn.configure(state="normal")
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass
        if err is None:
            return
        if isinstance(err, PermissionError):
            msg = "/dev/uinput 권한 없음 — input 그룹 또는 sudo 로 실행하세요"
        elif isinstance(err, ImportError):
            msg = "evdev 미설치 — pip install evdev 또는 apt install python3-evdev"
        else:
            msg = f"{type(err).__name__}: {err}"
        messagebox.showerror("오류", msg)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    TyperApp().run()


if __name__ == "__main__":
    main()
