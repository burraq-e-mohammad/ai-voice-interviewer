"""Shared test setup (pytest loads this file automatically).

Tests replace the real Whisper, Gemini/Groq, and Piper engines with tiny fakes
so the full suite runs offline in milliseconds.
"""

import os
from collections.abc import Iterator

os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_pipeline, get_rate_limiter
from app.core.rate_limit import RateLimiter
from app.main import app
from app.models.schemas import CandidateProfile, Message
from app.services.memory import ConversationMemory
from app.services.pipeline import VoiceChatPipeline

FAKE_AUDIO = b"RIFF fake wav data"
FAKE_REPLY_AUDIO = b"RIFF fake reply audio"


class FakeSTT:
    def __init__(self, text: str = "Hello interviewer") -> None:
        self.text = text
        self.calls: list[bytes] = []

    def transcribe(self, audio_bytes: bytes) -> str:
        self.calls.append(audio_bytes)
        return self.text


class FakeLLM:
    def __init__(
        self,
        opening: str = "Welcome! Tell me about yourself.",
        reply: str = "Can you walk through that system's scaling bottlenecks?",
        score: str = "8.5/10",
        report: str = "## Candidate Score: 8.5/10\nStrong system design.",
    ) -> None:
        self.opening = opening
        self.reply = reply
        self.score = score
        self.report = report
        self.opening_calls: list[tuple[CandidateProfile, int]] = []
        self.calls: list[tuple[str, list[Message], CandidateProfile | None, int, int]] = []
        self.evaluate_calls: list[tuple[CandidateProfile, list[Message]]] = []

    def generate_opening_question(self, profile: CandidateProfile, max_turns: int) -> str:
        self.opening_calls.append((profile, max_turns))
        return self.opening

    def generate_reply(
        self,
        user_text: str,
        history: list[Message] | None = None,
        profile: CandidateProfile | None = None,
        turn: int = 1,
        max_turns: int = 20,
    ) -> str:
        self.calls.append((user_text, list(history or []), profile, turn, max_turns))
        return self.reply

    def evaluate_interview(
        self, profile: CandidateProfile, history: list[Message]
    ) -> tuple[str, str]:
        self.evaluate_calls.append((profile, list(history)))
        return self.score, self.report


class FakeTTS:
    def synthesize(self, text: str) -> bytes:
        return FAKE_REPLY_AUDIO


@pytest.fixture
def fake_stt() -> FakeSTT:
    return FakeSTT()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def pipeline(fake_stt: FakeSTT, fake_llm: FakeLLM) -> VoiceChatPipeline:
    return VoiceChatPipeline(
        stt=fake_stt,
        llm=fake_llm,
        tts=FakeTTS(),
        memory=ConversationMemory(max_turns=20, max_sessions=100),
        max_turns=20,
    )


@pytest.fixture
def client(pipeline: VoiceChatPipeline) -> Iterator[TestClient]:
    """A test client whose app uses the fake pipeline and a fresh rate limiter."""
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(100, 60)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()

