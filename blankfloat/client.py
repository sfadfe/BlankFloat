"""OpenAI-compatible chat client (Gemini / Z.AI / …).

One call does classification and generation together (docs/ROUTING.md, v1).
"""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path

import requests
from PIL import Image

from .config import Config
from .prompts import SYSTEM_PROMPT, user_text

# Free-tier / busy endpoints often return HTTP 429. Back off and retry.
OVERLOAD_BACKOFF_SECONDS = (2.0, 5.0, 12.0, 20.0)


class ApiError(RuntimeError):
    pass


class MissingApiKey(ApiError):
    pass


def encode_image(path: Path, max_px: int = 1600) -> str:
    with Image.open(path) as img:
        img = img.convert("RGB")
        if max(img.size) > max_px:
            scale = max_px / max(img.size)
            new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
            img = img.resize(new_size, Image.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _messages(
    image_b64s: str | list[str],
    mode: str,
    retry: bool,
    payload_style: str,
    extra_text: str = "",
) -> list[dict]:
    if isinstance(image_b64s, str):
        image_b64s = [image_b64s]
    content: list[dict] = []
    for image_b64 in image_b64s:
        url = image_b64 if payload_style == "base64" else f"data:image/png;base64,{image_b64}"
        content.append({"type": "image_url", "image_url": {"url": url}})
    text = user_text(mode, retry=retry)
    if len(image_b64s) > 1:
        text = (
            f"You are given {len(image_b64s)} sequential screenshots of one assignment "
            f"(capture order: image 1 is first). Treat them as one continuous task.\n\n"
            + text
        )
    note = (extra_text or "").strip()
    if note:
        text = f"{text}\n\nAdditional user note:\n{note}"
    content.append({"type": "text", "text": text})
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def _post(cfg: Config, messages: list[dict]) -> requests.Response:
    return requests.post(
        f"{cfg.base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": cfg.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 2048,
        },
        timeout=cfg.timeout,
    )


def _debug_log(message: str) -> None:
    try:
        import os as _os
        import time as _time

        path = Path(_os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "blankfloat-api.log"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{_time.strftime('%H:%M:%S')} {message}\n")
    except OSError:
        pass


def _is_overload(status_code: int, body: str) -> bool:
    if status_code != 429:
        return False
    lowered = body.lower()
    # Z.AI free flash congestion, Gemini free-tier quota bursts, generic rate limits.
    return any(
        token in lowered
        for token in (
            "overload",
            "1305",
            "congest",
            "rate limit",
            "quota",
            "resource_exhausted",
            "too many requests",
        )
    )


def _message_for_429(body: str) -> str:
    lowered = body.lower()
    if "balance" in lowered or "recharge" in lowered or "1113" in lowered:
        return "API 잔액/패키지가 부족합니다. 결제 플랜을 확인하세요."
    if _is_overload(429, body):
        return "모델이 일시적으로 바쁩니다(429). 조금 뒤 다시 시도하세요."
    return f"호출이 거절되었습니다 (429): {body or 'rate limited'}"


def analyze(
    image_path: Path | list[Path],
    mode: str,
    cfg: Config,
    retry: bool = False,
    extra_text: str = "",
) -> str:
    """Send one or more screenshots and return the raw assistant text."""
    if not cfg.api_key:
        raise MissingApiKey(
            "API 키가 없습니다. 프로젝트 .env의 BLANKFLOAT_API_KEY, "
            "환경변수, 또는 ~/.config/blankfloat/config.json에 넣어 주세요."
        )

    paths = [image_path] if isinstance(image_path, Path) else list(image_path)
    if not paths:
        raise ApiError("이미지가 없습니다.")

    image_b64s = [encode_image(path, cfg.max_image_px) for path in paths]
    styles = [cfg.image_payload, "data_url" if cfg.image_payload == "base64" else "base64"]
    names = ",".join(p.name for p in paths)
    note = (extra_text or "").strip()
    _debug_log(
        f"analyze start mode={mode} retry={retry} model={cfg.model} "
        f"images={len(paths)} ({names}) note={bool(note)}"
    )

    last_error = ""
    overload_attempt = 0

    while True:
        for style in styles:
            try:
                started = time.monotonic()
                response = _post(
                    cfg,
                    _messages(image_b64s, mode, retry, style, extra_text=note),
                )
                elapsed = time.monotonic() - started
            except requests.Timeout as exc:
                _debug_log(f"timeout style={style}")
                raise ApiError(f"응답 시간 초과 ({cfg.timeout:.0f}s)") from exc
            except requests.RequestException as exc:
                _debug_log(f"network error style={style}: {exc}")
                raise ApiError(f"네트워크 오류: {exc}") from exc

            body = _error_text(response) if not response.ok else ""
            _debug_log(
                f"http {response.status_code} style={style} {elapsed:.2f}s"
                + (f" err={body}" if body else "")
            )

            if response.status_code == 400:
                last_error = body
                continue

            if response.status_code == 401:
                raise MissingApiKey("API 키가 거부되었습니다 (401).")

            if _is_overload(response.status_code, body):
                if overload_attempt >= len(OVERLOAD_BACKOFF_SECONDS):
                    raise ApiError(_message_for_429(body))
                wait = OVERLOAD_BACKOFF_SECONDS[overload_attempt]
                overload_attempt += 1
                _debug_log(f"overload backoff {wait}s (attempt {overload_attempt})")
                time.sleep(wait)
                break  # restart style loop after backoff

            if response.status_code == 429:
                raise ApiError(_message_for_429(body))

            if not response.ok:
                raise ApiError(f"HTTP {response.status_code}: {body}")

            if style != cfg.image_payload:
                cfg.image_payload = style
            text = _content(response)
            _debug_log(f"ok chars={len(text)}")
            return text
        else:
            # No overload break; either success returned, or all styles failed with 400.
            raise ApiError(f"이미지 요청이 거부되었습니다: {last_error}")


def _error_text(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:300]
    error = data.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)[:300]
    return str(error or data)[:300]


def _content(response: requests.Response) -> str:
    try:
        data = response.json()
        message = data["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ApiError(f"예상치 못한 응답 형식: {response.text[:200]}") from exc

    content = message.get("content")
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content if isinstance(c, dict)]
        content = "".join(parts)
    if not isinstance(content, str) or not content.strip():
        raise ApiError("모델이 빈 응답을 보냈습니다.")
    return content
