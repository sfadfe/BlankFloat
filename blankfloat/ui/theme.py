"""Colors and fonts for the answer card."""

from __future__ import annotations

import tkinter.font as tkfont

PALETTE = {
    "bg": "#000000",
    "card": "#000000",
    "card_alt": "#111111",
    "border": "#ffffff",
    "text": "#ffffff",
    "muted": "#777777",
    "accent": "#ffffff",
    "accent_dim": "#222222",
    "warn": "#cccccc",
    "danger": "#ffffff",
    "ok": "#ffffff",
}

ROUTE_COLORS = {
    "simple": PALETTE["text"],
    "complex": PALETTE["text"],
    "unreadable": PALETTE["muted"],
    "error": PALETTE["text"],
}

ROUTE_LABELS = {
    "simple": "간단",
    "complex": "복잡",
    "unreadable": "판독 실패",
    "error": "오류",
}


def build_fonts() -> dict[str, tkfont.Font]:
    base = tkfont.nametofont("TkDefaultFont")
    fixed = tkfont.nametofont("TkFixedFont")
    family = base.actual("family")
    mono = fixed.actual("family")
    return {
        "title": tkfont.Font(family=family, size=11, weight="bold"),
        "body": tkfont.Font(family=family, size=11),
        "body_bold": tkfont.Font(family=family, size=11, weight="bold"),
        "small": tkfont.Font(family=family, size=9),
        "answer": tkfont.Font(family=family, size=13),
        "mono": tkfont.Font(family=mono, size=11),
    }
