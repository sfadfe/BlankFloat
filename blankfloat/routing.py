"""Model output parsing and the local guards from docs/ROUTING.md.

The guards are output repair, not the main router: they only run after the model
has already produced a route.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

ROUTES = ("simple", "complex", "unreadable")
LANGUAGES = ("ko", "en", "mixed", "other")

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class ParseError(ValueError):
    """Raised when the model reply cannot be turned into a valid Analysis."""


@dataclass
class Signals:
    has_blanks: bool = False
    has_choices: bool = False
    has_short_answer: bool = False
    has_math: bool = False
    has_writing: bool = False
    max_expected_chars: int | None = None


@dataclass
class Answer:
    id: str
    text: str
    uncertain: bool = False


@dataclass
class Analysis:
    route: str = "unreadable"
    confidence: float = 0.0
    reason: str = ""
    language: str = "other"
    question_count: int = 0
    signals: Signals = field(default_factory=Signals)
    answers: list[Answer] = field(default_factory=list)
    prompt: str | None = None
    outline: list[str] | None = None
    guard_notes: list[str] = field(default_factory=list)


def extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a model reply that may be wrapped in prose."""
    if not text or not text.strip():
        raise ParseError("empty model reply")

    candidates: list[str] = []
    fenced = _FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text.strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ParseError("no JSON object in model reply")


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        digits = re.search(r"-?\d+", value)
        if digits:
            return int(digits.group())
    return None


def _parse_signals(raw: Any) -> Signals:
    data = raw if isinstance(raw, dict) else {}
    return Signals(
        has_blanks=_as_bool(data.get("has_blanks")),
        has_choices=_as_bool(data.get("has_choices")),
        has_short_answer=_as_bool(data.get("has_short_answer")),
        has_math=_as_bool(data.get("has_math")),
        has_writing=_as_bool(data.get("has_writing")),
        max_expected_chars=_as_int(data.get("max_expected_chars")),
    )


def _parse_answers(raw: Any) -> list[Answer]:
    if not isinstance(raw, list):
        return []
    answers: list[Answer] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            answers.append(
                Answer(
                    id=str(item.get("id") or index),
                    text=text,
                    uncertain=_as_bool(item.get("uncertain")),
                )
            )
        elif isinstance(item, str) and item.strip():
            answers.append(Answer(id=str(index), text=item.strip()))
    return answers


def _parse_outline(raw: Any) -> list[str] | None:
    if isinstance(raw, list):
        bullets = [str(x).strip() for x in raw if str(x).strip()]
        return bullets or None
    if isinstance(raw, str) and raw.strip():
        bullets = [line.strip(" -•\t") for line in raw.splitlines() if line.strip()]
        return bullets or None
    return None


def normalize(raw: dict[str, Any]) -> Analysis:
    """Turn a parsed JSON object into an Analysis, rejecting unusable output."""
    route = str(raw.get("route", "")).strip().lower()
    if route not in ROUTES:
        raise ParseError(f"invalid route: {raw.get('route')!r}")

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(max(confidence, 0.0), 1.0)

    language = str(raw.get("language", "other")).strip().lower()
    if language not in LANGUAGES:
        language = "other"

    prompt = raw.get("prompt")
    prompt = prompt.strip() if isinstance(prompt, str) and prompt.strip() else None

    return Analysis(
        route=route,
        confidence=confidence,
        reason=str(raw.get("reason", "") or "").strip(),
        language=language,
        question_count=_as_int(raw.get("question_count")) or 0,
        signals=_parse_signals(raw.get("signals")),
        answers=_parse_answers(raw.get("answers")),
        prompt=prompt,
        outline=_parse_outline(raw.get("outline")),
    )


def apply_guards(
    analysis: Analysis,
    user_mode: str = "auto",
    low_confidence: float = 0.45,
    promote_chars: int = 200,
) -> Analysis:
    """Post-process a model route. Mirrors the guard chain in docs/ROUTING.md."""
    route = analysis.route
    signals = analysis.signals
    has_answers = bool(analysis.answers)
    max_chars = signals.max_expected_chars

    if user_mode in ("simple", "complex"):
        if route != user_mode:
            analysis.guard_notes.append(f"user_mode={user_mode} overrides {route}")
        analysis.route = user_mode

    elif route == "complex" and analysis.confidence < low_confidence:
        # Ambiguous writing call: prefer answers, but only if we actually have any.
        if has_answers:
            analysis.route = "simple"
            analysis.guard_notes.append(
                f"low confidence {analysis.confidence:.2f} < {low_confidence}, fell back to simple"
            )
        else:
            analysis.guard_notes.append(
                f"low confidence {analysis.confidence:.2f} but no answers, kept complex"
            )

    elif route == "simple" and signals.has_writing and max_chars is not None and max_chars >= promote_chars:
        analysis.route = "complex"
        analysis.guard_notes.append(
            f"writing signal with max_expected_chars={max_chars}, promoted to complex"
        )

    elif route == "simple" and not has_answers:
        analysis.route = "complex" if signals.has_writing else "unreadable"
        analysis.guard_notes.append(
            f"simple with empty answers, switched to {analysis.route}"
        )

    return _enforce_route_fields(analysis)


def _enforce_route_fields(analysis: Analysis) -> Analysis:
    """Keep the payload consistent with the final route."""
    if analysis.route == "simple":
        analysis.prompt = None
        analysis.outline = None
    elif analysis.route == "complex":
        analysis.answers = []
        if not analysis.prompt:
            analysis.route = "unreadable"
            analysis.guard_notes.append("complex without prompt, downgraded to unreadable")
    if analysis.route == "unreadable":
        analysis.answers = []
        analysis.prompt = None
        analysis.outline = None
    return analysis


def answers_as_text(analysis: Analysis) -> str:
    lines = []
    for answer in analysis.answers:
        mark = " (?)" if answer.uncertain else ""
        lines.append(f"{answer.id}) {answer.text}{mark}")
    return "\n".join(lines)


def to_dict(analysis: Analysis) -> dict[str, Any]:
    return {
        "route": analysis.route,
        "confidence": analysis.confidence,
        "reason": analysis.reason,
        "language": analysis.language,
        "question_count": analysis.question_count,
        "signals": {
            "has_blanks": analysis.signals.has_blanks,
            "has_choices": analysis.signals.has_choices,
            "has_short_answer": analysis.signals.has_short_answer,
            "has_math": analysis.signals.has_math,
            "has_writing": analysis.signals.has_writing,
            "max_expected_chars": analysis.signals.max_expected_chars,
        },
        "answers": [
            {"id": a.id, "text": a.text, "uncertain": a.uncertain} for a in analysis.answers
        ],
        "prompt": analysis.prompt,
        "outline": analysis.outline,
        "guard_notes": analysis.guard_notes,
    }
