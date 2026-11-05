"""Unit tests for the STT -> LLM -> TTS orchestration."""

import pytest

from app.core.errors import LLMServiceError
from app.models.schemas import Message
from app.services.memory import ConversationMemory
from app.services.pipeline import VoiceChatPipeline
from tests.conftest import FAKE_AUDIO, FAKE_REPLY_AUDIO, FakeLLM, FakeSTT, FakeTTS


def test_runs_all_three_steps_in_order(
    pipeline: VoiceChatPipeline, fake_stt: FakeSTT, fake_llm: FakeLLM
) -> None:
    result = pipeline.run(FAKE_AUDIO)

    assert fake_stt.calls == [FAKE_AUDIO]  # STT received the audio
    assert fake_llm.calls[0][0] == "Hello bot"  # LLM received the transcript
    assert result.transcript == "Hello bot"
    assert result.reply_text == "Hello human"
    assert result.reply_audio == FAKE_REPLY_AUDIO  # TTS output is returned


def test_saves_exchange_to_memory_when_session_given() -> None:
    memory = ConversationMemory(max_turns=5, max_sessions=10)
    pipeline = VoiceChatPipeline(FakeSTT(), FakeLLM(), FakeTTS(), memory)

    pipeline.run(FAKE_AUDIO, session_id="s1")

    assert memory.get_history("s1") == [
        Message(role="user", content="Hello bot"),
        Message(role="assistant", content="Hello human"),
    ]


class BrokenLLM:
    def generate_reply(self, user_text: str, history: list[Message] | None = None) -> str:
        raise LLMServiceError("down")


def test_errors_propagate_and_nothing_is_saved_to_memory() -> None:
    memory = ConversationMemory(max_turns=5, max_sessions=10)
    pipeline = VoiceChatPipeline(FakeSTT(), BrokenLLM(), FakeTTS(), memory)

    with pytest.raises(LLMServiceError):
        pipeline.run(FAKE_AUDIO, session_id="s1")

    assert memory.get_history("s1") == []
