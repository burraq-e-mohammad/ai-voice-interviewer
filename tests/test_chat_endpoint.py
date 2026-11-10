"""End-to-end API tests through the real FastAPI app (with fake AI services)."""

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
    session_id: str = "sess-123",
):
    """Helper: send a multipart /chat upload the same way the web client does."""
    return client.post(
        "/chat",
        files={"audio": ("voice.wav", data, content_type)},
        data={"session_id": session_id},
    )


# --- Resume parsing & session lifecycle ---------------------------------------


def test_parse_resume_extracts_plain_text(client: TestClient) -> None:
    response = client.post(
        "/session/parse-resume",
        files={"file": ("resume.txt", b"Built distributed FastAPI services.", "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "resume.txt"
    assert body["resume_text"] == "Built distributed FastAPI services."
    assert body["word_count"] == 4


def test_parse_resume_rejects_empty_file(client: TestClient) -> None:
    response = client.post(
        "/session/parse-resume",
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    assert response.status_code == 400


def test_start_interview_returns_session_and_opening_audio(
    client: TestClient, fake_llm: FakeLLM
) -> None:
    response = client.post(
        "/session/start",
        json={
            "profile": {
                "name": "Alex",
                "level": "Senior",
                "position": "Backend Engineer",
                "company": "Stripe",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["opening_text"] == fake_llm.opening
    assert body["opening_audio_base64"]
    assert body["turn"] == 1
    assert body["max_turns"] == get_settings().max_interview_turns


def test_evaluate_interview_returns_scorecard(client: TestClient, fake_llm: FakeLLM) -> None:
    start_resp = client.post(
        "/session/start",
        json={"profile": {"name": "Alex", "position": "SWE", "company": "Google"}},
    )
    session_id = start_resp.json()["session_id"]
    post_audio(client, session_id=session_id)

    eval_resp = client.post("/session/evaluate", json={"session_id": session_id})

    assert eval_resp.status_code == 200
    body = eval_resp.json()
    assert body["session_id"] == session_id
    assert body["score"] == fake_llm.score
    assert body["feedback_markdown"] == fake_llm.report
    assert body["candidate_name"] == "Alex"
    assert body["company"] == "Google"


# --- /chat happy path ---------------------------------------------------------


def test_chat_returns_audio_and_interview_headers(
    client: TestClient, fake_stt: FakeSTT, fake_llm: FakeLLM
) -> None:
    response = post_audio(client)

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == FAKE_REPLY_AUDIO
    assert unquote(response.headers["X-Transcript"]) == fake_stt.text
    assert unquote(response.headers["X-Reply-Text"]) == fake_llm.reply
    assert response.headers["X-Turn"] == "2"
    assert response.headers["X-Is-Complete"] == "false"


def test_non_ascii_text_is_safely_encoded_in_headers(
    client: TestClient, fake_stt: FakeSTT
) -> None:
    fake_stt.text = "Привет, café ☕"

    response = post_audio(client)

    assert response.status_code == 200
    assert unquote(response.headers["X-Transcript"]) == "Привет, café ☕"


def test_browser_content_type_with_codec_suffix_is_accepted(client: TestClient) -> None:
    response = post_audio(client, content_type="audio/webm;codecs=opus")

    assert response.status_code == 200


def test_session_id_preserves_interview_history_across_turns(
    client: TestClient, fake_stt: FakeSTT, fake_llm: FakeLLM
) -> None:
    post_audio(client, session_id="abc-123")
    post_audio(client, session_id="abc-123")

    _answer, history, _profile, turn, _max_turns = fake_llm.calls[1]
    assert turn == 2
    assert [m.content for m in history] == [fake_stt.text, fake_llm.reply]


# --- Input validation ---------------------------------------------------------


def test_missing_audio_field_returns_422(client: TestClient) -> None:
    response = client.post("/chat", data={"session_id": "abc-123"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_missing_session_id_returns_422(client: TestClient) -> None:
    response = client.post("/chat", files={"audio": ("voice.wav", FAKE_AUDIO, "audio/wav")})

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


# --- Service errors are mapped to clean JSON responses ------------------------


class FailingPipeline:
    """A pipeline that always raises the given exception."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def run(self, audio_bytes: bytes, session_id: str):
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
    assert "secret" not in response.text


# --- Security & routes --------------------------------------------------------


def test_rate_limit_returns_429_with_retry_after(client: TestClient) -> None:
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    app.dependency_overrides[get_rate_limiter] = lambda: limiter

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

    assert response.headers.get("access-control-allow-origin") in {"http://localhost:5500", "*"}


def test_expected_api_endpoints_exist() -> None:
    paths = set(app.openapi()["paths"])

    assert paths == {
        "/session/parse-resume",
        "/session/start",
        "/chat",
        "/session/evaluate",
    }


def test_get_on_chat_is_not_allowed(client: TestClient) -> None:
    assert client.get("/chat").status_code == 405

