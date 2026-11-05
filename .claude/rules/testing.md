# Testing Rules

Tests prove the code works and stop it from breaking later. Run them with `pytest`.

## 1. Goals

- The full suite runs in **a few seconds**, **offline**, and **without AI models or API keys**.
- Every bug fix comes with a test that would have caught the bug.
- Every new feature, setting, or error type comes with a test.

## 2. Test types in this project

| File | Kind | What it covers |
|------|------|----------------|
| `tests/test_chat_endpoint.py` | API / integration | Full HTTP flow through FastAPI with fake services |
| `tests/test_pipeline.py` | Unit | STT → LLM → TTS order, memory updates, error propagation |
| `tests/test_services.py` | Unit | Our wrapper code around Whisper, Groq, and Piper |
| `tests/test_rate_limit.py` | Unit | Sliding window, Retry-After, per-client isolation |
| `tests/test_memory.py` | Unit | History limits, session isolation, LRU eviction |

## 3. Fakes, not real services

- Never call the real Groq API or load real models in the test suite.
- Fakes live in `tests/conftest.py` (`FakeSTT`, `FakeLLM`, `FakeTTS`) or next to the test
  that needs them (`FakeWhisperModel`, `FakeGroqClient`, `FakePiperVoice`).
- Fakes can record their calls (`self.calls`), so tests can check *what* was passed in.
- Replace FastAPI dependencies with `app.dependency_overrides[...]`, and always clear
  them afterwards (the `client` fixture does this).

## 4. Controlling time

- Never use `time.sleep()` in tests. Inject a fake clock (see `FakeClock` in
  `test_rate_limit.py`) and move it forward by hand.

## 5. Writing a good test

- **Name** describes the behaviour: `test_too_large_file_returns_413`, not `test_upload_3`.
- **Arrange → Act → Assert**, separated by blank lines.
- Test **one behaviour** per test.
- Assert on the important parts: the status code **and** the error `code`, not the exact wording.
- Cover both the **happy path** and the **failure paths** (invalid input, service down).

## 6. Security behaviour must be tested

- Every validation rule (type, size, empty, session_id format).
- That the rate limit returns 429 with `Retry-After`.
- That CORS allows configured origins and rejects others.
- That internal error details never appear in responses.
- That exactly one API endpoint exists.

## 7. Manual / real-model checks

Automated tests use fakes. Before a demo, do one real check:
1. `uvicorn app.main:app` with a real `GROQ_API_KEY`.
2. Send a recording from the web client or with curl.
3. Confirm you hear a sensible reply.

## 8. Commands

```bash
pytest                                  # everything
pytest tests/test_memory.py             # one file
pytest -k rate_limit                    # tests whose name matches
pytest -x                               # stop at the first failure
```

## 9. Definition of done

`ruff format . && ruff check . && mypy app && pytest` all pass with no skipped tests
and no warnings ignored without a comment.
