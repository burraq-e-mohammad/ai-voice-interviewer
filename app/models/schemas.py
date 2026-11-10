"""Data shapes used across the AI Voice Interviewer application."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    """One message in a conversation. `frozen=True` makes it read-only."""

    role: Role
    content: str

    def to_dict(self) -> dict[str, str]:
        """Convert to the standard dict format accepted by LLM chat APIs."""
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ChatResult:
    """Everything the pipeline produced for one voice turn."""

    transcript: str  # what the candidate said (STT output)
    reply_text: str  # what the interviewer replied (LLM output)
    reply_audio: bytes  # the spoken response as WAV audio (TTS output)
    turn: int = 1
    max_turns: int = 20
    is_complete: bool = False


class CandidateProfile(BaseModel):
    """Candidate background, target role specifications, job description, and parsed resume."""

    name: str = Field(default="Candidate", max_length=150)
    level: str = Field(default="Senior", max_length=100)
    position: str = Field(default="Software Engineer", max_length=200)
    company: str = Field(default="Google", max_length=200)
    job_description: str = Field(default="", max_length=40000)
    resume_text: str = Field(default="", max_length=40000)
    experience: str = Field(default="", max_length=10000)
    skills: str = Field(default="", max_length=10000)


class ParseResumeResponse(BaseModel):
    """Extracted text and summary statistics from an uploaded resume file."""

    filename: str
    resume_text: str
    char_count: int
    word_count: int


class StartInterviewRequest(BaseModel):
    """Payload to initiate an interview session with candidate profile."""

    profile: CandidateProfile


class StartInterviewResponse(BaseModel):
    """Initial session response with opening question and spoken greeting."""

    session_id: str
    opening_text: str
    opening_audio_base64: str
    turn: int
    max_turns: int


class EvaluationRequest(BaseModel):
    """Payload to request performance evaluation for a completed session."""

    session_id: str = Field(min_length=1, max_length=64)


class EvaluationResponse(BaseModel):
    """Full candidate performance critique and quantitative score."""

    session_id: str
    score: str
    feedback_markdown: str
    candidate_name: str
    position: str
    company: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
