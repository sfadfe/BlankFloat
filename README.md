# blankfloat

과제 화면을 영역 캡처하면, 빈칸·단답은 **답만** 띄우고 글쓰기 과제는 **영문 프롬프트**를 만드는 리눅스 플로팅 유틸.  
자동입력(구 tqtq)도 같은 프로세스에 붙어 있다.

```text
영역 캡처 → 비전 모델 1회 → 답 카드 / 영문 프롬프트
자동입력 창 → /dev/uinput 가상 키보드 → 포커스 창에 타이핑
```

라우팅 규칙: [`docs/ROUTING.md`](docs/ROUTING.md)

## 설치

Ubuntu GNOME **Wayland** (개발·검증: Ubuntu 24.04 / GNOME 46), Python 3.10+.

```bash
sudo apt install python3-tk python3-gi python3-requests python3-pil python3-evdev \
  xdg-desktop-portal xdg-desktop-portal-gnome
```

선택: `flameshot` (비-GNOME 또는 `BLANKFLOAT_CAPTURE` 폴백). GNOME Wayland에서는 기본으로 쓰지 않는다. `grim`/`slurp`는 wlroots 전용.

### 자동입력 권한 (`/dev/uinput`)

Wayland는 `xdotool` / `pyautogui` 같은 합성 입력을 막는다. 그래서 **커널 uinput**으로 가상 키보드를 만든다 (`python3-evdev` → `/dev/uinput`).

```bash
# 방법 A: 사용자를 input 그룹에 넣고 재로그인
sudo usermod -aG input "$USER"

# 방법 B: udev로 uinput 쓰기 허용 (예시)
# echo 'KERNEL=="uinput", MODE="0660", GROUP="input"' | sudo tee /etc/udev/rules.d/99-uinput.rules
# sudo udevadm control --reload-rules && sudo udevadm trigger

# 모듈이 없으면
sudo modprobe uinput
```

권한이 없으면 자동입력만 실패하고, 캡처·분석은 그대로 된다.

## 설정

1. [Google AI Studio](https://aistudio.google.com/apikey)에서 API 키 발급
2. 프로젝트 루트에 `.env` 만들기:

```bash
cp example.env .env
# BLANKFLOAT_API_KEY=... 채우기
```

기본 모델: `gemini-3.5-flash-lite`  
기본 URL: `https://generativelanguage.googleapis.com/v1beta/openai`

다른 모델/프로바이더는 `.env`의 `BLANKFLOAT_MODEL` / `BLANKFLOAT_BASE_URL`을 바꾸면 된다.  
우선순위: 이미 있는 환경변수 → `.env` → `~/.config/blankfloat/config.json`

```bash
./bin/blankfloat config
```

## 실행

```bash
./bin/blankfloat              # 자동입력 창 + 캡처 데몬 (한 프로세스)
./bin/blankfloat --capture    # 띄우자마자 캡처
./bin/blankfloat stop         # 전체 종료
```

- **자동입력 창**은 항상 떠 있다. 텍스트 넣고 `확인` 또는 `Ctrl+Enter` → 창이 숨겨진 뒤 3초 카운트다운 → 포커스된 창에 타이핑.
- 핫키/`capture`로 찍으면 분석 후 **답 카드**가 뜬다. 카드 `✕` / `Esc`는 카드만 닫는다.
- 전체 종료: 자동입력 창 닫기, `Ctrl+Q`, 또는 `./bin/blankfloat stop`.
- 답 카드 텍스트는 드래그해서 복사하면 된다. (답 → 자동입력 자동 연동은 없음)

한글은 두벌식 QWERTY 시퀀스로 보내고, 대상 창 IME가 한글 모드일 때 조합된다.

### 핫키 (GNOME)

앱이 Wayland에서 전역 단축키를 잡을 수 없어서 **GNOME 커스텀 키바인딩**으로 등록한다.

```bash
./scripts/install-hotkey.sh                         # 기본 키
./scripts/install-hotkey.sh '<Super>a' '<Super>m'   # 다른 키
./scripts/uninstall-hotkey.sh
```

| 핫키 (기본) | 동작 |
|-------------|------|
| `Ctrl+Shift+Alt+A` | 캡처. 평소=단발 분석, 멀티 세션 중=샷만 추가 |
| `Ctrl+Shift+Alt+M` | 멀티샷 on/off. off로 끌 때 메모 입력 후 모아둔 샷 일괄 분석 (Enter 전송 / Esc 취소) |

CLI: `./bin/blankfloat capture` / `./bin/blankfloat multi`  
데몬이 없으면 해당 동작으로 앱을 띄운다.

로그인 시 데몬을 미리 올려 핫키 콜드스타트를 피하려면:

```bash
./scripts/install-autostart.sh
./scripts/uninstall-autostart.sh
```

앱 그리드/대시용 바로가기:

```bash
./scripts/install-desktop.sh            # ~/.local/share/applications
./scripts/install-desktop.sh --desktop  # + 바탕화면 복사
./scripts/uninstall-desktop.sh
```

### UI 없이 파일만 분석

```bash
./bin/blankfloat analyze shot.png
./bin/blankfloat analyze shot.png --mode simple --raw
```

`--mode`: `auto` / `simple` / `complex` (기본은 설정값).

## Wayland에서 뭘 썼는지 (Ubuntu GNOME)

| 막히는 것 | 우회 |
|-----------|------|
| `org.gnome.Shell.Screenshot` 직접 호출 | GNOME 42+에서 AccessDenied → 쓰지 않음 |
| 대화형 스크린샷 포털 / flameshot | 권한 허용 후에도 자주 실패 (`response code 2` 등) |
| 앱 전역 핫키 | Wayland가 막음 → `gsettings` 커스텀 키바인딩 |
| `xdotool` / `pyautogui` | 컴포지터가 합성 입력 차단 |

실제로 쓰는 경로:

1. **캡처** — XDG Desktop Portal (`org.freedesktop.portal.Screenshot`, `python3-gi`)  
   - GNOME Wayland 기본: **비대화형 전체 캡처** + **Tk 드래그 크롭** (`portal-region`만)  
   - `parent_window`는 빈 문자열 금지 → `wayland:` / `x11:$DISPLAY`  
   - 다른 세션/강제 폴백: `BLANKFLOAT_CAPTURE=portal-region,flameshot,…`
2. **핫키** — `scripts/install-hotkey.sh`가 GNOME에 `blankfloat capture` / `multi` 등록  
   - 데몬 상시: `scripts/install-autostart.sh`
3. **자동입력** — `evdev.UInput` → `/dev/uinput` (프로세스 수명 동안 재사용)

## 개발

```bash
python3 -m unittest discover -s tests
```
