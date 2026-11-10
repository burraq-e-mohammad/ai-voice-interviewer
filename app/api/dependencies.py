"""FastAPI dependencies: shared singleton objects for AI services, pipeline, and rate limiting."""

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
    """Builds the full AI Voice Interview pipeline once and reuses it across requests."""
    settings = get_settings()

    provider = settings.llm_provider.lower()
    if provider == "gemini":
        api_key = settings.gemini_api_key.get_secret_value()
        model = settings.gemini_model
    else:
        api_key = settings.groq_api_key.get_secret_value()
        model = settings.groq_model

    return VoiceChatPipeline(
        stt=SpeechToText(
            model_size=settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        ),
        llm=LLMService(
            api_key=api_key,
            model=model,
            provider=provider,
            max_tokens=settings.llm_max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        tts=TextToSpeech(voice_path=settings.piper_voice_path),
        memory=ConversationMemory(
            max_turns=settings.max_interview_turns,
            max_sessions=settings.max_sessions,
        ),
        max_turns=settings.max_interview_turns,
    )


@lru_cache
def get_rate_limiter() -> RateLimiter:
    """Shared rate limiter instance."""
    settings = get_settings()
    return RateLimiter(
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )


def enforce_rate_limit(
    request: Request,
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> None:
    """Validates that the incoming client IP has not exceeded rate quotas."""
    client_ip = request.client.host if request.client else "unknown"
    limiter.check(client_ip)


def get_app_settings() -> Settings:
    """Settings accessor dependency."""
    return get_settings()
