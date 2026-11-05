"""Data shapes used across the app.

Keeping these in one file gives every layer a shared, typed vocabulary.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

# A chat message as Groq (and most LLM APIs) expect it.
Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    """One message in a conversation. `frozen=True` makes it read-only."""

    role: Role
    content: str

    def to_dict(self) -> dict[str, str]:
        """Convert to the plain dict format the Groq SDK accepts."""
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ChatResult:
    """Everything the pipeline produced for one request."""

    transcript: str  # what the user said (STT output)
    reply_text: str  # what the bot answered (LLM output)
    reply_audio: bytes  # the answer as WAV audio (TTS output)


# --- API response models ---------------------------------------------------
# These are only used for error responses (success returns raw audio), but
# declaring them lets FastAPI show the error format in the /docs page.


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
