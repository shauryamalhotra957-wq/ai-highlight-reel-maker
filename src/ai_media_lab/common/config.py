from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_local_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(project_root() / ".env", override=False)
    except Exception:
        return


def project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return current.parents[3]


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppSettings:
    data_dir: Path
    openai_api_key: str | None
    transcribe_model: str
    text_model: str
    force_demo: bool

    @property
    def openai_enabled(self) -> bool:
        return bool(self.openai_api_key) and not self.force_demo


def get_settings() -> AppSettings:
    load_local_env()
    root = project_root()
    configured_data_dir = os.getenv("AI_MEDIA_DATA_DIR")
    data_dir = Path(configured_data_dir).expanduser() if configured_data_dir else root / "var"
    return AppSettings(
        data_dir=data_dir,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        transcribe_model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1"),
        text_model=os.getenv("OPENAI_TEXT_MODEL", "gpt-5.6"),
        force_demo=env_flag("AI_MEDIA_FORCE_DEMO", False),
    )


def service_path(service: str, *parts: str) -> Path:
    path = get_settings().data_dir / service
    for part in parts:
        path = path / part
    path.mkdir(parents=True, exist_ok=True)
    return path
