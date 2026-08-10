"""User configuration for blankfloat."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

# Gemini via OpenAI-compatible endpoint (vision + free tier for Lite).
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_MODEL = "gemini-3.5-flash-lite"

MODES = ("auto", "simple", "complex")

_API_KEY_ENV = (
    "BLANKFLOAT_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "ZHIPU_API_KEY",
    "GLM_API_KEY",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "blankfloat"


def config_path() -> Path:
    return config_dir() / "config.json"


def load_dotenv(path: Path | None = None) -> Path | None:
    """Load KEY=VALUE pairs from a .env file into os.environ.

    Existing environment variables win. Looks at ``path``, then cwd/.env,
    then the repo-root .env. Returns the file that was loaded, if any.
    """
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path)
    candidates.append(Path.cwd() / ".env")
    root_env = repo_root() / ".env"
    if root_env not in candidates:
        candidates.append(root_env)

    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ[key] = value
        return candidate
    return None


@dataclass
class Config:
    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: float = 90.0
    default_mode: str = "auto"

    # Image payload sent to the model.
    max_image_px: int = 1600
    # Gemini OpenAI-compat wants data URLs; Z.AI often accepts bare base64.
    image_payload: str = "data_url"  # "data_url" or "base64"

    # Local guard thresholds, see docs/ROUTING.md.
    low_confidence: float = 0.45
    promote_chars: int = 200

    # UI
    window_width: int = 460
    window_height: int = 580
    opacity: float = 0.97

    @classmethod
    def load(cls) -> "Config":
        load_dotenv()
        cfg = cls()
        path = config_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            known = {f.name for f in fields(cls)}
            for key, value in data.items():
                if key in known and value is not None:
                    setattr(cfg, key, value)

        for env_key in _API_KEY_ENV:
            value = os.environ.get(env_key)
            if value:
                cfg.api_key = value.strip()
                break
        if os.environ.get("BLANKFLOAT_MODEL"):
            cfg.model = os.environ["BLANKFLOAT_MODEL"]
        if os.environ.get("BLANKFLOAT_BASE_URL"):
            cfg.base_url = os.environ["BLANKFLOAT_BASE_URL"]

        if cfg.default_mode not in MODES:
            cfg.default_mode = "auto"
        return cfg

    def save(self) -> Path:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        path.chmod(0o600)
        return path
