"""Speech-to-Text using faster-whisper.

Why faster-whisper?
  * It is OpenAI's open-source Whisper model (MIT licence) running on
    CTranslate2, which makes it up to ~4x faster than the original and lets
    it run well on a normal laptop CPU.
  * It decodes almost any audio format (wav, mp3, webm, ogg, ...) through the
    bundled FFmpeg libraries, so the browser recording can be sent as-is.
  * The model downloads automatically the first time it is used.
"""

import io
import logging
from typing import Any

from app.core.errors import InvalidAudioError, NoSpeechDetectedError

logger = logging.getLogger(__name__)


class SpeechToText:
    def __init__(
        self,
        model_size: str,
        device: str = "cpu",
        compute_type: str = "int8",
        model: Any | None = None,
    ) -> None:
        """Load the Whisper model.

        Loading takes a few seconds, so this object is created once and reused
        for every request (see `app/api/dependencies.py`).

        `model` lets tests pass in a fake model instead of loading a real one.
        """
        if model is None:
            # Imported here, not at the top of the file, so that tests (which
            # use a fake model) do not need to load this heavy library.
            from faster_whisper import WhisperModel

            logger.info("Loading Whisper model '%s' on %s...", model_size, device)
            model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._model = model

    def transcribe(self, audio_bytes: bytes) -> str:
        """Turn recorded speech into text.

        Raises:
            InvalidAudioError: the bytes could not be decoded as audio.
            NoSpeechDetectedError: the audio contained no recognisable speech.
        """
        try:
            # vad_filter=True: a Voice Activity Detector skips silent parts,
            # which is faster and stops Whisper "hallucinating" words in silence.
            # beam_size=1 (greedy decoding) is fastest; accuracy is fine for chat.
            segments, _info = self._model.transcribe(
                io.BytesIO(audio_bytes), beam_size=1, vad_filter=True
            )
            # `segments` is a lazy generator - the real work happens while we
            # loop over it, so this loop must also be inside the try block.
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            # Log the technical details for us, show a friendly message to the user.
            logger.warning("Audio decoding/transcription failed: %s", exc)
            raise InvalidAudioError(
                "Could not process the audio. Please send a valid voice recording."
            ) from exc

        if not text:
            raise NoSpeechDetectedError("No speech was detected in the audio. Please try again.")
        return text
