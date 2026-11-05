# CLAUDE.md: Voice Chatbot project guide

This file explains the whole project on one page. It is read automatically by Claude Code
(an AI coding assistant), and it is written so that a beginner can also read it and explain
the project to someone else.

## What this project does

A **voice chatbot API**. A user sends a voice recording, and the API sends back a spoken
answer. Inside, three AI steps run one after another:

1. **Speech-to-Text (STT)**: `faster-whisper` turns the recording into text. Runs locally.
2. **LLM**: Groq (model `qwen/qwen3.8-27b`) writes an answer to that text. Runs in the cloud.
3. **Text-to-Speech (TTS)**: `Piper` turns the answer into a WAV file. Runs locally.

There is exactly **one endpoint**: `POST /chat` (audio in → audio out).

## Tech stack

| Concern | Choice |
|---------|--------|
| Web framework | FastAPI + Uvicorn |
| Settings | pydantic-settings (`.env` file) |
| STT | faster-whisper (Whisper `base`, int8, CPU) |
| LLM | Groq Python SDK |
| TTS | piper-tts (`en_US-lessac-medium` voice) |
| Tests / quality | pytest, ruff (lint + format), mypy (types) |

## Architecture (layers)

```
HTTP request
   │
   ▼
app/api/routes.py        ← HTTP layer: rate limit, validate upload, return audio
   │
   ▼
app/services/pipeline.py ← Orchestration: STT → LLM → TTS, plus memory
   │
   ├── app/services/stt.py     (faster-whisper)
   ├── app/services/llm.py     (Groq)
   ├── app/services/tts.py     (Piper)
   └── app/services/memory.py  (last N exchanges per session, in RAM)

app/core/      ← cross-cutting helpers: errors, rate limiting, validation
app/models/    ← shared data shapes (Message, ChatResult, ErrorResponse)
app/config.py  ← all settings in one typed class
app/main.py    ← builds the app: CORS, error handlers, router
```

**Golden rule:** each layer only talks to the layer below it. Routes know nothing about
Whisper or Groq, and services know nothing about HTTP.

## How a request flows

1. `enforce_rate_limit` checks the client IP. If over the limit, it returns **429**.
2. `read_validated_audio` checks the content type (allow-list), the size, and that the file
   is not empty. Problems return **415 / 413 / 400**.
3. `pipeline.run()` runs in a **thread pool**, because the models block the CPU.
4. The response body is WAV audio. The headers `X-Transcript` and `X-Reply-Text` carry the text.
5. Any `VoiceBotError` is turned into JSON `{"error": {"code", "message"}}` in `app/main.py`.

## How to run

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
python scripts/download_voice.py          # Piper voice → models/
copy .env.example .env                    # then set GROQ_API_KEY
uvicorn app.main:app --reload             # API on :8000, docs at /docs
python -m http.server 5500 --directory client   # demo page on :5500
```

## How to test and check quality

```bash
pytest          # 44 tests, ~1 s, no models or network (fakes are used)
ruff check .    # lint
ruff format .   # format
mypy app        # type check
```

## Key design decisions (details in docs/DECISIONS.md)

- **Dependency injection**: `get_pipeline()` and `get_rate_limiter()` are FastAPI dependencies,
  so tests swap them out with `app.dependency_overrides`.
- **Lazy model loading**: models load on the first request (`lru_cache`). Startup is instant, but
  the first request is slow.
- **Protocols** in `pipeline.py` define what STT/LLM/TTS must look like, so the services
  can be replaced.
- **Memory is optional and in-RAM**: it is only used when the client sends `session_id`. It is
  capped per session (`MAX_HISTORY_TURNS`) and in total (`MAX_SESSIONS`).
- **`av<17` is pinned**: faster-whisper 1.2.x breaks with av 17+.

## Conventions (full rules in .claude/rules/)

- Type hints on every function, and docstrings that explain *why*.
- Services raise `VoiceBotError` subclasses, never `HTTPException`.
- Never log or return secrets, stack traces, or user speech text.
- Every new behaviour gets a test, and every new setting goes in `config.py` and `.env.example`.

## Where to look

| I want to... | Go to |
|--------------|-------|
| Change the bot's personality | `SYSTEM_PROMPT` in `.env` / `app/config.py` |
| Change the voice | `scripts/download_voice.py` + `PIPER_VOICE_PATH` |
| Add an error type | `app/core/errors.py` |
| Change limits | `.env` (`RATE_LIMIT_*`, `MAX_AUDIO_BYTES`) |
| See recipes for common tasks | `skills.md` |
