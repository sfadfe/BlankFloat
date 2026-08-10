"""blankfloat CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import ipc
from .config import MODES, Config, config_path


def build_parser() -> argparse.ArgumentParser:
    # The shared flags suppress their defaults so that writing them before the
    # subcommand ("blankfloat --mode simple analyze shot.png") keeps working.
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--mode", choices=MODES, default=argparse.SUPPRESS,
                        help="시작 모드 (기본: 설정값)")
    shared.add_argument("--capture", action="store_true", default=argparse.SUPPRESS,
                        help="실행하자마자 캡처")

    parser = argparse.ArgumentParser(prog="blankfloat", description="플로팅 과제 캡처 도우미")
    parser.add_argument("--mode", choices=MODES, default=None, help="시작 모드 (기본: 설정값)")
    parser.add_argument("--capture", action="store_true", help="실행하자마자 캡처")

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", parents=[shared], help="자동입력 GUI + 캡처 데몬 실행 (기본)")
    sub.add_parser("capture", parents=[shared], help="실행 중인 데몬에 캡처 요청 (핫키용)")
    sub.add_parser(
        "multi",
        parents=[shared],
        help="멀티샷 토글 (세션 on/off; 캡처는 capture 핫키)",
    )
    sub.add_parser("config", parents=[shared], help="현재 설정 출력")
    sub.add_parser("stop", help="실행 중인 앱 종료")

    analyze_cmd = sub.add_parser("analyze", parents=[shared], help="이미지 파일 하나를 분석 (UI 없음)")
    analyze_cmd.add_argument("image", type=Path)
    analyze_cmd.add_argument("--raw", action="store_true", help="모델 원본 응답도 출력")

    return parser


def _config(args) -> Config:
    cfg = Config.load()
    if args.mode:
        cfg.default_mode = args.mode
    return cfg


def cmd_run(args) -> int:
    from .ui import run as run_ui

    run_ui(_config(args), start_capture=args.capture)
    return 0


def cmd_capture(args) -> int:
    if ipc.send("capture") == "ok":
        return 0

    from .ui import run as run_ui

    run_ui(_config(args), start_capture=True)
    return 0


def cmd_multi(args) -> int:
    if ipc.send("multi") == "ok":
        return 0

    from .typer import TyperApp
    from .ui.app import FloatingApp

    # No daemon yet: start app and arm multi-shot (captures via capture hotkey).
    cfg = _config(args)
    typer = TyperApp()
    typer.root._blankfloat_typer_close = typer.close  # noqa: SLF001
    app = FloatingApp(cfg, master=typer.root)
    typer.root.protocol("WM_DELETE_WINDOW", app.quit)
    app.root.after(250, app.toggle_multi)
    try:
        typer.run()
    finally:
        typer.close()
    return 0


def cmd_analyze(args) -> int:
    from . import pipeline
    from .routing import to_dict

    if not args.image.exists():
        print(f"파일이 없습니다: {args.image}", file=sys.stderr)
        return 1

    cfg = _config(args)
    result = pipeline.analyze_image(args.image, cfg.default_mode, cfg)
    payload = {
        "error": result.error or None,
        "elapsed": round(result.elapsed, 2),
        "analysis": to_dict(result.analysis) if result.analysis else None,
    }
    if args.raw:
        payload["raw_text"] = result.raw_text
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if result.ok else 1


def cmd_config(args) -> int:
    cfg = _config(args)
    print(f"config: {config_path()}")
    print(f"model: {cfg.model}")
    print(f"base_url: {cfg.base_url}")
    print(f"api_key: {'설정됨' if cfg.api_key else '없음'}")
    print(f"default_mode: {cfg.default_mode}")
    print(f"socket: {ipc.socket_path()}")
    return 0


def cmd_stop(_args) -> int:
    return 0 if ipc.send("quit") == "ok" else 1


HANDLERS = {
    None: cmd_run,
    "run": cmd_run,
    "capture": cmd_capture,
    "multi": cmd_multi,
    "analyze": cmd_analyze,
    "config": cmd_config,
    "stop": cmd_stop,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
