"""Unit tests for the STT, LLM and TTS service wrappers.

Each service accepts an optional fake engine/client in its constructor, so we
test our wrapper logic (error handling, formatting, prompt assembly) offline.
"""

import io
import wave
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.errors import (
    InvalidAudioError,
    LLMServiceError,
    NoSpeechDetectedError,
    SpeechSynthesisError,
)
from app.models.schemas import CandidateProfile, Message
from app.services.llm import LLMService
from app.services.stt import SpeechToText
from app.services.tts import TextToSpeech

# --- Speech-to-Text -----------------------------------------------------------


class FakeWhisperModel:
    """Mimics faster_whisper.WhisperModel.transcribe(): returns (segments, info)."""

    def __init__(self, texts: list[str] | None = None, error: Exception | None = None) -> None:
        self.texts = texts or []
        self.error = error

    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[Any, None]:
        if self.error:
            raise self.error
        return (SimpleNamespace(text=t) for t in self.texts), None


def test_stt_joins_segments_into_one_string() -> None:
    stt = SpeechToText("base", model=FakeWhisperModel([" Hello", " world. "]))

    assert stt.transcribe(b"audio") == "Hello world."


def test_stt_raises_when_no_speech() -> None:
    stt = SpeechToText("base", model=FakeWhisperModel([]))

    with pytest.raises(NoSpeechDetectedError):
        stt.transcribe(b"audio")


def test_stt_wraps_decoding_errors() -> None:
    stt = SpeechToText("base", model=FakeWhisperModel(error=ValueError("corrupt file")))

    with pytest.raises(InvalidAudioError):
        stt.transcribe(b"not audio")


# --- LLM ----------------------------------------------------------------------


class FakeChatClient:
    """Mimics the OpenAI-compatible `client.chat.completions.create(...)` interface."""

    def __init__(self, reply: str | None = "Tell me about your architecture.", error: Exception | None = None) -> None:
        self.last_request: dict[str, Any] = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._reply = reply
        self._error = error

    def _create(self, **kwargs: Any) -> Any:
        self.last_request = kwargs
        if self._error:
            raise self._error
        message = SimpleNamespace(content=self._reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_llm(client: FakeChatClient) -> LLMService:
    return LLMService(api_key="x", model="test-model", provider="gemini", client=client)


def test_llm_sends_profile_history_and_candidate_answer() -> None:
    client = FakeChatClient()
    profile = CandidateProfile(name="Alex", position="Data Engineer", company="Stripe")
    history = [Message("assistant", "Welcome!"), Message("user", "Thanks")]

    reply = make_llm(client).generate_reply("I built ETL pipelines.", history=history, profile=profile)

    assert reply == "Tell me about your architecture."
    assert client.last_request["model"] == "test-model"
    messages = client.last_request["messages"]
    assert messages[0]["role"] == "system"
    assert "Stripe" in messages[0]["content"]
    assert messages[1:] == [
        {"role": "assistant", "content": "Welcome!"},
        {"role": "user", "content": "Thanks"},
        {"role": "user", "content": "I built ETL pipelines."},
    ]


def test_llm_wraps_api_errors_without_leaking_details() -> None:
    client = FakeChatClient(error=RuntimeError("401 invalid key secret_token_123"))

    with pytest.raises(LLMServiceError) as exc_info:
        make_llm(client).generate_reply("Hi")

    assert "secret_token_123" not in exc_info.value.message


def test_llm_strips_hidden_reasoning_and_markdown_symbols() -> None:
    client = FakeChatClient(reply="<think>\nReasoning...\n</think>\n\n**Great point.** How did you *scale* it?")

    assert make_llm(client).generate_reply("Scale?") == "Great point. How did you scale it?"


def test_llm_rejects_empty_reply() -> None:
    with pytest.raises(LLMServiceError):
        make_llm(FakeChatClient(reply="   ")).generate_reply("Hi")


def test_llm_opening_falls_back_gracefully_on_error() -> None:
    client = FakeChatClient(error=RuntimeError("network blip"))
    profile = CandidateProfile(name="Jordan", position="Backend Engineer", company="Linear")

    opening = make_llm(client).generate_opening_question(profile, max_turns=20)

    assert "Jordan" in opening
    assert "Linear" in opening


def test_llm_evaluate_extracts_numeric_score() -> None:
    client = FakeChatClient(reply="## Candidate Score: 9.2/10\n\nExcellent clarity.")
    profile = CandidateProfile(name="Jordan", position="Backend Engineer", company="Linear")

    score, report = make_llm(client).evaluate_interview(profile, [Message("user", "My answer")])

    assert score == "9.2/10"
    assert "Excellent clarity." in report


# --- Text-to-Speech -----------------------------------------------------------


class FakePiperVoice:
    """Mimics piper.PiperVoice.synthesize_wav(): writes 0.1s of silence."""

    def __init__(self) -> None:
        self.spoken_texts: list[str] = []

    def synthesize_wav(self, text: str, wav_file: wave.Wave_write) -> None:
        self.spoken_texts.append(text)
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x00" * 2205)


def test_tts_returns_a_valid_wav_file() -> None:
    tts = TextToSpeech("unused.onnx", voice=FakePiperVoice())

    audio = tts.synthesize("Hello there")

    with wave.open(io.BytesIO(audio), "rb") as wav_file:
        assert wav_file.getframerate() == 22050
        assert wav_file.getnframes() == 2205


def test_tts_normalizes_markdown_and_punctuation() -> None:
    fake_voice = FakePiperVoice()
    tts = TextToSpeech("unused.onnx", voice=fake_voice)

    tts.synthesize("**Hello** — it’s `ready`!")

    assert fake_voice.spoken_texts == ["Hello , it's ready!"]


def test_tts_rejects_empty_text() -> None:
    tts = TextToSpeech("unused.onnx", voice=FakePiperVoice())

    with pytest.raises(SpeechSynthesisError):
        tts.synthesize("   ")


def test_tts_missing_voice_file_gives_helpful_error() -> None:
    with pytest.raises(FileNotFoundError, match="download_voice"):
        TextToSpeech("models/does-not-exist.onnx")

