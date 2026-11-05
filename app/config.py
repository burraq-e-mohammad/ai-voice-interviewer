"""Application configuration.

All settings are read from environment variables (or a `.env` file).
Keeping configuration in one place means:
  * no secrets are hard-coded in the source code, and
  * you can change behaviour (model size, limits, ...) without editing code.
"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings. Pydantic validates every value when the app starts,
    so a typo like RATE_LIMIT_REQUESTS=abc fails fast with a clear error."""

    # Tell pydantic-settings to also read a local `.env` file.
    # `extra="ignore"` means unrelated variables in .env do not cause errors.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM (Groq) -------------------------------------------------------
    # SecretStr hides the key when settings are printed or logged.
    groq_api_key: SecretStr
    groq_model: str = "qwen/qwen3.8-27b"
    llm_max_tokens: int = Field(default=300, ge=16, le=2048)
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    system_prompt: str = (
        "You are a friendly voice assistant. Your answers are spoken out loud, "
        "so reply in short, plain sentences (2-4 sentences). "
        "Do not use markdown, lists, emojis or code blocks."
    )

    # --- Speech-to-Text (faster-whisper) ----------------------------------
    # Model sizes: tiny, base, small, medium, large-v3. Bigger = more accurate but slower.
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"  # "cuda" if you have an NVIDIA GPU
    whisper_compute_type: str = "int8"  # int8 is fast and light on CPU

    # --- Text-to-Speech (Piper) -------------------------------------------
    piper_voice_path: str = "models/en_US-lessac-medium.onnx"

    # --- Security & limits ------------------------------------------------
    max_audio_bytes: int = Field(default=10 * 1024 * 1024, gt=0)  # 10 MB
    rate_limit_requests: int = Field(default=10, gt=0)
    rate_limit_window_seconds: int = Field(default=60, gt=0)
    # Browser origins allowed to call the API (the demo web client runs on port 5500).
    cors_origins: list[str] = ["http://localhost:5500", "http://127.0.0.1:5500"]
    # Show the interactive Swagger page at /docs. Turn off in production.
    enable_docs: bool = True

    # --- Conversation memory ----------------------------------------------
    # How many past (user + assistant) exchanges to remember per session.
    max_history_turns: int = Field(default=5, ge=0, le=20)
    # Upper bound on sessions kept in RAM, so memory cannot grow forever.
    max_sessions: int = Field(default=1000, gt=0)


@lru_cache
def get_settings() -> Settings:
    """Return the settings object.

    `lru_cache` makes this a singleton: the environment is read only once,
    and every caller gets the same object.
    """
    # pydantic fills the required fields from the environment, which mypy cannot see.
    return Settings()  # type: ignore[call-arg]
