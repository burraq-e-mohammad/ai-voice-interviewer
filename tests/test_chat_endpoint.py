"""End-to-end tests of POST /chat through the real FastAPI app (with fake AI services)."""

from urllib.parse import unquote

from fastapi.testclient import TestClient

from app.api.dependencies import get_pipeline, get_rate_limiter
from app.config import get_settings
from app.core.errors import InvalidAudioError, LLMServiceError, NoSpeechDetectedError
from app.core.rate_limit import RateLimiter
from app.main import app
from tests.conftest import FAKE_AUDIO, FAKE_REPLY_AUDIO, FakeLLM, FakeSTT


def post_audio(
    client: TestClient,
    data: bytes = FAKE_AUDIO,
    content_type: str = "audio/wav",
    session_id: str | None = None,
):
    """Helper: send a multipart upload the same way a browser would."""
    form = {"session_id": session_id} if session_id is not None else None
    return client.post("/chat", files={"audio": ("voice.wav", data, content_type)}, data=form)


# --- Happy path ---------------------------------------------------------------


def test_chat_returns_audio_and_text_headers(client: TestClient) -> None:
    response = post_audio(client)

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == FAKE_REPLY_AUDIO
    assert unquote(response.headers["X-Transcript"]) == "Hello bot"
    assert unquote(response.headers["X-Reply-Text"]) == "Hello human"


def test_non_ascii_text_is_safely_encoded_in_headers(client: TestClient, fake_stt: FakeSTT) -> None:
    fake_stt.text = "Привет, café ☕"

    response = post_audio(client)

    assert response.status_code == 200
    assert unquote(response.headers["X-Transcript"]) == "Привет, café ☕"


def test_browser_content_type_with_codec_suffix_is_accepted(client: TestClient) -> None:
    # Chrome sends "audio/webm;codecs=opus".
    response = post_audio(client, content_type="audio/webm;codecs=opus")
    assert response.status_code == 200


def test_session_id_gives_the_llm_conversation_history(
    client: TestClient, fake_llm: FakeLLM
) -> None:
    post_audio(client, session_id="abc-123")
    post_audio(client, session_id="abc-123")

    # The second call should have received the first exchange as history.
    _question, history = fake_llm.calls[1]
    assert [m.content for m in history] == ["Hello bot", "Hello human"]


def test_requests_without_session_id_are_stateless(client: TestClient, fake_llm: FakeLLM) -> None:
    post_audio(client)
    post_audio(client)

    assert fake_llm.calls[1][1] == []


# --- Input validation -----------------------------------------------------------


def test_missing_audio_field_returns_422(client: TestClient) -> None:
    response = client.post("/chat")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unsupported_file_type_returns_415(client: TestClient) -> None:
    response = post_audio(client, data=b"%PDF-1.4", content_type="application/pdf")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_empty_file_returns_400(client: TestClient) -> None:
    response = post_audio(client, data=b"")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_audio"


def test_too_large_file_returns_413(client: TestClient) -> None:
    too_big = b"0" * (get_settings().max_audio_bytes + 1)

    response = post_audio(client, data=too_big)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "audio_too_large"


def test_invalid_session_id_returns_422(client: TestClient) -> None:
    response = post_audio(client, session_id="bad id with spaces & symbols!")

    assert response.status_code == 422


# --- Service errors are mapped to clean JSON responses -------------------------


class FailingPipeline:
    """A pipeline that always raises the given exception."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def run(self, audio_bytes: bytes, session_id: str | None = None):
        raise self.error


def use_failing_pipeline(error: Exception) -> None:
    app.dependency_overrides[get_pipeline] = lambda: FailingPipeline(error)


def test_no_speech_returns_422(client: TestClient) -> None:
    use_failing_pipeline(NoSpeechDetectedError("No speech."))

    response = post_audio(client)

    assert response.status_code == 422
    assert response.json() == {"error": {"code": "no_speech_detected", "message": "No speech."}}


def test_undecodable_audio_returns_400(client: TestClient) -> None:
    use_failing_pipeline(InvalidAudioError("Bad audio."))

    assert post_audio(client).status_code == 400


def test_llm_failure_returns_502(client: TestClient) -> None:
    use_failing_pipeline(LLMServiceError("AI down."))

    response = post_audio(client)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "llm_unavailable"


def test_unexpected_error_returns_generic_500_without_details(client: TestClient) -> None:
    use_failing_pipeline(RuntimeError("secret internal detail"))

    response = post_audio(client)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    # The internal error message must never leak to the client.
    assert "secret" not in response.text


# --- Security -----------------------------------------------------------------


def test_rate_limit_returns_429_with_retry_after(client: TestClient) -> None:
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    limiter = RateLimiter(max_requests=2, window_seconds=60)

    assert post_audio(client).status_code == 200
    assert post_audio(client).status_code == 200
    response = post_audio(client)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
    assert int(response.headers["Retry-After"]) > 0


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/chat",
        headers={"Origin": "http://localhost:5500", "Access-Control-Request-Method": "POST"},
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5500"


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    response = client.options(
        "/chat",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_only_one_api_endpoint_exists() -> None:
    # The OpenAPI schema lists every API endpoint (but not the /docs pages).
    paths = app.openapi()["paths"]

    assert list(paths) == ["/chat"]
    assert list(paths["/chat"]) == ["post"]


def test_get_on_chat_is_not_allowed(client: TestClient) -> None:
    assert client.get("/chat").status_code == 405
