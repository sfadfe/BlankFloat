"""Full-screen portal capture, then Tk region crop.

GNOME's interactive screenshot portal often returns response code 2
(``InteractiveScreenshot didn't return a file``). Non-interactive full
captures work after the user grants permission, so we grab the whole
screen and let the user drag a crop box.

Runs as its own process so Tk never shares a thread with the floating UI.

Exit codes: 0 captured, 2 cancelled, 1 error.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from . import portal_screenshot as portal

EXIT_OK = portal.EXIT_OK
EXIT_ERROR = portal.EXIT_ERROR
EXIT_CANCELLED = portal.EXIT_CANCELLED


def _crop_with_tk(source: Path, out_path: Path) -> int:
    import tkinter as tk

    from PIL import Image, ImageTk

    with Image.open(source) as opened:
        image = opened.convert("RGB")

    img_w, img_h = image.size
    result = {"box": None, "cancelled": False}

    root = tk.Tk()
    root.title("blankfloat 영역 선택")
    root.attributes("-topmost", True)
    try:
        root.attributes("-fullscreen", True)
    except tk.TclError:
        root.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")
    root.configure(cursor="crosshair", bg="#000000")
    root.focus_force()

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    scale = min(screen_w / img_w, screen_h / img_h)
    view_w = max(1, int(img_w * scale))
    view_h = max(1, int(img_h * scale))
    offset_x = (screen_w - view_w) // 2
    offset_y = (screen_h - view_h) // 2

    display = image.resize((view_w, view_h), Image.LANCZOS)
    photo = ImageTk.PhotoImage(display)

    canvas = tk.Canvas(root, width=screen_w, height=screen_h, highlightthickness=0, bg="#111111")
    canvas.pack(fill="both", expand=True)
    canvas.create_image(offset_x, offset_y, anchor="nw", image=photo)
    # Dim the screenshot slightly so the selection reads clearly.
    shade = canvas.create_rectangle(offset_x, offset_y, offset_x + view_w, offset_y + view_h,
                                    fill="#000000", stipple="gray50", outline="")
    rect = canvas.create_rectangle(0, 0, 0, 0, outline="#000000", width=2)

    state = {"x0": 0, "y0": 0, "dragging": False}

    def _clamp_view(x: int, y: int) -> tuple[int, int]:
        return (
            min(max(x, offset_x), offset_x + view_w),
            min(max(y, offset_y), offset_y + view_h),
        )

    def _to_image_box(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int] | None:
        left = min(x0, x1) - offset_x
        top = min(y0, y1) - offset_y
        right = max(x0, x1) - offset_x
        bottom = max(y0, y1) - offset_y
        if right - left < 4 or bottom - top < 4:
            return None
        return (
            max(0, int(left / scale)),
            max(0, int(top / scale)),
            min(img_w, int(right / scale)),
            min(img_h, int(bottom / scale)),
        )

    def on_press(event):
        x, y = _clamp_view(event.x, event.y)
        state["x0"], state["y0"] = x, y
        state["dragging"] = True
        canvas.coords(rect, x, y, x, y)
        canvas.itemconfigure(shade, state="hidden")

    def on_drag(event):
        if not state["dragging"]:
            return
        x, y = _clamp_view(event.x, event.y)
        canvas.coords(rect, state["x0"], state["y0"], x, y)

    def on_release(event):
        if not state["dragging"]:
            return
        state["dragging"] = False
        x, y = _clamp_view(event.x, event.y)
        box = _to_image_box(state["x0"], state["y0"], x, y)
        if box is None:
            canvas.itemconfigure(shade, state="normal")
            canvas.coords(rect, 0, 0, 0, 0)
            return
        result["box"] = box
        root.quit()

    def on_cancel(_event=None):
        result["cancelled"] = True
        root.quit()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_cancel)
    root.protocol("WM_DELETE_WINDOW", on_cancel)

    # Keep references alive for Tk.
    root._photo = photo  # noqa: SLF001

    root.mainloop()
    try:
        root.destroy()
    except tk.TclError:
        pass

    if result["cancelled"] or result["box"] is None:
        return EXIT_CANCELLED

    left, top, right, bottom = result["box"]
    cropped = image.crop((left, top, right, bottom))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(out_path, format="PNG")
    return EXIT_OK


def capture_region_to(out_path: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="blankfloat-full-") as tmp:
        full = Path(tmp) / "full.png"
        code = portal.take_screenshot(full, interactive=False)
        if code != EXIT_OK:
            return code
        if not full.exists() or full.stat().st_size == 0:
            print("portal full screenshot produced an empty file", file=sys.stderr)
            return EXIT_ERROR
        return _crop_with_tk(full, out_path)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python3 -m blankfloat.portal_region OUT.png", file=sys.stderr)
        return EXIT_ERROR
    try:
        return capture_region_to(Path(argv[1]))
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    import gi

    gi.require_version("Gio", "2.0")
    sys.exit(main(sys.argv))
