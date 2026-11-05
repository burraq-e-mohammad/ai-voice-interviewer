"""FastAPI dependencies: shared objects that endpoints receive via `Depends()`.

Why dependencies?
  * The heavy objects (AI models) are created ONCE and reused (`lru_cache`).
  * Tests can replace any of them with `app.dependency_overrides[...]`, so
    the test suite never loads real models or calls the real Groq API.

Models are loaded lazily - on the first /chat request, not at startup. This
keeps startup instant and the tests light. The trade-off: the very first
request is slower (and on first run, the Whisper model is downloaded).
"""

from functools import lru_cache

from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.core.rate_limit import RateLimiter
from app.services.llm import LLMService
from app.services.memory import ConversationMemory
from app.services.pipeline import VoiceChatPipeline
from app.services.stt import SpeechToText
from app.services.tts import TextToSpeech


@lru_cache
def get_pipeline() -> VoiceChatPipeline:
    """Build the full pipeline once and reuse it for every request."""
    settings = get_settings()
    return VoiceChatPipeline(
        stt=SpeechToText(
            model_size=settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        ),
        llm=LLMService(
            # get_secret_value() is the only place the real key is read.
            api_key=settings.groq_api_key.get_secret_value(),
            model=settings.groq_model,
            system_prompt=settings.system_prompt,
            max_tokens=settings.llm_max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        tts=TextToSpeech(voice_path=settings.piper_voice_path),
        memory=ConversationMemory(
            max_turns=settings.max_history_turns,
            max_sessions=settings.max_sessions,
        ),
    )


@lru_cache
def get_rate_limiter() -> RateLimiter:
    """One shared rate limiter for the whole app."""
    settings = get_settings()
    return RateLimiter(
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )


def enforce_rate_limit(
    request: Request,
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> None:
    """Runs before the endpoint; raises RateLimitExceededError if over the limit."""
    # We identify clients by IP address. (Behind a reverse proxy you would read
    # the X-Forwarded-For header instead - see docs/SECURITY.md.)
    client_ip = request.client.host if request.client else "unknown"
    limiter.check(client_ip)


def get_app_settings() -> Settings:
    """Wrapper so endpoints can depend on settings (and tests can override them)."""
    return get_settings()
