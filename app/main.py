"""Application entry point: creates the FastAPI app and wires everything together."""

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
    """Consistent JSON response format for all client-facing errors."""
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="AI Voice Interviewer API",
        description="Spoken mock interview system with real-time STT, Gemini conversational reasoning, and Piper neural speech.",
        version="2.0.0",
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Transcript",
            "X-Reply-Text",
            "X-Turn",
            "X-Max-Turns",
            "X-Is-Complete",
            "Retry-After",
        ],
    )

    app.include_router(router)

    @app.exception_handler(VoiceBotError)
    async def handle_voicebot_error(_request: Request, exc: VoiceBotError) -> JSONResponse:
        response = error_response(exc.status_code, exc.code, exc.message)
        if isinstance(exc, RateLimitExceededError):
            response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return response

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        return error_response(422, "validation_error", f"Invalid request - {problems}")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unexpected error: %s", exc)
        return error_response(500, "internal_error", "Something went wrong on our side.")

    return app


app = create_app()
