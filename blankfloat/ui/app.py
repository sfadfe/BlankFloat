"""Background daemon + black answer card: answers or prompt only.

Supports a multi-shot session: collect several region captures, then analyze
them together as sequential images in one API call.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path

from .. import ipc, pipeline
from ..config import Config
from ..pipeline import Result
from .theme import PALETTE, build_fonts

_MIN_W = 200
_MAX_W = 640
_MIN_H = 72
_MAX_H = 720
_HEADER_H = 28
_GRIP_H = 18
_PAD_X = 32
_PAD_Y = 20
_BORDER = 1


class FloatingApp:
    def __init__(
        self,
        cfg: Config,
        start_capture: bool = False,
        master: tk.Misc | None = None,
    ):
        self.cfg = cfg
        self.mode = cfg.default_mode
        self.result: Result | None = None
        self.busy = False
        self.queue: queue.Queue[Result] = queue.Queue()
        self.multi_active = False
        self.multi_paths: list[Path] = []

        # Standalone: own Tk. Combined with typer: answer card is a Toplevel.
        if master is None:
            self.root = tk.Tk()
        else:
            self.root = tk.Toplevel(master)
        self.root.title("blankfloat")
        self.root.configure(bg=PALETTE["border"])
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", cfg.opacity)
        except tk.TclError:
            pass

        self.fonts = build_fonts()
        self._place_window()
        self._build()
        self._render_idle()

        # Daemon: stay alive without a visible chrome window until a result arrives.
        self.root.withdraw()

        self.root.bind("<Escape>", lambda _e: self.hide())
        self.root.bind("<Control-q>", lambda _e: self.quit())
        self.root.after(80, self._drain_queue)

        self.server: ipc.Server | None = None
        try:
            self.server = ipc.Server(self._handle_ipc)
            self.server.start()
        except (RuntimeError, OSError):
            self.server = None

        if start_capture:
            self.root.after(250, self.start_capture)

    # window chrome ---------------------------------------------------------

    def _place_window(self) -> None:
        width, height = self.cfg.window_width, self.cfg.window_height
        screen_w = self.root.winfo_screenwidth()
        x = max(20, screen_w - width - 40)
        self.root.geometry(f"{width}x{height}+{x}+60")

    def _build(self) -> None:
        # 1px white frame around the black card.
        shell = tk.Frame(self.root, bg=PALETTE["border"])
        shell.pack(fill="both", expand=True)
        body = tk.Frame(shell, bg=PALETTE["bg"])
        body.pack(fill="both", expand=True, padx=_BORDER, pady=_BORDER)

        header = tk.Frame(body, bg=PALETTE["bg"], height=_HEADER_H)
        header.pack(fill="x")
        header.pack_propagate(False)

        self.elapsed_label = tk.Label(
            header,
            text="",
            bg=PALETTE["bg"],
            fg=PALETTE["muted"],
            font=self.fonts["small"],
        )
        self.elapsed_label.pack(side="left", padx=10)

        close = tk.Label(
            header, text="✕", bg=PALETTE["bg"], fg=PALETTE["muted"], font=self.fonts["body"]
        )
        close.pack(side="right", padx=(4, 10))
        close.bind("<Button-1>", lambda _e: self.hide())
        self._hover(close, PALETTE["text"], PALETTE["muted"])

        # Small clipboard icon left of ✕; keep a ref so Tk doesn't GC the image.
        icon_path = Path(__file__).resolve().parent / "icons" / "copy.png"
        self._copy_icon = tk.PhotoImage(file=str(icon_path))
        self.copy_btn = tk.Label(
            header,
            image=self._copy_icon,
            bg=PALETTE["bg"],
            cursor="hand2",
            padx=4,
            pady=2,
        )
        self.copy_btn.pack(side="right")
        self.copy_btn.bind("<Button-1>", lambda _e: self.copy_to_clipboard())
        self.copy_btn.bind(
            "<Enter>", lambda _e: self.copy_btn.configure(bg=PALETTE["accent_dim"]), add="+"
        )
        self.copy_btn.bind(
            "<Leave>", lambda _e: self.copy_btn.configure(bg=PALETTE["bg"]), add="+"
        )

        for widget in (header, self.elapsed_label):
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        self.text = tk.Text(
            body,
            bg=PALETTE["bg"],
            fg=PALETTE["text"],
            font=self.fonts["answer"],
            relief="flat",
            wrap="word",
            padx=14,
            pady=8,
            highlightthickness=0,
            borderwidth=0,
            insertbackground=PALETTE["text"],
            selectbackground="#333333",
            selectforeground=PALETTE["text"],
            cursor="xterm",
        )
        self.text.pack(fill="both", expand=True)

        self.text.tag_configure("answer", font=self.fonts["answer"], foreground=PALETTE["text"],
                                spacing3=10)
        self.text.tag_configure("num", font=self.fonts["body_bold"], foreground=PALETTE["text"])
        self.text.tag_configure("mono", font=self.fonts["mono"], foreground=PALETTE["text"],
                                spacing1=1)
        self.text.tag_configure("muted", foreground=PALETTE["muted"], font=self.fonts["small"])

        grip = tk.Label(
            body,
            text="◢",
            bg=PALETTE["bg"],
            fg="#333333",
            font=self.fonts["small"],
            cursor="bottom_right_corner",
        )
        grip.pack(side="right", anchor="se", padx=6, pady=4)
        grip.bind("<Button-1>", self._resize_start)
        grip.bind("<B1-Motion>", self._resize_move)

        self.mode_buttons: dict[str, tk.Label] = {}
        self.action_buttons: list[tk.Label] = []

    def _hover(self, widget: tk.Label, active: str, idle: str) -> None:
        widget.bind("<Enter>", lambda _e: widget.configure(fg=active), add="+")
        widget.bind("<Leave>", lambda _e: widget.configure(fg=idle), add="+")

    # window interactions ---------------------------------------------------

    def _drag_start(self, event: tk.Event) -> None:
        self._drag_origin = (event.x_root, event.y_root,
                             self.root.winfo_x(), self.root.winfo_y())

    def _drag_move(self, event: tk.Event) -> None:
        start_x, start_y, win_x, win_y = self._drag_origin
        self.root.geometry(
            f"+{win_x + event.x_root - start_x}+{win_y + event.y_root - start_y}"
        )

    def _resize_start(self, event: tk.Event) -> None:
        self._resize_origin = (event.x_root, event.y_root,
                               self.root.winfo_width(), self.root.winfo_height())

    def _resize_move(self, event: tk.Event) -> None:
        start_x, start_y, width, height = self._resize_origin
        new_w = max(_MIN_W, width + event.x_root - start_x)
        new_h = max(_MIN_H, height + event.y_root - start_y)
        self.root.geometry(f"{new_w}x{new_h}")

    def hide(self) -> None:
        self.root.withdraw()

    def show(self) -> None:
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.root.lift()

    def copy_to_clipboard(self) -> None:
        """Copy the visible answer/prompt text to the clipboard."""
        content = self.text.get("1.0", "end-1c")
        if not content.strip():
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            # Claim CLIPBOARD so the paste survives briefly after hide/withdraw.
            self.root.update_idletasks()
        except tk.TclError:
            return
        # Brief flash so the click registers without extra chrome.
        self.copy_btn.configure(bg=PALETTE["text"])
        self.root.after(120, lambda: self.copy_btn.configure(bg=PALETTE["bg"]))

    def quit(self) -> None:
        if self.server:
            self.server.stop()
            self.server = None
        # Tear down the whole app (typer root when embedded as Toplevel).
        main = self.root.master if isinstance(self.root, tk.Toplevel) else self.root
        closer = getattr(main, "_blankfloat_typer_close", None)
        if callable(closer):
            try:
                closer()
            except Exception:  # noqa: BLE001 — shutdown best-effort
                pass
        try:
            main.destroy()
        except tk.TclError:
            pass

    # capture flow ----------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def start_capture(self) -> None:
        """Normal hotkey: analyze one shot, or append while multi-session is on."""
        if self.busy:
            return
        self.busy = True
        self.root.withdraw()
        self.root.update_idletasks()
        mode = self.mode
        append_only = self.multi_active
        self.root.after(350, lambda: self._spawn_capture(mode, append_only=append_only))

    def toggle_multi(self) -> None:
        """Multi hotkey: arm session, or finish + note + analyze.

        Captures while armed come from the normal capture hotkey (append only).
        """
        if self.busy:
            return
        if self.multi_active:
            paths = list(self.multi_paths)
            self.multi_paths.clear()
            self.multi_active = False
            if not paths:
                self.hide()
                return
            self.busy = True
            self.root.withdraw()
            self.root.update_idletasks()
            self._prompt_multi_note(list(paths))
            return

        self.multi_active = True
        self.multi_paths = []

    def _prompt_multi_note(self, paths: list[Path]) -> None:
        """Ask for an optional note; Enter sends to API, Esc cancels."""
        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.configure(bg=PALETTE["border"])
        dlg.resizable(False, False)

        shell = tk.Frame(dlg, bg=PALETTE["border"])
        shell.pack(fill="both", expand=True)
        body = tk.Frame(shell, bg=PALETTE["bg"])
        body.pack(fill="both", expand=True, padx=_BORDER, pady=_BORDER)

        hint = tk.Label(
            body,
            text="추가 메모 (Enter 전송 / Esc 취소)",
            bg=PALETTE["bg"],
            fg=PALETTE["muted"],
            font=self.fonts["small"],
            anchor="w",
        )
        hint.pack(fill="x", padx=10, pady=(8, 4))

        entry = tk.Entry(
            body,
            bg=PALETTE["bg"],
            fg=PALETTE["text"],
            insertbackground=PALETTE["text"],
            relief="flat",
            font=self.fonts["answer"],
            highlightthickness=0,
            borderwidth=0,
        )
        entry.pack(fill="x", padx=10, pady=(0, 10))

        width, height = 420, 72
        screen_w = dlg.winfo_screenwidth()
        screen_h = dlg.winfo_screenheight()
        x = max(20, (screen_w - width) // 2)
        y = max(40, (screen_h - height) // 3)
        dlg.geometry(f"{width}x{height}+{x}+{y}")

        done = {"closed": False}

        def close_dialog() -> None:
            try:
                dlg.grab_release()
            except tk.TclError:
                pass
            try:
                dlg.destroy()
            except tk.TclError:
                pass

        def submit(_event: object | None = None) -> str | None:
            if done["closed"]:
                return "break"
            done["closed"] = True
            note = entry.get()
            close_dialog()
            self._complete_multi_note(paths, note)
            return "break"

        def cancel(_event: object | None = None) -> str | None:
            if done["closed"]:
                return "break"
            done["closed"] = True
            close_dialog()
            self._complete_multi_note(paths, None)
            return "break"

        entry.bind("<Return>", submit)
        dlg.bind("<Escape>", cancel)
        entry.bind("<Escape>", cancel)
        # Test hooks (event_generate is unreliable with grab/overrideredirect).
        dlg._blankfloat_submit = submit  # noqa: SLF001
        dlg._blankfloat_cancel = cancel  # noqa: SLF001

        try:
            dlg.grab_set()
        except tk.TclError:
            pass
        entry.focus_force()

    def _complete_multi_note(self, paths: list[Path], note: str | None) -> None:
        """Finish the multi-shot note dialog: None cancels, str sends to API."""
        if note is None:
            self.busy = False
            return
        self._spawn_analyze_paths(paths, self.mode, extra_text=note)

    def _spawn_capture(self, mode: str, *, append_only: bool) -> None:
        def work() -> None:
            if append_only:
                self.queue.put(pipeline.capture_only())
            else:
                self.queue.put(pipeline.capture_and_analyze(mode, self.cfg))

        threading.Thread(target=work, daemon=True).start()

    def _spawn_analyze_paths(
        self, paths: list[Path], mode: str, extra_text: str = ""
    ) -> None:
        note = extra_text
        thread = threading.Thread(
            target=lambda: self.queue.put(
                pipeline.analyze_images(paths, mode, self.cfg, extra_text=note)
            ),
            daemon=True,
        )
        thread.start()

    def analyze_file(self, path: Path) -> None:
        if self.busy:
            return
        self.busy = True
        mode = self.mode
        thread = threading.Thread(
            target=lambda: self.queue.put(pipeline.analyze_image(path, mode, self.cfg)),
            daemon=True,
        )
        thread.start()

    def _drain_queue(self) -> None:
        try:
            while True:
                self._finish(self.queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(80, self._drain_queue)

    def _finish(self, result: Result) -> None:
        self.busy = False
        self.result = result
        if result.cancelled:
            # Esc/cancel during region select: stay quiet; multi session kept if active.
            self.hide()
            return
        if result.multi_appended and result.image_path is not None and not result.error:
            if self.multi_active:
                self.multi_paths.append(result.image_path)
            self.hide()
            return
        self.show()
        self._render_result(result)

    def _handle_ipc(self, command: str) -> str:
        if command == "ping":
            return "pong"
        if command == "capture":
            self.root.after(0, self.start_capture)
            return "ok"
        if command == "multi":
            self.root.after(0, self.toggle_multi)
            return "ok"
        if command == "show":
            self.root.after(0, self.show)
            return "ok"
        if command == "quit":
            self.root.after(0, self.quit)
            return "ok"
        return "unknown"

    # rendering -------------------------------------------------------------

    def _write(self, content: str, tag: str = "") -> None:
        self.text.insert("end", content, tag)

    def _begin_text(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")

    def _end_text(self) -> None:
        # Keep selectable for drag-select; header also has a one-click copy button.
        self.text.configure(state="normal")

    def _set_elapsed(self, elapsed: float) -> None:
        self.elapsed_label.configure(text=f"{max(0, int(round(elapsed)))}s")

    def _fit_to_content(self) -> None:
        """Shrink/grow the card to the rendered text, within screen clamps."""
        self.root.update_idletasks()
        content = self.text.get("1.0", "end-1c")
        lines = content.splitlines() or [""]

        answer_font = self.fonts["answer"]
        mono_font = self.fonts["mono"]
        max_line_px = 0
        for line in lines:
            max_line_px = max(max_line_px, answer_font.measure(line), mono_font.measure(line))

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        max_w = min(_MAX_W, screen_w - 48)
        max_h = min(_MAX_H, screen_h - 80)
        width = max(_MIN_W, min(max_w, max_line_px + _PAD_X + 2 * _BORDER))

        x = self.root.winfo_x()
        y = self.root.winfo_y()
        if not self.root.winfo_viewable() or (x <= 1 and y <= 1):
            x = max(20, screen_w - width - 40)
            y = 60

        # Tall temporary size so wrapped display lines can be measured.
        self.root.geometry(f"{width}x{max_h}+{x}+{y}")
        self.root.update_idletasks()
        self.text.update_idletasks()

        end = self.text.index("end-1c")
        first = self.text.bbox("1.0")
        last = self.text.bbox(end)
        if first and last:
            text_h = (last[1] + last[3]) - first[1]
        else:
            count = self.text.count("1.0", end, "displaylines")
            display_lines = (count[0] if count else max(0, len(lines) - 1)) + 1
            text_h = display_lines * answer_font.metrics("linespace")

        height = max(
            _MIN_H,
            min(max_h, _HEADER_H + text_h + _GRIP_H + _PAD_Y + 2 * _BORDER),
        )
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _render_idle(self) -> None:
        self._begin_text()
        self._end_text()
        self.elapsed_label.configure(text="")

    def _render_result(self, result: Result) -> None:
        self.action_buttons = []
        self._begin_text()
        self._set_elapsed(result.elapsed)

        if result.error:
            self._write(result.error, "muted")
            self._end_text()
            self._fit_to_content()
            return

        analysis = result.analysis
        assert analysis is not None

        if analysis.route == "simple":
            self._render_simple(analysis)
        elif analysis.route == "complex":
            self._render_complex(analysis)
        else:
            self._write("다시 캡처해 주세요.", "muted")

        self._end_text()
        self._fit_to_content()

    def _render_simple(self, analysis) -> None:
        for answer in analysis.answers:
            self._write(f"{answer.id}) ", "num")
            self._write(f"{answer.text}\n", "answer")

    def _render_complex(self, analysis) -> None:
        self._write(analysis.prompt or "", "mono")

    def run(self) -> None:
        self.root.mainloop()


def run(cfg: Config, start_capture: bool = False, image: Path | None = None) -> None:
    """Run typer GUI (always visible) + blankfloat answer-card daemon."""
    from ..typer import TyperApp

    typer = TyperApp()
    # FloatingApp.quit destroys the shared Tk root; close uinput first.
    typer.root._blankfloat_typer_close = typer.close  # noqa: SLF001
    app = FloatingApp(
        cfg,
        start_capture=start_capture and image is None,
        master=typer.root,
    )
    typer.root.protocol("WM_DELETE_WINDOW", app.quit)
    if image is not None:
        app.root.after(200, lambda: app.analyze_file(image))
    try:
        typer.run()
    finally:
        typer.close()
