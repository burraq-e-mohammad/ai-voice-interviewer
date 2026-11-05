# Security Rules

The API accepts files from the internet and spends money-like resources (CPU and Groq quota),
so every change must keep these protections in place.

## 1. Secrets

- The Groq key lives **only** in `.env` (git-ignored) or real environment variables.
- Never hard-code keys, not even in tests. Tests use the dummy value `test-key-not-real`.
- Store secrets as `SecretStr` in `app/config.py`, so they print as `**********`.
- Call `.get_secret_value()` in exactly one place (`app/api/dependencies.py`).
- `.env.example` contains placeholders only.

## 2. Input validation (validate before doing expensive work)

- Uploaded audio is checked in `app/core/validation.py` **before** any model runs:
  - content type must be in the `ALLOWED_AUDIO_TYPES` **allow-list** (never use a block-list),
  - size must be ≤ `MAX_AUDIO_BYTES`. Read at most `max + 1` bytes, never the whole file,
  - the file must not be empty.
- Files that pass the checks but cannot be decoded are rejected with 400 by the STT service.
- `session_id` must match `^[A-Za-z0-9_-]{1,64}$`. This keeps junk out of memory.
- New inputs must have explicit limits (length, size, range) declared with pydantic/FastAPI.

## 3. Rate limiting

- Every `/chat` request passes `enforce_rate_limit` **first** (it is a route dependency).
- The default is 10 requests per 60 seconds per IP. Change it through settings, not code.
- The 429 response includes a `Retry-After` header.
- Known limitation: the limit is in memory and per process. Use Redis or a gateway for multi-server setups.
- Behind a reverse proxy, the client IP comes from `X-Forwarded-For`. Only trust that
  header when the proxy is trusted (configure `uvicorn --proxy-headers --forwarded-allow-ips`).

## 4. CORS

- Only origins listed in `CORS_ORIGINS` may call the API from a browser.
- **Never** use `allow_origins=["*"]`.
- Only the `POST` method is allowed.
- Only the headers the client really needs are exposed (`X-Transcript`, `X-Reply-Text`, `Retry-After`).

## 5. Error responses and logging

- Clients only ever see `{"error": {"code", "message"}}` with friendly text.
- Unexpected exceptions return a generic 500. Stack traces go to the server log only.
- Errors from Groq are logged on the server but never forwarded, because they may contain account details.
- Do not log transcripts or replies (user speech is personal data). Log lengths and timings.

## 6. Resource protection

- Conversation memory is capped per session (`MAX_HISTORY_TURNS`) and in total
  (`MAX_SESSIONS`, LRU eviction), so RAM cannot be exhausted.
- LLM output is capped by `LLM_MAX_TOKENS`, and Groq calls have a timeout.
- Models run in a thread pool, so one slow request cannot freeze the event loop.

## 7. Frontend (client/)

- Insert server text with `textContent`, never `innerHTML`, to prevent XSS.

## 8. Dependencies

- Pin minimum versions in `requirements.txt`. Add upper bounds only for known breakages
  (for example `av<17`), with a comment explaining why.
- Install only from PyPI. Check new packages for maintenance and licence first.

## 9. Production checklist (beyond this demo)

- Serve over HTTPS (a reverse proxy such as Caddy or nginx).
- Set `ENABLE_DOCS=false`.
- Add authentication (an API key header or OAuth) if the API is public.
- Use a shared rate-limit store (Redis).
