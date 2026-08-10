# Routing Logic

Blankfloat routes each screenshot into `simple` (direct answers), `complex` (English prompt for Korean writing), or `unreadable`.

## Architecture

```text
1차(메인): VLM 분류        ← GLM-4.6V-Flash가 route 결정
2차(보조): 로컬 가드       ← 짧은 하드코딩 후처리
3차(탈출): 사용자 강제모드 ← auto / simple / complex
```

- **메인 라우터는 키워드 if문 하드코딩이 아님.**
- 분류 규칙은 **시스템 프롬프트**에 두고, 모델이 JSON `route`를 반환한다.
- 앱 코드는 그 결과를 소비하고, 깨진 출력만 로컬 가드로 보정한다.
- v1은 **분류 + 생성 1회 호출** (분류 전용 / 답변 전용 2콜 안 함).

## Input

| Field | Description |
|-------|-------------|
| screenshot(s) | One region capture (PNG), or several sequential captures of one assignment |
| `user_mode` | `auto` (default) \| `simple` \| `complex` |

`user_mode != auto`이면 모델 분류를 무시하고 해당 모드만 실행한다.

멀티샷은 캡처 UX일 뿐이며 `simple`/`complex`를 강제하지 않는다. 여러 이미지는 한 메시지에
이미지 여러 장으로 보내고(세로 stitch 없음), 캡처 순서가 과제 순서다.

## Model output schema

Always require this JSON shape from `GLM-4.6V-Flash`:

```json
{
  "route": "simple" | "complex" | "unreadable",
  "confidence": 0.0,
  "reason": "short English tag",
  "language": "ko" | "en" | "mixed" | "other",
  "question_count": 0,
  "signals": {
    "has_blanks": false,
    "has_choices": false,
    "has_short_answer": false,
    "has_math": false,
    "has_writing": false,
    "max_expected_chars": null
  },
  "answers": [
    { "id": "1", "text": "...", "uncertain": false }
  ],
  "prompt": null,
  "outline": null
}
```

| `route` | Required fields |
|---------|-----------------|
| `simple` | `answers` filled, `prompt = null` |
| `complex` | `prompt` filled, `answers = []` |
| `unreadable` | both empty; UI asks to recapture |

## Classification rules (prompt-side, priority high → low)

### A. `unreadable`

- Text mostly unreadable, cropped, or not an assignment region

### B. `complex` (any match → complex)

- Essay / opinion / reflection / self-intro / report / email / speech
- “쓰시오 / 작성하시오 / 서술하시오” **and** expected length is paragraph-scale  
  (roughly **≥ 80 chars** or **> 3 sentences**)
- Long free-response spanning multiple paragraphs
- Rubric present and the deliverable is a full written piece

### C. `simple` (everything else that is readable)

- Fill-in-the-blank
- True/false, multiple choice
- Short answer (word / phrase / number / symbol / short expression)
- Math/science **final answer** when a long written solution is not explicitly required
- Short written response: **≤ 3 sentences** or **< 80 expected chars**

### Mixed capture (blanks + essay in one shot)

- If `has_writing=true` and there is a real writing item → **`complex` wins** (v1)
- One-line “소감” level writing → still `simple`
- Per-item `mixed` routing is **out of scope for v1**

## Local guards (post-process)

Applied after parsing model JSON:

```text
if user_mode != auto:
    route = user_mode

elif route == complex and confidence < 0.45:
    route = simple          # prefer answers when ambiguous
    # keep complex if answers is empty

elif route == simple and signals.has_writing and max_expected_chars >= 200:
    route = complex

elif route == simple and answers is empty:
    route = complex if signals.has_writing else unreadable
```

Principles:

- **Ambiguous → prefer `simple`** (lower friction)
- Strong writing signal + large expected length → **promote to `complex`**
- Local guards are **output repair**, not the main router

Also:

- JSON parse failure → retry once, then `unreadable`
- Invalid `route` / missing required fields → same

## Mode generation rules

### `simple`

- Fill `answers[]` in blank/number order
- Answers only; explanation off by default
- If unsure: `uncertain: true`; at most two candidates as `A / B` in `text`
- Math: **final answer** first; keep formulas short inside the answer string

### `complex`

- Do **not** write the final essay body in the app
- `prompt`: **English instructions**
  - Must include: `Final output language: Korean`
  - Quote topic / constraints / length / format from the screenshot **in Korean as-is**
  - Restate visible rubric/constraints in English
  - Instruct continuous prose paragraphs for a student submission; forbid numbered /
    bulleted outline answers unless the screenshot itself requires that structure
  - Do not embed a completed draft inside the prompt
- `outline`: optional Korean bullets (3–5) shown separately for the user
  (planning aid only — not the deliverable body)
- User pastes `prompt` into another chat model; blankfloat is a **prompt factory** here

## Decision tree

```text
screenshot
    │
    ▼
user_mode? ── simple/complex ──► generate that mode only
    │ auto
    ▼
VLM → JSON(route, signals, confidence, ...)
    │
    ├─ unreadable ──────────► recapture UI
    │
    ├─ local guards
    │
    ├─ simple ──► answers card
    └─ complex ─► prompt (+ outline) copy card
```

## Explicitly not in v1

- Per-question `mixed` routing
- Showing simple answers and complex prompt at the same time
- Dedicated “full solution steps” mode (math stays final-answer under `simple`)

## Model

- Provider: Gemini (Google AI Studio). OpenAI-compatible endpoint.
- Model: `gemini-3.5-flash-lite` (alt: `gemini-3.1-flash-lite`)
- Base URL: `https://generativelanguage.googleapis.com/v1beta/openai`
- Optional: Z.AI `glm-4.6v-flash` via env override
