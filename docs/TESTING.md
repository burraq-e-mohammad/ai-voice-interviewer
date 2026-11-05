# Testing

## Run the tests

```bash
.venv\Scripts\activate        # Windows  (source .venv/bin/activate on macOS/Linux)
pytest
```

Expected: `44 passed` in about one second. You need **no** internet, models, or Groq key.

## Strategy: test our code, fake the AI

The AI models are slow (seconds), large (hundreds of MB), and the LLM costs quota and needs
a network. Tests that use them would be slow, flaky, and impossible to run offline.

So we split the testing:

| What | How it's tested |
|------|-----------------|
| Our logic (validation, errors, rate limit, memory, prompt building, pipeline order) | **Automated tests** with fakes |
| That the real models/APIs work | **Manual smoke test** before a demo (below) |

This works because of **dependency injection**: every service takes its engine as a
constructor argument, and the endpoint gets its pipeline through `Depends(get_pipeline)`. In
tests, `app.dependency_overrides[get_pipeline] = lambda: fake_pipeline` swaps in the fake.

## Test files

| File | Tests | Covers |
|------|-------|--------|
| `test_chat_endpoint.py` | 19 | Full HTTP behaviour: success, headers, encoding, all validation errors, error mapping, rate limit 429, CORS, single-endpoint rule |
| `test_services.py` | 10 | STT segment joining and errors, the LLM message format, `<think>` tag removal and error wrapping (no key leakage), TTS WAV validity |
| `test_memory.py` | 7 | Ordering, turn limit, isolation, LRU eviction, disabled memory |
| `test_rate_limit.py` | 5 | Limit, window expiry, Retry-After, per-client counting (fake clock) |
| `test_pipeline.py` | 3 | Step order, memory saved on success only |

## Useful commands

```bash
pytest -k cors                         # only tests with "cors" in the name
pytest tests/test_memory.py            # one file
pytest -x                              # stop at the first failure
pytest --lf                            # re-run only the last failures
```

## Code-quality checks

```bash
ruff format .     # auto-format the code
ruff check .      # lint: unused imports, bug patterns, naming
mypy app          # static type check
```

## Manual smoke test (real models + real Groq)

1. Put your real `GROQ_API_KEY` in `.env`.
2. Start the API: `uvicorn app.main:app`.
3. Make a test question with Piper (no microphone needed):
   ```bash
   python -c "from app.services.tts import TextToSpeech; open('q.wav','wb').write(TextToSpeech('models/en_US-lessac-medium.onnx').synthesize('What is the capital of France?'))"
   ```
4. Send it:
   ```bash
   curl -X POST http://localhost:8000/chat -F "audio=@q.wav;type=audio/wav" --output reply.wav -D -
   ```
5. Expect `HTTP/1.1 200`, an `X-Transcript` header with your question, and a `reply.wav` that says "Paris".
6. Try the error paths: send a `.txt` file (→ 415), or send 11 requests in a minute (→ 429).

## Adding a test

1. Pick the right file (or create `tests/test_<module>.py`).
2. Name it after the behaviour: `test_<situation>_<expected result>`.
3. Use the fixtures in `conftest.py` (`client`, `fake_stt`, `fake_llm`, `pipeline`).
4. Follow Arrange → Act → Assert, with blank lines between them.
