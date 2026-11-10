"""Unit tests for the interview pipeline orchestration."""

import pytest

from app.core.errors import LLMServiceError
from app.models.schemas import CandidateProfile, Message
from app.services.memory import ConversationMemory
from app.services.pipeline import VoiceChatPipeline
from tests.conftest import FAKE_AUDIO, FAKE_REPLY_AUDIO, FakeLLM, FakeSTT, FakeTTS


def test_start_interview_records_opening_question(
    pipeline: VoiceChatPipeline, fake_llm: FakeLLM
) -> None:
    profile = CandidateProfile(name="Sam", company="Acme")

    opening_text, opening_audio = pipeline.start_interview("sess-1", profile)

    assert opening_text == fake_llm.opening
    assert opening_audio == FAKE_REPLY_AUDIO
    assert fake_llm.opening_calls == [(profile, 20)]


def test_run_processes_turn_and_updates_memory(
    pipeline: VoiceChatPipeline, fake_stt: FakeSTT, fake_llm: FakeLLM
) -> None:
    profile = CandidateProfile(name="Sam", position="ML Engineer", company="Acme")
    pipeline.start_interview("sess-1", profile)

    result = pipeline.run(FAKE_AUDIO, session_id="sess-1")

    assert fake_stt.calls == [FAKE_AUDIO]
    user_text, history, passed_profile, turn, max_turns = fake_llm.calls[0]
    assert user_text == "Hello interviewer"
    assert history == [Message(role="assistant", content=fake_llm.opening)]
    assert passed_profile == profile
    assert turn == 1
    assert max_turns == 20
    assert result.reply_audio == FAKE_REPLY_AUDIO
    assert result.turn == 2
    assert result.is_complete is False


def test_evaluate_returns_score_report_and_profile(
    pipeline: VoiceChatPipeline, fake_llm: FakeLLM
) -> None:
    profile = CandidateProfile(name="Sam", company="Acme")
    pipeline.start_interview("sess-1", profile)
    pipeline.run(FAKE_AUDIO, session_id="sess-1")

    score, report, returned_profile = pipeline.evaluate("sess-1")

    assert score == fake_llm.score
    assert report == fake_llm.report
    assert returned_profile == profile
    assert len(fake_llm.evaluate_calls[0][1]) == 3


class BrokenLLM(FakeLLM):
    def generate_reply(
        self,
        user_text: str,
        history: list[Message] | None = None,
        profile: CandidateProfile | None = None,
        turn: int = 1,
        max_turns: int = 20,
    ) -> str:
        raise LLMServiceError("down")


def test_errors_propagate_and_exchange_is_not_saved() -> None:
    memory = ConversationMemory(max_turns=20, max_sessions=10)
    pipeline = VoiceChatPipeline(FakeSTT(), BrokenLLM(), FakeTTS(), memory)

    with pytest.raises(LLMServiceError):
        pipeline.run(FAKE_AUDIO, session_id="s1")

    assert memory.get_history("s1") == []

