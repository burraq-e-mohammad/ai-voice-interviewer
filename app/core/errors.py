"""Custom exceptions for the voice chatbot.

Why custom exceptions?
  Each service raises an error that *describes the problem* (e.g. "the LLM is
  down"). One central handler in `app/main.py` turns these into consistent
  JSON responses with the right HTTP status code. The services never need to
  know anything about HTTP.
"""


class VoiceBotError(Exception):
    """Base class for every expected error in this app."""

    # Defaults; subclasses override them.
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        # This message is shown to the API user, so it must never contain secrets.
        self.message = message


# --- Errors caused by the client's input (4xx) ------------------------------


class InvalidAudioError(VoiceBotError):
    """The uploaded file is empty or cannot be decoded as audio."""

    status_code = 400
    code = "invalid_audio"


class AudioTooLargeError(VoiceBotError):
    """The uploaded file is bigger than MAX_AUDIO_BYTES."""

    status_code = 413
    code = "audio_too_large"


class UnsupportedAudioTypeError(VoiceBotError):
    """The file's content type is not in our allow-list."""

    status_code = 415
    code = "unsupported_media_type"


class NoSpeechDetectedError(VoiceBotError):
    """The audio was valid, but nobody said anything we could understand."""

    status_code = 422
    code = "no_speech_detected"


class RateLimitExceededError(VoiceBotError):
    """The client sent too many requests in the current time window."""

    status_code = 429
    code = "rate_limit_exceeded"

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


# --- Errors caused by our services (5xx) ------------------------------------


class LLMServiceError(VoiceBotError):
    """Groq could not produce a reply (network issue, bad key, quota, ...)."""

    status_code = 502  # "Bad Gateway": an upstream service failed
    code = "llm_unavailable"


class SpeechSynthesisError(VoiceBotError):
    """Piper could not turn the reply text into audio."""

    status_code = 500
    code = "speech_synthesis_failed"
