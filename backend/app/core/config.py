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

    # Voice input (CLAUDE.md §4). WHISPER_MODEL is the general model — a faster-whisper
    # size/hub name ("small", "medium") or a local CTranslate2 path — used for the
    # English narrative (translate task) and for non-Gujarati transcription.
    WHISPER_MODEL: str = "small"
    # Optional Gujarati-specialised model for the Gujarati DISPLAY transcript only: a
    # local CT2 path, or a name resolved under storage/whisper/. When present the
    # transcribe endpoint runs a dual-model path (Gujarati transcript from this model,
    # English narrative from WHISPER_MODEL). Empty or missing -> falls back to
    # WHISPER_MODEL for Gujarati too. See app/ai/transcribe.py.
    WHISPER_MODEL_GU: str = "gujarati-medium-ct2"


settings = Settings()
