"""Application entry point: creates the FastAPI app and wires everything together.

Run it with:
    uvicorn app.main:app --reload
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import get_settings
from app.core.errors import RateLimitExceededError, VoiceBotError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """Every error in the API has the same JSON shape:
    {"error": {"code": "...", "message": "..."}}
    A consistent shape makes life easy for whoever writes the client."""
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Using a function (an "app factory") instead of a global makes it easy
    to create fresh apps in tests.
    """
    settings = get_settings()

    app = FastAPI(
        title="Voice Chatbot API",
        description="Speak to an AI: Speech-to-Text -> LLM -> Text-to-Speech.",
        version="1.0.0",
        # FastAPI auto-generates an interactive docs page (/docs) and its schema
        # (/openapi.json). They are documentation, not API endpoints, and are handy
        # for demos. Set ENABLE_DOCS=false to switch them off (e.g. in production).
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )

    # CORS: browsers block web pages from calling an API on a different
    # origin (host:port) unless the API allows it. We allow ONLY the origins
    # listed in settings (the demo web client) - never "*".
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["POST"],
        allow_headers=["*"],
        # Without this, browser JavaScript cannot read our custom headers.
        expose_headers=["X-Transcript", "X-Reply-Text", "Retry-After"],
    )

    app.include_router(router)

    # --- Error handlers: turn exceptions into clean JSON responses ----------

    @app.exception_handler(VoiceBotError)
    async def handle_voicebot_error(_request: Request, exc: VoiceBotError) -> JSONResponse:
        response = error_response(exc.status_code, exc.code, exc.message)
        if isinstance(exc, RateLimitExceededError):
            # Standard header telling the client how long to wait.
            response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return response

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # e.g. missing "audio" field or a malformed session_id.
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        return error_response(422, "validation_error", f"Invalid request - {problems}")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        # A bug we did not foresee. Log the full stack trace for us, but give the
        # client a generic message: stack traces can leak internal details.
        logger.exception("Unexpected error: %s", exc)
        return error_response(500, "internal_error", "Something went wrong on our side.")

    return app


app = create_app()
