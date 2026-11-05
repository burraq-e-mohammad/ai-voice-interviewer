# Architecture Rules

The project uses a simple **layered architecture**. Each layer has one job, and it only
depends on the layers below it.

## 1. The layers

| Layer | Folder | Job | May import from |
|-------|--------|-----|-----------------|
| Entry point | `app/main.py` | Build the app: middleware, error handlers, router | everything |
| API (HTTP) | `app/api/` | Requests/responses, validation, dependencies | services, core, models, config |
| Services | `app/services/` | AI work and business logic | core, models |
| Core | `app/core/` | Reusable helpers: errors, rate limit, validation | models |
| Models | `app/models/` | Data shapes (dataclasses, pydantic models) | nothing in `app/` |
| Config | `app/config.py` | Typed settings | nothing in `app/` |

## 2. Dependency direction

- Dependencies point **downwards only**. A service must never import from `app.api`.
- Services must not import FastAPI or return HTTP objects. They take plain Python values
  (`bytes`, `str`) and return plain values, so they can be reused in a CLI or a worker.
- Services do not read settings themselves. Their values are passed into the constructor
  by `app/api/dependencies.py`.

## 3. The single endpoint rule

- The API exposes exactly **one** endpoint: `POST /chat`.
- New features must fit into this endpoint (as optional form fields) or into services.
  Do not add routes. A test (`test_only_one_api_endpoint_exists`) guards this rule.
- `/docs` and `/openapi.json` are auto-generated documentation, and `ENABLE_DOCS` controls them.

## 4. Thin routes

- A route handler does: validate → call the pipeline → build the response. That's all.
- Business logic (prompt building, memory, error mapping of third-party exceptions) lives in services.

## 5. The pipeline

- `VoiceChatPipeline` only orchestrates. It calls `stt.transcribe`, then `llm.generate_reply`,
  then `tts.synthesize`.
- It depends on **Protocols** (`SpeechToTextEngine`, `ReplyGenerator`, `TextToSpeechEngine`),
  not on concrete classes. To swap a provider, write a new class with the same method and
  wire it in `dependencies.py`.
- Memory is updated only after all three steps succeed.

## 6. Object lifetime

- Heavy objects (models, the Groq client, memory, the rate limiter) are created **once**, through
  `@lru_cache` factory functions in `app/api/dependencies.py`.
- Models load **lazily** on the first request. Do not load models at import time.
- Shared mutable state (memory, rate limiter) must be protected with a `threading.Lock`,
  because the pipeline runs in a thread pool.

## 7. Errors

- All expected errors inherit from `VoiceBotError` and carry `status_code` and `code`.
- The mapping to HTTP happens in **one place**: the exception handlers in `app/main.py`.

## 8. Configuration

- Every tunable value is a field in `Settings` (`app/config.py`) with a safe default and
  validation (`Field(gt=0)` and so on), and it is documented in `.env.example` and `docs/CONFIGURATION.md`.
- No magic numbers in services. Pass them in from settings.

## 9. Adding a new component (checklist)

1. Put the class in `app/services/`, with constructor injection and an optional fake hook.
2. Define or extend a Protocol if the pipeline uses it.
3. Wire it in `app/api/dependencies.py`.
4. Add settings, tests, and docs.
