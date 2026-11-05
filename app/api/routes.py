"""The API's only endpoint: POST /chat.

The endpoint is deliberately thin. Its job is HTTP stuff only:
  1. check the request (rate limit, file type/size, session id),
  2. hand the audio to the pipeline,
  3. send the reply audio back.
All the AI logic lives in `app/services/`.
"""

import logging
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.api.dependencies import enforce_rate_limit, get_app_settings, get_pipeline
from app.config import Settings
from app.core.validation import read_validated_audio
from app.models.schemas import ErrorResponse
from app.services.pipeline import VoiceChatPipeline

logger = logging.getLogger(__name__)

router = APIRouter()

# Session ids are only letters, digits, "-" and "_" (e.g. a UUID), max 64 chars.
# Rejecting anything else keeps junk and huge strings out of our memory store.
SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


@router.post(
    "/chat",
    summary="Talk to the voice bot",
    description=(
        "Upload a voice recording. The bot transcribes it, generates an answer "
        "with an LLM, and returns the answer as spoken audio (WAV)."
    ),
    response_class=Response,
    responses={
        200: {
            "content": {"audio/wav": {}},
            "description": "The spoken reply. Headers X-Transcript and X-Reply-Text "
            "contain the URL-encoded text versions.",
        },
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    # The rate limit runs first, before the upload is even validated.
    dependencies=[Depends(enforce_rate_limit)],
)
async def chat(
    audio: Annotated[UploadFile, File(description="Voice recording (wav, mp3, webm, ogg, ...)")],
    pipeline: Annotated[VoiceChatPipeline, Depends(get_pipeline)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    session_id: Annotated[
        str | None,
        Form(
            pattern=SESSION_ID_PATTERN,
            description="Optional. Send the same id on each request to keep conversation context.",
        ),
    ] = None,
) -> Response:
    audio_bytes = await read_validated_audio(audio, settings.max_audio_bytes)

    # The pipeline is slow, blocking CPU work. Running it in a thread pool keeps
    # the server's event loop free to accept other requests in the meantime.
    result = await run_in_threadpool(pipeline.run, audio_bytes, session_id)

    # Note: we log lengths, not the text itself - user speech can be private.
    logger.info(
        "Chat ok: transcript=%d chars, reply=%d chars",
        len(result.transcript),
        len(result.reply_text),
    )

    return Response(
        content=result.reply_audio,
        media_type="audio/wav",
        headers={
            # HTTP headers may only contain plain ASCII, so the text is URL-encoded.
            # These let a client show the conversation as text, too.
            "X-Transcript": quote(result.transcript),
            "X-Reply-Text": quote(result.reply_text),
        },
    )
