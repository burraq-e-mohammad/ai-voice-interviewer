# Presentation guide: demoing to your mentor

## Before the meeting (10 minutes)

1. `pytest`: confirm `44 passed`.
2. Start the API: `uvicorn app.main:app`.
3. Start the client: `python -m http.server 5500 --directory client`.
4. **Warm up**: open http://localhost:5500 and ask one question. This loads the models,
   so the live demo is fast.
5. Check your microphone permissions in the browser.

## Suggested 10-minute flow

| Time | What to show | What to say |
|------|-------------|-------------|
| 1 min | README diagram | "Voice in, voice out. Three steps: Whisper turns speech into text, Groq's Qwen model writes an answer, Piper speaks it." |
| 2 min | **Live demo** in the browser | Ask "What is FastAPI?", then a follow-up: "Why is it fast?" |
| 1 min | Point at the follow-up | "It understood 'it' because of conversation memory, using the session_id." |
| 2 min | `app/api/routes.py` → `app/services/pipeline.py` | "The route only handles HTTP. The pipeline only orchestrates. Each service wraps one library." |
| 1 min | http://localhost:8000/docs | "Exactly one endpoint, documented automatically." |
| 2 min | Security: `validation.py`, `rate_limit.py` | Upload a .txt in /docs → 415. "Allow-list, size limit, rate limit, CORS." |
| 1 min | Run `pytest` | "44 tests in about a second. The AI is faked through dependency injection, so the tests run offline." |

## Likely questions and good answers

**Why these STT/TTS libraries?**
They are both free, open-source, and run locally on a CPU with just `pip install`. faster-whisper is
Whisper on an optimised engine, about 4× faster. Piper is a fast neural TTS. Details are in `docs/DECISIONS.md`.

**What happens if Groq is down or the key is wrong?**
`LLMService` catches the error, logs the real reason, and raises `LLMServiceError`. The client gets
a 502 with a friendly message. The real reason is never leaked.

**Why `run_in_threadpool`?**
The models are blocking CPU work. In an async server, that would freeze all other requests. The thread pool keeps
the event loop free.

**How do the tests work without the models?**
Dependency injection. The endpoint gets the pipeline from `Depends(get_pipeline)`. Tests replace
it with `app.dependency_overrides`, and each service accepts a fake engine in its constructor.

**Why is the first request slow?**
The models are loaded lazily and cached with `lru_cache`. That trade-off gives instant startup and light tests.

**How does the rate limiter work?**
It is a sliding window. For each IP, it keeps the timestamps of recent requests, drops those older than 60 s, and
refuses the request if 10 remain. It returns 429 with `Retry-After`.

**What would you change for production?**
Authentication, HTTPS, Redis for rate limits and memory, streaming responses for lower latency,
and Docker for deployment. See `docs/SECURITY.md` → Known limitations.

**Why is memory stored in RAM?**
It is simple, with no database to install. It is capped per session and in total, so it can't grow forever. The
trade-off is that it is lost on restart.

**Why is the text in headers?**
The response body is the audio itself, so any client can play it directly. The text is a bonus for
clients that want to display it. Headers must be ASCII, so the text is URL-encoded.

## If something goes wrong live

- Mic not working → use `/docs` and upload a pre-recorded WAV (see the recipe in `skills.md` §10).
- Groq error 502 → check `GROQ_API_KEY` in `.env` and restart the server.
- More in `docs/TROUBLESHOOTING.md`.
