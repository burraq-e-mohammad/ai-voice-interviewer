# Architecture

## Big picture

```
 ┌──────────────┐  multipart upload   ┌──────────────────────────────────────────────┐
 │ Browser /    │ ──────────────────► │ FastAPI app (app/main.py)                    │
 │ curl client  │                     │   CORS middleware → error handlers → router  │
 │              │ ◄────────────────── │                                              │
 └──────────────┘  audio/wav + text   │  POST /chat (app/api/routes.py)              │
                     headers          │    1. enforce_rate_limit   (core/rate_limit) │
                                      │    2. read_validated_audio (core/validation) │
                                      │    3. pipeline.run  ── in a thread pool ──┐  │
                                      └───────────────────────────────────────────┼──┘
                                                                                  ▼
                       ┌─────────────────── VoiceChatPipeline (services/pipeline.py) ─┐
                       │  SpeechToText ──► LLMService ──► TextToSpeech                │
                       │  (faster-whisper)  (Groq API)    (Piper)                     │
                       │        ▲               ▲                                     │
                       │        └─ ConversationMemory (history per session_id) ┘      │
                       └──────────────────────────────────────────────────────────────┘
```

## Layers

The code is split into layers. Each layer has one responsibility.

| Layer | Folder | Responsibility | Knows about HTTP? |
|-------|--------|---------------|-------------------|
| Entry point | `app/main.py` | Create the app, add CORS, register error handlers | Yes |
| API | `app/api/` | The `/chat` route and its dependencies | Yes |
| Services | `app/services/` | STT, LLM, TTS, memory, pipeline | **No** |
| Core | `app/core/` | Errors, rate limiter, upload validation | Barely (validation reads an `UploadFile`) |
| Models | `app/models/` | Data shapes shared by all layers | No |
| Config | `app/config.py` | Settings from the environment | No |

**Why layers?** If tomorrow you want a command-line version of the bot, you can reuse
`app/services/` unchanged. Only the HTTP layer is FastAPI-specific.

## Request lifecycle, step by step

1. **CORS middleware** (browser requests only). If the page's origin is not in
   `CORS_ORIGINS`, the browser blocks the call.
2. **Rate limit dependency**: `enforce_rate_limit` asks the `RateLimiter` whether this IP
   has requests left. If not, it raises `RateLimitExceededError` → **429**.
3. **FastAPI parameter parsing**: it checks that `audio` exists and that `session_id` matches the pattern.
   If not, it returns **422** `validation_error`.
4. **Upload validation**: `read_validated_audio` checks the type (allow-list), size, and emptiness.
5. **Pipeline**: `run_in_threadpool(pipeline.run, ...)`. The models are CPU-heavy and
   *blocking*. Running them in a worker thread keeps the async server free to handle other requests.
6. **Response**: WAV bytes with `media_type="audio/wav"`, plus URL-encoded
   `X-Transcript` and `X-Reply-Text` headers.
7. **Errors**: any `VoiceBotError` raised anywhere is turned into JSON by the handler in
   `app/main.py`. Unknown exceptions become a generic 500.

## Design patterns used (and why)

| Pattern | Where | Why |
|---------|-------|-----|
| **App factory** | `create_app()` in `main.py` | Builds a configured app in one place |
| **Dependency injection** | `Depends(get_pipeline)`, constructor parameters | Tests swap in fakes; no hidden globals |
| **Singleton via `lru_cache`** | `get_settings`, `get_pipeline`, `get_rate_limiter` | Load models / read env exactly once |
| **Lazy loading** | models created on first request | Instant startup, light tests |
| **Protocol (structural typing)** | `pipeline.py` | Any object with the right method fits, so providers are swappable |
| **Exception hierarchy** | `core/errors.py` | One handler maps every error to a status code |
| **Allow-list** | `ALLOWED_AUDIO_TYPES` | Safer than trying to block bad types |

## Concurrency

- FastAPI runs on an **async event loop**. Slow, blocking work (Whisper, Piper, the
  Groq SDK call) would freeze it, so the whole pipeline runs in a **thread pool**.
- The services are shared between threads, so the mutable state (memory dict and rate-limiter
  dict) is protected by a `threading.Lock`.
- Whisper and Piper inference itself is read-only on the model weights, so it is safe to share.

## State

| State | Lives in | Survives restart? | Shared across processes? |
|-------|----------|-------------------|--------------------------|
| Conversation memory | RAM (`ConversationMemory`) | No | No |
| Rate-limit counters | RAM (`RateLimiter`) | No | No |
| Models | RAM, loaded from disk/HF cache | Reloaded | Each process loads its own |

This is intentional for a simple local project. To scale up, move memory and rate limits to Redis.
