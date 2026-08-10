#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uinput_typer.py
================
/dev/uinput 에 가상 하드웨어 키보드를 직접 생성하여, 커널 레벨에서
키 인터럽트를 발생시키는 저수준 타이핑 자동화 스크립트.

핵심 동작 원리
--------------
- evdev.UInput 으로 만든 가상 디바이스는 X11/Wayland 같은 '디스플레이 서버'가
  아니라 '리눅스 입력 서브시스템(/dev/input)'에 직접 이벤트를 주입한다.
- 따라서 Wayland 의 보안 격리(xdotool/pyautogui 차단)와 무관하게 동작하며,
  포커스를 가진 어떤 창(브라우저 textarea 포함)이든 물리 키보드와 동일하게
  입력을 받는다.
- 입력 경로가 커널이므로 SSH/tmux 같은 원격 셸에서 실행하더라도, 신호는
  '코드를 실행한 그 머신의 로컬 입력 스택'으로 전달된다. (원격 PC에서 로컬 PC를
  타이핑시키는 것이 아니라, uinput 디바이스가 생성된 머신의 로컬 세션에 입력된다.)

실행 전제
---------
- Ubuntu 24.04 LTS, Wayland 세션
- sudo 권한으로 실행 (/dev/uinput 쓰기 권한 필요)
"""

import sys
import time
import random

try:
    from evdev import UInput, ecodes as e
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError(
        "evdev 모듈이 없습니다. "
        "sudo apt install python3-evdev 또는 pip install evdev 로 설치하세요."
    ) from exc


# ---------------------------------------------------------------------------
# 1. 영문/숫자/특수문자 → (keycode, shift 필요 여부) 매핑 (US QWERTY 기준)
# ---------------------------------------------------------------------------
# 값: (evdev 키코드, Shift 동시 입력 필요 여부)
CHAR_MAP = {
    # --- 소문자 (Shift 불필요) ---
    'a': (e.KEY_A, False), 'b': (e.KEY_B, False), 'c': (e.KEY_C, False),
    'd': (e.KEY_D, False), 'e': (e.KEY_E, False), 'f': (e.KEY_F, False),
    'g': (e.KEY_G, False), 'h': (e.KEY_H, False), 'i': (e.KEY_I, False),
    'j': (e.KEY_J, False), 'k': (e.KEY_K, False), 'l': (e.KEY_L, False),
    'm': (e.KEY_M, False), 'n': (e.KEY_N, False), 'o': (e.KEY_O, False),
    'p': (e.KEY_P, False), 'q': (e.KEY_Q, False), 'r': (e.KEY_R, False),
    's': (e.KEY_S, False), 't': (e.KEY_T, False), 'u': (e.KEY_U, False),
    'v': (e.KEY_V, False), 'w': (e.KEY_W, False), 'x': (e.KEY_X, False),
    'y': (e.KEY_Y, False), 'z': (e.KEY_Z, False),

    # --- 대문자 (Shift 필요, 키코드는 소문자와 동일) ---
    'A': (e.KEY_A, True), 'B': (e.KEY_B, True), 'C': (e.KEY_C, True),
    'D': (e.KEY_D, True), 'E': (e.KEY_E, True), 'F': (e.KEY_F, True),
    'G': (e.KEY_G, True), 'H': (e.KEY_H, True), 'I': (e.KEY_I, True),
    'J': (e.KEY_J, True), 'K': (e.KEY_K, True), 'L': (e.KEY_L, True),
    'M': (e.KEY_M, True), 'N': (e.KEY_N, True), 'O': (e.KEY_O, True),
    'P': (e.KEY_P, True), 'Q': (e.KEY_Q, True), 'R': (e.KEY_R, True),
    'S': (e.KEY_S, True), 'T': (e.KEY_T, True), 'U': (e.KEY_U, True),
    'V': (e.KEY_V, True), 'W': (e.KEY_W, True), 'X': (e.KEY_X, True),
    'Y': (e.KEY_Y, True), 'Z': (e.KEY_Z, True),

    # --- 숫자 (Shift 불필요) ---
    '0': (e.KEY_0, False), '1': (e.KEY_1, False), '2': (e.KEY_2, False),
    '3': (e.KEY_3, False), '4': (e.KEY_4, False), '5': (e.KEY_5, False),
    '6': (e.KEY_6, False), '7': (e.KEY_7, False), '8': (e.KEY_8, False),
    '9': (e.KEY_9, False),

    # --- 숫자열 위 특수문자 (Shift 필요) ---
    '!': (e.KEY_1, True), '@': (e.KEY_2, True), '#': (e.KEY_3, True),
    '$': (e.KEY_4, True), '%': (e.KEY_5, True), '^': (e.KEY_6, True),
    '&': (e.KEY_7, True), '*': (e.KEY_8, True), '(': (e.KEY_9, True),
    ')': (e.KEY_0, True),

    # --- 기타 특수문자 ---
    '-':  (e.KEY_MINUS, False),      '_': (e.KEY_MINUS, True),
    '=':  (e.KEY_EQUAL, False),      '+': (e.KEY_EQUAL, True),
    '[':  (e.KEY_LEFTBRACE, False),  '{': (e.KEY_LEFTBRACE, True),
    ']':  (e.KEY_RIGHTBRACE, False), '}': (e.KEY_RIGHTBRACE, True),
    '\\': (e.KEY_BACKSLASH, False),  '|': (e.KEY_BACKSLASH, True),
    ';':  (e.KEY_SEMICOLON, False),  ':': (e.KEY_SEMICOLON, True),
    "'":  (e.KEY_APOSTROPHE, False), '"': (e.KEY_APOSTROPHE, True),
    ',':  (e.KEY_COMMA, False),      '<': (e.KEY_COMMA, True),
    '.':  (e.KEY_DOT, False),        '>': (e.KEY_DOT, True),
    '/':  (e.KEY_SLASH, False),      '?': (e.KEY_SLASH, True),
    '`':  (e.KEY_GRAVE, False),      '~': (e.KEY_GRAVE, True),

    # --- 공백/제어 문자 ---
    ' ':  (e.KEY_SPACE, False),
    '\t': (e.KEY_TAB, False),
    '\n': (e.KEY_ENTER, False),
}


# ---------------------------------------------------------------------------
# 2. 한글 → 두벌식 QWERTY 키 매핑
# ---------------------------------------------------------------------------
# 물리 키코드만 주입한다. 한글 조합은 OS IME가 한다.
# type_payload 가 한글/영문 구간마다 IME를 맞춘 뒤(ime.py), 한글 구간만
# 아래 매핑으로 QWERTY 시퀀스를 보낸다.

# 유니코드 완성형 한글 분해용 자모 테이블
_CHOSEONG = [  # 초성 19
    'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ',
    'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ',
]
_JUNGSEONG = [  # 중성 21
    'ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅘ',
    'ㅙ', 'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅠ', 'ㅡ', 'ㅢ', 'ㅣ',
]
_JONGSEONG = [  # 종성 28 (인덱스 0 = 받침 없음)
    '', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ',
    'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ',
    'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ',
]

# 단일 자모 → 두벌식 QWERTY 글자 (대문자는 CHAR_MAP 에서 Shift 처리됨)
_JAMO_TO_KEY = {
    # 자음
    'ㄱ': 'r', 'ㄲ': 'R', 'ㄴ': 's', 'ㄷ': 'e', 'ㄸ': 'E', 'ㄹ': 'f',
    'ㅁ': 'a', 'ㅂ': 'q', 'ㅃ': 'Q', 'ㅅ': 't', 'ㅆ': 'T', 'ㅇ': 'd',
    'ㅈ': 'w', 'ㅉ': 'W', 'ㅊ': 'c', 'ㅋ': 'z', 'ㅌ': 'x', 'ㅍ': 'v',
    'ㅎ': 'g',
    # 모음
    'ㅏ': 'k', 'ㅐ': 'o', 'ㅑ': 'i', 'ㅒ': 'O', 'ㅓ': 'j', 'ㅔ': 'p',
    'ㅕ': 'u', 'ㅖ': 'P', 'ㅗ': 'h', 'ㅛ': 'y', 'ㅜ': 'n', 'ㅠ': 'b',
    'ㅡ': 'm', 'ㅣ': 'l',
}

# 겹자모(복합 자모) → 단일 자모 2개로 분해 (두벌식은 두 키를 연달아 누름)
_COMPOUND_JAMO = {
    # 겹받침
    'ㄳ': 'ㄱㅅ', 'ㄵ': 'ㄴㅈ', 'ㄶ': 'ㄴㅎ', 'ㄺ': 'ㄹㄱ', 'ㄻ': 'ㄹㅁ',
    'ㄼ': 'ㄹㅂ', 'ㄽ': 'ㄹㅅ', 'ㄾ': 'ㄹㅌ', 'ㄿ': 'ㄹㅍ', 'ㅀ': 'ㄹㅎ',
    'ㅄ': 'ㅂㅅ',
    # 복합 모음
    'ㅘ': 'ㅗㅏ', 'ㅙ': 'ㅗㅐ', 'ㅚ': 'ㅗㅣ', 'ㅝ': 'ㅜㅓ', 'ㅞ': 'ㅜㅔ',
    'ㅟ': 'ㅜㅣ', 'ㅢ': 'ㅡㅣ',
}


def _jamo_to_qwerty_chars(jamo: str):
    """단일/복합 자모 하나를 두벌식 QWERTY 글자(들)로 변환한다."""
    if jamo in _JAMO_TO_KEY:
        return _JAMO_TO_KEY[jamo]
    if jamo in _COMPOUND_JAMO:                       # 겹자모는 재귀적으로 분해
        return ''.join(_jamo_to_qwerty_chars(j) for j in _COMPOUND_JAMO[jamo])
    return ''                                        # 매핑 없음


def hangul_to_qwerty(text: str) -> str:
    """
    한글 문장을 두벌식 기준의 QWERTY 입력 시퀀스(영문 문자열)로 변환한다.
    한글이 아닌 문자는 그대로 통과시킨다.

    예) "가나" -> "rksk"  (ㄱ=r, ㅏ=k, ㄴ=s, ㅏ=k)
    """
    out = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:                 # 완성형 한글 음절 영역
            s = code - 0xAC00
            cho = s // (21 * 28)
            jung = (s % (21 * 28)) // 28
            jong = s % 28
            out.append(_jamo_to_qwerty_chars(_CHOSEONG[cho]))
            out.append(_jamo_to_qwerty_chars(_JUNGSEONG[jung]))
            if jong:                                 # 받침이 있으면
                out.append(_jamo_to_qwerty_chars(_JONGSEONG[jong]))
        else:
            out.append(ch)                           # 영문/숫자/공백 등은 그대로
    return ''.join(out)


# ---------------------------------------------------------------------------
# 3. 가상 디바이스 생성 / 키 입력 / 본문 타이핑
# ---------------------------------------------------------------------------
# QWERTY 인접 키 (오타 시뮬레이션용). 소문자 기준.
_KEY_NEIGHBORS = {
    'q': 'wa', 'w': 'qeas', 'e': 'wrsd', 'r': 'etdf', 't': 'ryfg',
    'y': 'tugh', 'u': 'yihj', 'i': 'uojk', 'o': 'ipkl', 'p': 'ol',
    'a': 'qwsz', 's': 'awedxz', 'd': 'serfcx', 'f': 'drtgvc',
    'g': 'ftyhbv', 'h': 'gyujnb', 'j': 'huiknm', 'k': 'jiolm',
    'l': 'kop',
    'z': 'asx', 'x': 'zsdc', 'c': 'xdfv', 'v': 'cfgb',
    'b': 'vghn', 'n': 'bhjm', 'm': 'njk',
    '1': '2q', '2': '13w', '3': '24e', '4': '35r', '5': '46t',
    '6': '57y', '7': '68u', '8': '79i', '9': '80o', '0': '9p',
}


def build_capabilities():
    """CHAR_MAP 에서 쓰는 모든 키코드 + Shift/Backspace 를 디바이스 능력으로 등록."""
    keys = {code for (code, _shift) in CHAR_MAP.values()}
    keys.add(e.KEY_LEFTSHIFT)
    keys.add(e.KEY_BACKSPACE)
    return {e.EV_KEY: sorted(keys)}


def press_key(ui: "UInput", keycode: int, shift: bool = False):
    """단일 키 1회 입력 (필요 시 Shift 조합)."""
    if shift:
        ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1)   # Shift down
        ui.syn()
    ui.write(e.EV_KEY, keycode, 1)               # key down
    ui.syn()
    ui.write(e.EV_KEY, keycode, 0)               # key up
    ui.syn()
    if shift:
        ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0)   # Shift up
        ui.syn()


def _pick_typo_char(ch: str) -> str | None:
    """인접 키 오타 후보. 공백/제어문자는 None."""
    if ch in (" ", "\t", "\n"):
        return None
    base = ch.lower()
    neighbors = _KEY_NEIGHBORS.get(base)
    if not neighbors:
        return None
    wrong = random.choice(neighbors)
    return wrong.upper() if ch.isupper() else wrong


def _human_delay(min_delay: float, max_delay: float,
                 pause_prob: float, long_pause_prob: float) -> float:
    """
    키 간 지연. 평소엔 min~max 근처, 가끔 짧은 멈춤, 드물게 긴 멈춤.
    분포를 살짝 비대칭(감마)으로 잡아 기계적 uniform 느낌을 줄인다.
    """
    roll = random.random()
    if roll < long_pause_prob:
        # 낮은 확률 — 생각하는 척 / 읽기 멈춤
        return random.uniform(0.45, 1.8)
    if roll < long_pause_prob + pause_prob:
        return random.uniform(0.12, 0.45)
    # 기본: 감마로 치우친 값 + 가끔 아주 빠른 연타
    span = max(max_delay - min_delay, 1e-4)
    if random.random() < 0.08:
        return random.uniform(max(0.012, min_delay * 0.4), min_delay + span * 0.35)
    # mean ≈ mid, 오른쪽에 꼬리
    mid = (min_delay + max_delay) / 2
    sample = random.gammavariate(2.2, span / 2.2)
    return min(max_delay * 1.35, min_delay + abs(sample - (span * 0.3)) * 0.9 + (mid - min_delay) * 0.15)


def type_text(
    ui: "UInput",
    text: str,
    min_delay: float = 0.03,
    max_delay: float = 0.08,
    typo_prob: float = 0.045,
    pause_prob: float = 0.06,
    long_pause_prob: float = 0.012,
    typo_skip_first: int = 0,
):
    """
    문자열을 한 글자씩 키 인터럽트로 주입한다.
    - typo_prob: 글자마다 인접키 오타 → Backspace → 재입력
    - typo_skip_first: 앞 N키는 오타 시뮬레이션 안 함 (시작 직후 티 안 나게)
    - 지연은 불규칙(짧은 연타 / 짧은 멈춤 / 드물게 긴 멈춤)
    """
    for index, ch in enumerate(text):
        mapping = CHAR_MAP.get(ch)
        if mapping is None:
            sys.stderr.write(f"[경고] 매핑되지 않은 문자 건너뜀: {ch!r}\n")
            continue

        typo = None
        if index >= typo_skip_first and random.random() < typo_prob:
            typo = _pick_typo_char(ch)

        if typo is not None:
            typo_map = CHAR_MAP.get(typo)
            if typo_map is not None:
                press_key(ui, *typo_map)
                time.sleep(_human_delay(min_delay, max_delay, pause_prob, long_pause_prob) * 0.7)
                # 인지 → 지우기
                time.sleep(random.uniform(0.05, 0.18))
                press_key(ui, e.KEY_BACKSPACE)
                time.sleep(random.uniform(0.04, 0.14))

        keycode, shift = mapping
        press_key(ui, keycode, shift)
        time.sleep(_human_delay(min_delay, max_delay, pause_prob, long_pause_prob))


def countdown(seconds: int = 5, on_tick=None):
    """타겟 입력창을 클릭해 포커스를 줄 시간을 카운트다운으로 안내."""
    if on_tick is None:
        print(f"\n[준비] {seconds}초 안에 브라우저의 입력창(textarea)을 클릭해 "
              f"포커스를 맞추세요.")
    for remaining in range(seconds, 0, -1):
        if on_tick is not None:
            on_tick(remaining)
        else:
            print(f"  타이핑 시작까지 {remaining}초...", end="\r", flush=True)
        time.sleep(1)
    if on_tick is None:
        print(" " * 40, end="\r")   # 카운트다운 줄 정리
        print("[시작] 타이핑을 시작합니다.\n")


# BUS_USB(기본) 가상 키보드는 Dell Inspiron 등에서 터치패드를 먹통으로
# 만드는 사례가 있다. BUS_VIRTUAL + 전용 이름으로 외부 USB 입력기처럼
# 보이지 않게 한다. 디바이스는 타이핑 동안에만 연다.
_UINPUT_NAME = "blankfloat-kbd"
_UINPUT_VENDOR = 0x0000
_UINPUT_PRODUCT = 0xBF01


def open_uinput() -> "UInput":
    """가상 키보드를 연다. 권한/모듈 문제는 PermissionError/OSError."""
    return UInput(
        build_capabilities(),
        name=_UINPUT_NAME,
        bustype=e.BUS_VIRTUAL,
        vendor=_UINPUT_VENDOR,
        product=_UINPUT_PRODUCT,
        phys="blankfloat/uinput",
    )


def type_payload(
    text: str,
    *,
    countdown_secs: int = 3,
    convert_hangul: bool = True,
    switch_ime: bool = True,
    settle_secs: float | None = None,
    ui: "UInput | None" = None,
    min_delay: float = 0.03,
    max_delay: float = 0.08,
    typo_prob: float = 0.045,
    pause_prob: float = 0.06,
    long_pause_prob: float = 0.012,
    typo_skip_first: int = 8,
    on_tick=None,
    on_status=None,
    ime=None,
):
    """
    uinput 으로 text 를 타이핑한다.

    기본값: 한글/영문 구간마다 IME를 맞춘 뒤, 한글 구간만 두벌식 QWERTY로
    바꿔 보낸다 (``switch_ime`` / ``convert_hangul`` 로 끌 수 있음).

    ``typo_skip_first``: 전체 타이핑 시작 후 앞 N키는 오타 없음 (구간 넘어가도 이어짐).

    ``ui`` 를 넘기면 그 디바이스를 재사용하고 닫지 않는다 (settle 기본 0).
    없으면 타이핑 직전에 열고 끝나면 바로 닫으며 settle 기본 0.25초.
    (상시 open 은 Dell 터치패드 먹통 유발 — 프로세스 수명 재사용 안 함.)
    """
    from .ime import ImeController, script_runs

    owns_ui = ui is None
    if settle_secs is None:
        settle_secs = 0.25 if owns_ui else 0.0
    if owns_ui:
        ui = open_uinput()
    assert ui is not None

    controller = ime
    if switch_ime and controller is None:
        controller = ImeController()
    snap = controller.snapshot() if controller is not None else None
    runs = script_runs(text) if (switch_ime or convert_hangul) else [("latin", text)]

    try:
        # 커널/udev 가 새 디바이스를 인식해 입력 스택에 붙일 시간
        if settle_secs > 0:
            if on_status:
                on_status("디바이스 준비 중...")
            time.sleep(settle_secs)
        if countdown_secs > 0:
            if on_status:
                on_status("입력창을 클릭하세요")
            countdown(countdown_secs, on_tick=on_tick)
        if on_status:
            on_status("타이핑 중...")

        skip_left = max(0, int(typo_skip_first))
        for mode, chunk in runs:
            if not chunk:
                continue
            if controller is not None:
                controller.set_mode(mode)
            if mode == "hangul" and convert_hangul:
                payload = hangul_to_qwerty(chunk)
            else:
                payload = chunk
            type_text(
                ui,
                payload,
                min_delay=min_delay,
                max_delay=max_delay,
                typo_prob=typo_prob,
                pause_prob=pause_prob,
                long_pause_prob=long_pause_prob,
                typo_skip_first=skip_left,
            )
            skip_left = max(0, skip_left - len(payload))
        if on_status:
            on_status("완료")
    finally:
        if controller is not None:
            try:
                controller.restore(snap)
            except Exception:  # noqa: BLE001 — typing already finished
                pass
        if owns_ui:
            ui.close()


def main():
    payload = '''
Regarding Google's Corporate Social Responsibility (CSR) model, the company's key activity is releasing Gemma as open-source and allowing users to access the advanced Gemini models for free or at a low subscription fee. By opening up AI technologies that require massive computing resources, Google lowers the technological entry barriers for academia and SMEs, which aligns with CSR by preventing the monopolization of knowledge and alleviating technological inequality at a societal level. It is highly advantageous that users can access state-of-the-art AI models either for free or at a significantly lower cost compared to the expense of running an LLM directly in a local environment. Through this case, I learned that while such corporate initiatives democratize AI access, they must be viewed objectively as strategic business moves aimed at ecosystem dominance rather than pure charity. It taught me the necessity of maintaining a critical perspective on these "free" corporate models, recognizing the potential risks of platform lock-in, and emphasizing the importance of transparent data governance and ethical accountability behind these technological contributions.
'''
    try:
        type_payload(payload, countdown_secs=3)
        print("\n[완료] 타이핑이 끝났습니다.")
    except PermissionError:
        sys.stderr.write(
            "[오류] /dev/uinput 접근 권한이 없습니다. sudo 로 실행하세요.\n"
            "       (필요 시: sudo modprobe uinput)\n"
        )
        sys.exit(1)
    except OSError as err:
        sys.stderr.write(
            f"[오류] uinput 디바이스 생성 실패: {err}\n"
            "       'uinput' 커널 모듈이 로드되어 있는지 확인하세요: "
            "sudo modprobe uinput\n"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        sys.stderr.write("\n[중단] 사용자에 의해 중지되었습니다.\n")


if __name__ == "__main__":
    main()


# sudo .venv/bin/python3 uinput_typer.py
# sudo .venv/bin/python3 typer_ui.py