"""The voice interview pipeline: candidate voice in -> STT -> LLM Interviewer -> TTS voice out."""

import logging
import time
from typing import Protocol

from app.models.schemas import CandidateProfile, ChatResult, Message
from app.services.memory import ConversationMemory

logger = logging.getLogger(__name__)


class SpeechToTextEngine(Protocol):
    def transcribe(self, audio_bytes: bytes) -> str: ...


class InterviewReplyGenerator(Protocol):
    def generate_opening_question(self, profile: CandidateProfile, max_turns: int) -> str: ...

    def generate_reply(
        self,
        user_text: str,
        history: list[Message] | None = None,
        profile: CandidateProfile | None = None,
        turn: int = 1,
        max_turns: int = 20,
    ) -> str: ...

    def evaluate_interview(self, profile: CandidateProfile, history: list[Message]) -> tuple[str, str]: ...


class TextToSpeechEngine(Protocol):
    def synthesize(self, text: str) -> bytes: ...


class VoiceChatPipeline:
    """Orchestrates candidate speech transcription, Gemini interviewer logic, and Piper audio synthesis."""

    def __init__(
        self,
        stt: SpeechToTextEngine,
        llm: InterviewReplyGenerator,
        tts: TextToSpeechEngine,
        memory: ConversationMemory,
        max_turns: int = 20,
    ) -> None:
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._memory = memory
        self._max_turns = max_turns

    def start_interview(self, session_id: str, profile: CandidateProfile) -> tuple[str, bytes]:
        """Sets up a candidate session and generates the initial verbal greeting & question."""
        self._memory.start_session(session_id, profile)

        # Generate personalized opening question
        opening_text = self._llm.generate_opening_question(profile, max_turns=self._max_turns)

        # Synthesize spoken audio for the opening greeting
        opening_audio = self._tts.synthesize(opening_text)

        # Record opening in history so the model remembers what it asked
        self._memory.record_interviewer_opening(session_id, opening_text)
        return opening_text, opening_audio

    def run(self, audio_bytes: bytes, session_id: str) -> ChatResult:
        """Processes one candidate spoken turn: transcribe, advance interview, and speak reply."""
        started = time.perf_counter()

        # Step 1: Transcribe candidate's speech
        transcript = self._stt.transcribe(audio_bytes)
        logger.info("STT transcribed: '%s' (%.2fs)", transcript[:60], time.perf_counter() - started)

        # Step 2: Retrieve profile, turn, and past dialogue
        profile = self._memory.get_profile(session_id)
        current_turn = self._memory.get_turn(session_id)
        history = self._memory.get_history(session_id)

        # Step 3: Generate next question from AI interviewer
        reply_text = self._llm.generate_reply(
            user_text=transcript,
            history=history,
            profile=profile,
            turn=current_turn,
            max_turns=self._max_turns,
        )
        logger.info("Interviewer generated reply (%.2fs)", time.perf_counter() - started)

        # Step 4: Synthesize spoken response audio
        reply_audio = self._tts.synthesize(reply_text)
        logger.info("TTS synthesized audio (%.2fs total)", time.perf_counter() - started)

        # Step 5: Advance interview turn in memory
        new_turn, is_complete = self._memory.record_exchange(session_id, transcript, reply_text)

        return ChatResult(
            transcript=transcript,
            reply_text=reply_text,
            reply_audio=reply_audio,
            turn=new_turn,
            max_turns=self._max_turns,
            is_complete=is_complete,
        )

    def evaluate(self, session_id: str) -> tuple[str, str, CandidateProfile]:
        """Generates performance evaluation report from full interview history."""
        profile = self._memory.get_profile(session_id)
        history = self._memory.get_history(session_id)
        score, report = self._llm.evaluate_interview(profile, history)
        return score, report, profile
