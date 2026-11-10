"""Text-to-Speech using Piper.

Why Piper?
  * Open source, runs fully offline on a normal CPU, and is fast (it speaks
    faster than real time even on a Raspberry Pi).
  * Natural-sounding neural voices in many languages, each a small `.onnx`
    file (~60 MB) plus a `.onnx.json` config file.
  * Download a voice with:  python scripts/download_voice.py
"""

import io
import logging
import re
import wave
from pathlib import Path
from typing import Any

from app.core.errors import SpeechSynthesisError

logger = logging.getLogger(__name__)


class TextToSpeech:
    def __init__(self, voice_path: str, voice: Any | None = None) -> None:
        """Load a Piper voice model.

        `voice` lets tests pass in a fake voice instead of loading a real one.
        """
        if voice is None:
            path = Path(voice_path)
            if not path.is_file():
                # Check relative to project root
                alt_path = Path(__file__).resolve().parent.parent.parent / voice_path
                if alt_path.is_file():
                    path = alt_path
                else:
                    raise FileNotFoundError(
                        f"Piper voice not found at '{path}' or '{alt_path}'. "
                        "Run `python scripts/download_voice.py` to download it."
                    )
            from piper import PiperVoice

            logger.info("Loading Piper voice '%s'...", path.name)
            voice = PiperVoice.load(path)  # also reads '<voice>.onnx.json' next to it
        self._voice = voice

    def synthesize(self, text: str) -> bytes:
        """Turn text into speech and return it as WAV file bytes.

        Raises:
            SpeechSynthesisError: text is empty or Piper failed.
        """
        if not text.strip():
            raise SpeechSynthesisError("Cannot speak an empty reply.")

        # Clean and normalize text for neural voice synthesis
        clean_text = text.replace("’", "'").replace("“", '"').replace("”", '"').replace("—", ", ").replace("–", ", ")
        clean_text = re.sub(r"[\*#_`~<>]", "", clean_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        # We write the WAV into memory (BytesIO) instead of a file on disk:
        # it is faster and there are no temp files to clean up.
        buffer = io.BytesIO()
        try:
            with wave.open(buffer, "wb") as wav_file:
                # Piper sets the WAV header (sample rate, channels) for us.
                self._voice.synthesize_wav(clean_text, wav_file)
        except Exception as exc:
            logger.error("Piper synthesis failed: %s", exc)
            raise SpeechSynthesisError("Could not generate the spoken reply.") from exc

        return buffer.getvalue()
