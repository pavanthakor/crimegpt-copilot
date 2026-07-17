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


settings = Settings()
