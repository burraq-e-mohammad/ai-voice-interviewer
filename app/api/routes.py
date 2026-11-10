"""API routes for AI Voice Interviewer: starting sessions, voice Q&A, and candidate evaluation."""

import base64
import io
import logging
import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.api.dependencies import enforce_rate_limit, get_app_settings, get_pipeline
from app.config import Settings
from app.core.validation import read_validated_audio
from app.models.schemas import (
    ErrorResponse,
    EvaluationRequest,
    EvaluationResponse,
    ParseResumeResponse,
    StartInterviewRequest,
    StartInterviewResponse,
)
from app.services.pipeline import VoiceChatPipeline

logger = logging.getLogger(__name__)

router = APIRouter()

SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


def extract_text_from_file(content: bytes, filename: str) -> str:
    """Extracts raw text from PDF, DOCX, or plain text bytes."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(content))
        text_parts = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(text_parts).strip()
    elif ext in ("docx", "doc"):
        import docx

        doc = docx.Document(io.BytesIO(content))
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()]).strip()
    else:
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1", errors="ignore")


@router.post(
    "/session/parse-resume",
    summary="Upload and extract text from candidate resume",
    description="Parses PDF, DOCX, or TXT resume files and extracts text for the LLM interviewer.",
    response_model=ParseResumeResponse,
    dependencies=[Depends(enforce_rate_limit)],
)
async def parse_resume(
    file: Annotated[UploadFile, File(description="Candidate resume file (PDF, DOCX, TXT)")],
) -> ParseResumeResponse:
    filename = file.filename or "resume.txt"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded resume file is empty.")

    try:
        text = await run_in_threadpool(extract_text_from_file, content, filename)
    except Exception as exc:
        logger.error("Failed to parse resume %s: %s", filename, exc)
        raise HTTPException(
            status_code=400, detail=f"Unable to read resume: {exc}"
        ) from exc

    words = len(text.split())
    logger.info("Parsed resume %s: %d characters, %d words", filename, len(text), words)
    return ParseResumeResponse(
        filename=filename,
        resume_text=text,
        char_count=len(text),
        word_count=words,
    )


@router.post(
    "/session/start",
    summary="Start a new interview session",
    description="Registers the candidate profile, initializes session state, and generates the verbal opening greeting.",
    response_model=StartInterviewResponse,
    responses={
        200: {"description": "Interview session successfully created with opening audio."},
        400: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
    dependencies=[Depends(enforce_rate_limit)],
)
async def start_interview(
    request: StartInterviewRequest,
    pipeline: Annotated[VoiceChatPipeline, Depends(get_pipeline)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> StartInterviewResponse:
    session_id = str(uuid.uuid4())
    logger.info("Starting interview session %s for %s (%s)", session_id, request.profile.name, request.profile.position)

    # Generate initial personalized greeting and question
    opening_text, opening_audio = await run_in_threadpool(
        pipeline.start_interview, session_id, request.profile
    )

    audio_b64 = base64.b64encode(opening_audio).decode("ascii")

    return StartInterviewResponse(
        session_id=session_id,
        opening_text=opening_text,
        opening_audio_base64=audio_b64,
        turn=1,
        max_turns=settings.max_interview_turns,
    )


@router.post(
    "/chat",
    summary="Conduct one voice interview turn",
    description=(
        "Upload the candidate's spoken response. The audio is transcribed via Whisper, "
        "the interviewer generates the next targeted question via Gemini, and speaks it back as WAV audio."
    ),
    response_class=Response,
    responses={
        200: {
            "content": {"audio/wav": {}},
            "description": "Spoken reply audio. Metadata returned in headers X-Transcript, X-Reply-Text, X-Turn, X-Is-Complete.",
        },
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    dependencies=[Depends(enforce_rate_limit)],
)
async def chat(
    audio: Annotated[UploadFile, File(description="Candidate voice recording (wav, webm, mp3)")],
    pipeline: Annotated[VoiceChatPipeline, Depends(get_pipeline)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    session_id: Annotated[
        str,
        Form(
            pattern=SESSION_ID_PATTERN,
            description="The session ID from /session/start.",
        ),
    ],
) -> Response:
    audio_bytes = await read_validated_audio(audio, settings.max_audio_bytes)

    # Process STT, LLM reasoning, and TTS in worker thread pool
    result = await run_in_threadpool(pipeline.run, audio_bytes, session_id)

    logger.info(
        "Voice turn processed: turn=%d/%d complete=%s transcript_len=%d",
        result.turn,
        result.max_turns,
        result.is_complete,
        len(result.transcript),
    )

    return Response(
        content=result.reply_audio,
        media_type="audio/wav",
        headers={
            "X-Transcript": quote(result.transcript),
            "X-Reply-Text": quote(result.reply_text),
            "X-Turn": str(result.turn),
            "X-Max-Turns": str(result.max_turns),
            "X-Is-Complete": "true" if result.is_complete else "false",
        },
    )


@router.post(
    "/session/evaluate",
    summary="Generate candidate performance evaluation report",
    description="Evaluates all candidate responses across the interview and returns scores and coaching feedback.",
    response_model=EvaluationResponse,
    responses={
        200: {"description": "Evaluation scorecard successfully generated."},
        400: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
    dependencies=[Depends(enforce_rate_limit)],
)
async def evaluate_interview(
    request: EvaluationRequest,
    pipeline: Annotated[VoiceChatPipeline, Depends(get_pipeline)],
) -> EvaluationResponse:
    logger.info("Evaluating interview dialogue for session %s", request.session_id)
    score, feedback_markdown, profile = await run_in_threadpool(pipeline.evaluate, request.session_id)

    return EvaluationResponse(
        session_id=request.session_id,
        score=score,
        feedback_markdown=feedback_markdown,
        candidate_name=profile.name,
        position=profile.position,
        company=profile.company,
    )
