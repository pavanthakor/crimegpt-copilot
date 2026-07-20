"""Application settings, loaded from backend/.env via pydantic-settings."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# core/config.py -> app -> backend/.env
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    DATABASE_URL: str
    JWT_SECRET: str
    OLLAMA_HOST: str = "http://localhost:11434"
    LLM_MODEL: str = "qwen2.5:7b"
    DEMO_MODE: bool = False
    FORCE_API: bool = False
    FALLBACK_API_KEY: str = ""

    # Voice input (CLAUDE.md §4). A faster-whisper model NAME ("small", "medium",
    # "large-v3") downloaded from the Systran hub, OR a path to a local CTranslate2
    # model directory (e.g. a converted Gujarati-tuned checkpoint). Switching this
    # is the only change needed to swap models — see app/ai/transcribe.py.
    WHISPER_MODEL: str = "small"


settings = Settings()
