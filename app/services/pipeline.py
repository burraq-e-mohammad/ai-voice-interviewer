"""The voice chat pipeline: audio in -> text -> answer -> audio out.

This is the heart of the app. It only *orchestrates* the three services;
it does not know how Whisper, Groq or Piper work internally.

Why Protocols?
  A `Protocol` describes what methods an object must have ("anything with a
  `transcribe(bytes) -> str` method is a SpeechToTextEngine"). The pipeline
  depends on these descriptions, not on the concrete classes. That means:
    * tests can plug in tiny fake services (fast, no models, no internet), and
    * you could swap Piper for another TTS without touching this file.
"""

import logging
import time
from typing import Protocol

from app.models.schemas import ChatResult, Message
from app.services.memory import ConversationMemory

logger = logging.getLogger(__name__)


class SpeechToTextEngine(Protocol):
    def transcribe(self, audio_bytes: bytes) -> str: ...


class ReplyGenerator(Protocol):
    def generate_reply(self, user_text: str, history: list[Message] | None = None) -> str: ...


class TextToSpeechEngine(Protocol):
    def synthesize(self, text: str) -> bytes: ...


class VoiceChatPipeline:
    def __init__(
        self,
        stt: SpeechToTextEngine,
        llm: ReplyGenerator,
        tts: TextToSpeechEngine,
        memory: ConversationMemory,
    ) -> None:
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._memory = memory

    def run(self, audio_bytes: bytes, session_id: str | None = None) -> ChatResult:
        """Run all three steps for one request.

        This function is *blocking* (the AI models use the CPU for seconds),
        so the API layer runs it in a worker thread to keep the server responsive.

        Any step can raise a VoiceBotError; we let it bubble up to the central
        error handler instead of catching it here.
        """
        started = time.perf_counter()

        # Step 1: Speech-to-Text - what did the user say?
        transcript = self._stt.transcribe(audio_bytes)
        logger.info("STT done (%.2fs)", time.perf_counter() - started)

        # Step 2: LLM - what should we answer? Include earlier messages if we have a session.
        history = self._memory.get_history(session_id) if session_id else []
        reply_text = self._llm.generate_reply(transcript, history)
        logger.info("LLM done (%.2fs)", time.perf_counter() - started)

        # Step 3: Text-to-Speech - turn the answer into audio.
        reply_audio = self._tts.synthesize(reply_text)
        logger.info("TTS done (%.2fs total)", time.perf_counter() - started)

        # Only remember the exchange once every step succeeded.
        if session_id:
            self._memory.add_exchange(session_id, transcript, reply_text)

        return ChatResult(transcript=transcript, reply_text=reply_text, reply_audio=reply_audio)
