"""Application configuration for AI Voice Interviewer."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Typed application settings read from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM Providers -----------------------------------------------------
    llm_provider: str = Field(default="gemini", description="LLM backend: 'gemini' or 'groq'")
    gemini_api_key: SecretStr = Field(default=SecretStr(""))
    gemini_model: str = Field(default="gemini-3.5-flash-lite")

    groq_api_key: SecretStr = Field(default=SecretStr(""))
    groq_model: str = Field(default="qwen/qwen3.8-27b")

    llm_max_tokens: int = Field(default=350, ge=32, le=2048)
    llm_timeout_seconds: float = Field(default=30.0, gt=0)

    # --- Interview Session Parameters --------------------------------------
    max_interview_turns: int = Field(default=20, ge=1, le=50)

    # --- Speech-to-Text (faster-whisper) ----------------------------------
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # --- Text-to-Speech (Piper) -------------------------------------------
    piper_voice_path: str = str(PROJECT_ROOT / "models" / "en_US-lessac-medium.onnx")

    # --- Security & Limits ------------------------------------------------
    max_audio_bytes: int = Field(default=15 * 1024 * 1024, gt=0)  # 15 MB
    rate_limit_requests: int = Field(default=30, gt=0)
    rate_limit_window_seconds: int = Field(default=60, gt=0)
    cors_origins: list[str] = [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*",
    ]
    enable_docs: bool = True

    # --- Session Storage --------------------------------------------------
    max_sessions: int = Field(default=1000, gt=0)


@lru_cache
def get_settings() -> Settings:
    """Singleton getter for application settings."""
    return Settings()
