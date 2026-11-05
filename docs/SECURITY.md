# Security

This page lists the protections in the project, the threat each one stops, and where it is in the code.

| # | Protection | Threat it stops | Code |
|---|-----------|-----------------|------|
| 1 | Content-type **allow-list** | Uploading executables, documents, or other non-audio files | `app/core/validation.py` |
| 2 | **Size limit**, reading max+1 bytes | Memory exhaustion from huge uploads | `app/core/validation.py` |
| 3 | Empty-file check | Wasting model time on nothing | `app/core/validation.py` |
| 4 | Decode check (STT) | Fake "audio" files that pass the type check | `app/services/stt.py` |
| 5 | `session_id` regex (`^[A-Za-z0-9_-]{1,64}$`) | Junk/huge keys in memory | `app/api/routes.py` |
| 6 | **Rate limiting** per IP (10/min) | Abuse, CPU overload, burning the Groq quota | `app/core/rate_limit.py` |
| 7 | **CORS** allow-list, POST only | Other websites calling the API from users' browsers | `app/main.py` |
| 8 | Secrets via `.env` + `SecretStr` | Leaking the API key in git or logs | `app/config.py` |
| 9 | Generic error messages | Leaking stack traces / Groq account info | `app/main.py`, `app/services/llm.py` |
| 10 | No transcript logging | Personal data in log files | `app/api/routes.py` |
| 11 | Memory caps (turns + sessions, LRU) | RAM exhaustion via many sessions | `app/services/memory.py` |
| 12 | `LLM_MAX_TOKENS`, timeout | Runaway cost/latency | `app/services/llm.py` |
| 13 | `textContent` in web client | XSS from server-provided text | `client/app.js` |

## Terms explained

- **CORS (Cross-Origin Resource Sharing):** browsers block a web page from reading responses
  from a *different* origin (scheme + host + port) unless that server allows it. We allow only our
  demo page. Note that CORS protects *browser users*. It does not stop curl or scripts, and that is
  why rate limiting exists too.
- **Rate limiting:** a cap on requests per client per time window. We use a *sliding window*:
  we remember the timestamps of recent requests and count those in the last 60 seconds.
- **Allow-list vs block-list:** an allow-list accepts only known-good values. A block-list
  tries to name every bad value, and it always misses some.
- **XSS (Cross-Site Scripting):** if a page inserts server text as HTML, a malicious string
  like `<img onerror=...>` would run as code. `textContent` treats it as plain text.

## Known limitations (and how production would fix them)

| Limitation | Production fix |
|-----------|----------------|
| No authentication: anyone who can reach the server can use it | API keys or OAuth2 (FastAPI `Security` dependencies) |
| Rate limit is in memory and per process | Redis-backed limiter or an API gateway |
| HTTP, not HTTPS | Reverse proxy (Caddy/nginx) with TLS certificates |
| Content type is client-declared | Already mitigated by the decode check. Could add magic-byte sniffing |
| Behind a proxy, every request has the proxy's IP | `uvicorn --proxy-headers --forwarded-allow-ips=<proxy ip>` |
| Prompt injection (a user says "ignore your instructions") | Acceptable for a chat bot with no tools or private data. Never give the LLM secrets or actions |

## Reporting

If you find a security issue, do not open a public issue. Contact the maintainer directly.
