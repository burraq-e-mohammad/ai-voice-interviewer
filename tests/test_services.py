"""Unit tests for the STT, LLM and TTS service wrappers.

Each service accepts an optional fake engine/client in its constructor, so we
can test OUR code (error handling, message building) without the real models.
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
from app.models.schemas import Message
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


class FakeGroqClient:
    """Mimics the shape `client.chat.completions.create(...)` of the Groq SDK."""

    def __init__(self, reply: str | None = "Hi!", error: Exception | None = None) -> None:
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


def make_llm(client: FakeGroqClient) -> LLMService:
    return LLMService(api_key="x", model="test-model", system_prompt="Be brief.", client=client)


def test_llm_sends_system_prompt_history_and_question() -> None:
    client = FakeGroqClient()
    history = [Message("user", "Hi"), Message("assistant", "Hello")]

    reply = make_llm(client).generate_reply("How are you?", history)

    assert reply == "Hi!"
    assert client.last_request["model"] == "test-model"
    assert client.last_request["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "How are you?"},
    ]


def test_llm_wraps_api_errors_without_leaking_details() -> None:
    client = FakeGroqClient(error=RuntimeError("401 invalid key gsk_secret"))

    with pytest.raises(LLMServiceError) as exc_info:
        make_llm(client).generate_reply("Hi")

    assert "gsk_secret" not in exc_info.value.message


def test_llm_removes_hidden_reasoning_from_reply() -> None:
    client = FakeGroqClient(reply="<think>\nThe user wants...\n</think>\n\nParis is the capital.")

    assert make_llm(client).generate_reply("Capital of France?") == "Paris is the capital."


def test_llm_rejects_empty_reply() -> None:
    with pytest.raises(LLMServiceError):
        make_llm(FakeGroqClient(reply="   ")).generate_reply("Hi")


# --- Text-to-Speech -----------------------------------------------------------


class FakePiperVoice:
    """Mimics piper.PiperVoice.synthesize_wav(): writes 0.1s of silence."""

    def synthesize_wav(self, text: str, wav_file: wave.Wave_write) -> None:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x00" * 2205)


def test_tts_returns_a_valid_wav_file() -> None:
    tts = TextToSpeech("unused.onnx", voice=FakePiperVoice())

    audio = tts.synthesize("Hello there")

    # Re-open the bytes as a WAV file to prove they are well-formed.
    with wave.open(io.BytesIO(audio), "rb") as wav_file:
        assert wav_file.getframerate() == 22050
        assert wav_file.getnframes() == 2205


def test_tts_rejects_empty_text() -> None:
    tts = TextToSpeech("unused.onnx", voice=FakePiperVoice())

    with pytest.raises(SpeechSynthesisError):
        tts.synthesize("   ")


def test_tts_missing_voice_file_gives_helpful_error() -> None:
    with pytest.raises(FileNotFoundError, match="download_voice"):
        TextToSpeech("models/does-not-exist.onnx")
