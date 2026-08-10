"""screenshot -> single VLM call -> local guards -> result."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from . import capture as capture_mod
from . import client, routing
from .config import Config
from .routing import Analysis


@dataclass
class Result:
    analysis: Analysis | None = None
    image_path: Path | None = None
    raw_text: str = ""
    error: str = ""
    elapsed: float = 0.0
    cancelled: bool = False
    # True when a multi-shot session only appended a capture (no analysis yet).
    multi_appended: bool = False

    @property
    def ok(self) -> bool:
        return self.analysis is not None and not self.error

    @property
    def route(self) -> str:
        return self.analysis.route if self.analysis else "error"


def analyze_image(image_path: Path, user_mode: str, cfg: Config) -> Result:
    return analyze_images([image_path], user_mode, cfg)


def analyze_images(image_paths: list[Path], user_mode: str, cfg: Config) -> Result:
    if not image_paths:
        return Result(error="이미지가 없습니다.")

    started = time.monotonic()
    model_mode = user_mode if user_mode in ("simple", "complex") else "auto"
    raw_text = ""
    first = image_paths[0]

    for attempt in (False, True):  # one retry on unusable JSON
        try:
            raw_text = client.analyze(image_paths, model_mode, cfg, retry=attempt)
        except client.ApiError as exc:
            return Result(
                image_path=first,
                error=str(exc),
                raw_text=raw_text,
                elapsed=time.monotonic() - started,
            )

        try:
            analysis = routing.normalize(routing.extract_json(raw_text))
        except routing.ParseError:
            continue

        analysis = routing.apply_guards(
            analysis,
            user_mode=user_mode,
            low_confidence=cfg.low_confidence,
            promote_chars=cfg.promote_chars,
        )
        return Result(
            analysis=analysis,
            image_path=first,
            raw_text=raw_text,
            elapsed=time.monotonic() - started,
        )

    unreadable = Analysis(route="unreadable", reason="model_json_invalid")
    unreadable.guard_notes.append("JSON 파싱 2회 실패, unreadable 처리")
    return Result(
        analysis=unreadable,
        image_path=first,
        raw_text=raw_text,
        elapsed=time.monotonic() - started,
    )


def capture_only() -> Result:
    """Region capture without analysis (multi-shot append)."""
    try:
        image_path = capture_mod.capture_region()
    except capture_mod.CaptureCancelled as exc:
        return Result(error=str(exc), cancelled=True)
    except capture_mod.CaptureError as exc:
        return Result(error=str(exc))

    capture_mod.cleanup_old_captures()
    return Result(image_path=image_path, multi_appended=True)


def capture_and_analyze(user_mode: str, cfg: Config) -> Result:
    try:
        image_path = capture_mod.capture_region()
    except capture_mod.CaptureCancelled as exc:
        return Result(error=str(exc), cancelled=True)
    except capture_mod.CaptureError as exc:
        return Result(error=str(exc))

    capture_mod.cleanup_old_captures()
    return analyze_image(image_path, user_mode, cfg)
