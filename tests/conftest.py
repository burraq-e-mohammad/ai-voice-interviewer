"""Shared test setup (pytest loads this file automatically).

Key idea: tests never load the real AI models or call the real Groq API.
We replace them with tiny *fakes* that return predictable answers. This
makes the tests fast (milliseconds), free, and runnable without internet.
"""

import os

# Settings require a Groq key. Set a dummy one BEFORE the app is imported,
# because the app reads its settings while being imported.
os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")

from collections.abc import Iterator  # noqa: E402  (must come after the env setup)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.dependencies import get_pipeline, get_rate_limiter  # noqa: E402
from app.core.rate_limit import RateLimiter  # noqa: E402
from app.main import app  # noqa: E402
from app.models.schemas import Message  # noqa: E402
from app.services.memory import ConversationMemory  # noqa: E402
from app.services.pipeline import VoiceChatPipeline  # noqa: E402

# A tiny but valid-looking payload. Fakes never decode it, so its content does not matter.
FAKE_AUDIO = b"RIFF fake wav data"
FAKE_REPLY_AUDIO = b"RIFF fake reply audio"


class FakeSTT:
    def __init__(self, text: str = "Hello bot") -> None:
        self.text = text
        self.calls: list[bytes] = []

    def transcribe(self, audio_bytes: bytes) -> str:
        self.calls.append(audio_bytes)
        return self.text


class FakeLLM:
    def __init__(self, reply: str = "Hello human") -> None:
        self.reply = reply
        # Record what we were asked, so tests can check the history was passed in.
        self.calls: list[tuple[str, list[Message]]] = []

    def generate_reply(self, user_text: str, history: list[Message] | None = None) -> str:
        self.calls.append((user_text, list(history or [])))
        return self.reply


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
        memory=ConversationMemory(max_turns=5, max_sessions=100),
    )


@pytest.fixture
def client(pipeline: VoiceChatPipeline) -> Iterator[TestClient]:
    """A test client whose app uses the fake pipeline and a fresh rate limiter."""
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(100, 60)
    # raise_server_exceptions=False lets us test our 500 error handler.
    yield TestClient(app, raise_server_exceptions=False)
    # Clean up so overrides never leak into other tests.
    app.dependency_overrides.clear()
