"""Input validation for uploaded audio.

Rule: never trust user input. We check the upload *before* doing any
expensive work (speech recognition, LLM calls), so bad requests fail fast
and cheaply.
"""

from fastapi import UploadFile

from app.core.errors import AudioTooLargeError, InvalidAudioError, UnsupportedAudioTypeError

# Allow-list of audio formats. An allow-list (instead of a block-list) is safer:
# anything we did not explicitly approve is rejected.
# faster-whisper decodes all of these through FFmpeg (bundled via the `av` package).
ALLOWED_AUDIO_TYPES: frozenset[str] = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/mpeg",  # .mp3
        "audio/mp3",
        "audio/webm",  # what Chrome/Edge record in the browser
        "audio/ogg",  # what Firefox records in the browser
        "audio/mp4",  # what Safari records in the browser
        "audio/x-m4a",
        "audio/flac",
    }
)


async def read_validated_audio(upload: UploadFile, max_bytes: int) -> bytes:
    """Check the upload's type and size, and return its bytes.

    Raises:
        UnsupportedAudioTypeError: content type is not in the allow-list.
        AudioTooLargeError: file is bigger than `max_bytes`.
        InvalidAudioError: file is empty.
    """
    # Browsers send e.g. "audio/webm;codecs=opus" - we only compare the main part.
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise UnsupportedAudioTypeError(
            f"Unsupported audio type '{content_type or 'unknown'}'. "
            f"Allowed types: {', '.join(sorted(ALLOWED_AUDIO_TYPES))}."
        )

    # Read at most max_bytes + 1. If we got more than max_bytes, the file is too
    # big - and we never had to load a huge file fully into memory to find out.
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise AudioTooLargeError(f"Audio file is too large. Maximum size is {max_bytes} bytes.")
    if not data:
        raise InvalidAudioError("Audio file is empty.")

    return data
