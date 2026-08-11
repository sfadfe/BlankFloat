# blankfloat 작업 노트

## 환경 사실

- 세션: Ubuntu GNOME 46, **Wayland** (`XDG_SESSION_TYPE=wayland`), XWayland도 있음 (`DISPLAY=:0`).
- `org.gnome.Shell.Screenshot.ScreenshotArea` / `SelectArea`는 GNOME 42+에서 막힘:
  `GDBus.Error:org.freedesktop.DBus.Error.AccessDenied: ScreenshotArea is not allowed`.
- 영역 캡처: GNOME Wayland에서는 **portal-region만** 쓴다 (비대화형 전체 캡처 + Tk 크롭).
  flameshot / interactive portal / grim / spectacle는 스킵
  (`BLANKFLOAT_CAPTURE=…`로 강제 가능).
  GNOME interactive portal / flameshot은 권한 allow 후에도
  `InteractiveScreenshot didn't return a file` / response code 2로 자주 실패한다.
  비대화형(`interactive: false`) 전체 캡처는 allow 이후 동작 확인됨.
- `grim`은 설치돼 있어도 wlroots 전용이라 GNOME에서는 못 씀. `slurp`, `gnome-screenshot` 없음.
- 포털을 쓸 때는 `parent_window`를 빈 문자열로 보내면 GNOME 46이 거절한다.
  `wayland:` / `x11:$DISPLAY` 같은 non-empty 핸들을 넣는다.
- 이미 있는 파이썬 모듈: `tkinter`, `gi`(PyGObject), `PIL` 10.2, `requests`. **PySide6 없음** →
  UI는 추가 설치 없이 가는 Tk 기준으로 만들었다.
- 자동입력(tqtq): `blankfloat/typer/` (`uinput_typer` + Tk UI). `evdev` + `/dev/uinput` 쓰기 권한 필요.
  `./bin/blankfloat`는 자동입력 창(상시) + 답카드 데몬을 한 프로세스/한 mainloop로 띄운다.
  uinput 은 타이핑 구간에만 open/close (`BUS_VIRTUAL`, 이름 `blankfloat-kbd`).
  상시 USB 가상 키보드는 Dell Inspiron 터치패드 먹통을 유발한다.
  답→자동입력 연동은 없다. 확인 후 카운트다운·타이핑 중에는 자동입력 창을 `withdraw`한다.
  한/영 구간마다 IME 전환 (`typer/ime.py`, 기본 fcitx5). `BLANKFLOAT_IME=off` 로 비활성.
- 핫키는 데몬 IPC에 의존한다. 로그인 시 데몬: `scripts/install-autostart.sh`.
  없으면 `capture`/`multi`가 콜드스타트한다.
- 멀티샷: `blankfloat multi` / `Ctrl+Shift+Alt+M`은 세션 on/off만.
  샷은 `capture`/`Ctrl+Shift+Alt+A`로 append. 종료(2회 M) 시 모아둔 샷 일괄 분석.
  API에는 이미지 여러 장을 한 메시지에 보냄 (세로 stitch 없음). 종료 직후 짧은 메모
  입력창이 뜨고, Enter면 메모를 붙여 API 전송·창 닫힘, Esc면 전송 취소.
  메모 창은 핫키(Ctrl+Shift+Alt+M) 해제 후 ~350ms에 띄움 (캡처와 동일 settle;
  안 그러면 Wayland에서 Entry 포커스/grab이 실패함). 부모는 withdrawn 답카드가 아니라
  Tk 루트(타이퍼 창).

## 설정 / 비밀

- API 키는 프로젝트 루트 `.env`의 `BLANKFLOAT_API_KEY`로 관리한다 (`example.env` 템플릿).
  `.env`는 gitignore. Gemini 발급: https://aistudio.google.com/apikey
  기본 base URL: `https://generativelanguage.googleapis.com/v1beta/openai`
  기본 모델: `gemini-3.5-flash-lite` (alt: `gemini-3.1-flash-lite`)
- `config.load_dotenv()`는 이미 있는 환경변수를 덮어쓰지 않는다. 추가 의존성 없이 파싱.

## 에이전트 샌드박스

- 기본 샌드박스에서는 **D-Bus 세션 소켓이 안 보임** (`/run/user/1000/bus` 접근 불가).
  `gdbus`, 포털 캡처, GUI 실행을 검증하려면 `required_permissions: ["all"]`로 돌려야 한다.
- 네트워크도 allowlist라 Gemini/Z.AI 호출 검증은 `full_network` 필요.
- Gemini 무료 티어·Z.AI flash는 HTTP 429가 날 수 있다.
  클라이언트가 2/5/12/20초 백오프로 재시도한다.

## UI

- 지금 Tk UI는 **기능 우선 스모크용**이라 디자인이 개구리다.
  **기능 구현이 끝난 뒤에** 손본다. 그 전까지 시각 폴리시/리디자인에 시간 쓰지 말 것.

## 코드 규칙

- 라우팅 규칙 본문은 `blankfloat/prompts.py`의 시스템 프롬프트에 둔다.
  파이썬 `routing.apply_guards()`는 `docs/ROUTING.md`의 가드 체인만 그대로 구현하고,
  키워드 기반 분류를 새로 추가하지 않는다.
- `docs/ROUTING.md`를 고치면 `prompts.py`, `routing.apply_guards()`, `tests/test_routing.py`를 같이 맞춘다.
- GLib 메인루프는 Tk 메인루프와 섞지 않는다. 포털 캡처는 `python3 -m blankfloat.portal_screenshot`
  **별도 프로세스**로 돌리고 종료 코드로 결과를 받는다 (0 성공 / 2 취소 / 1 오류).
- PyGObject 함정: `GLib.Variant("(sa{sv})", ("", options))`의 `options`는 **파이썬 dict**여야 한다.
  이미 만든 `GLib.Variant("a{sv}", ...)`를 넣으면 `KeyError: 0`으로 죽는다.

## 검증

```bash
python3 -m unittest discover -s tests     # 샌드박스에서 가능
./bin/blankfloat config                   # 설정 확인
./bin/blankfloat analyze shot.png         # API 키 + 네트워크 필요
```
