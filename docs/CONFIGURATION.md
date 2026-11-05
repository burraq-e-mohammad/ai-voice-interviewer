# Configuration

All settings are defined in **one place**, the `Settings` class in `app/config.py`. Values come
from (highest priority first):

1. real environment variables (e.g. `set GROQ_MODEL=...` in the terminal),
2. the `.env` file in the project root,
3. the defaults in `app/config.py`.

Variable names are **not case-sensitive**: `GROQ_API_KEY` fills the field `groq_api_key`.
Pydantic **validates** every value at startup. For example, `RATE_LIMIT_REQUESTS=0` is rejected
with a clear error before the server starts.

## Required

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Your Groq API key (starts with `gsk_`). Free at https://console.groq.com/keys. Stored as `SecretStr`, so it never appears in logs. |

## LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_MODEL` | `qwen/qwen3.8-27b` | Any chat model from https://console.groq.com/docs/models |
| `LLM_MAX_TOKENS` | `300` | Maximum answer length (16–2048). Shorter answers are faster to speak. |
| `LLM_TIMEOUT_SECONDS` | `30` | Give up on Groq after this long. |
| `SYSTEM_PROMPT` | *(friendly, short, no markdown)* | The bot's personality and rules. |

## Speech-to-Text

| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPER_MODEL_SIZE` | `base` | `tiny`, `base`, `small`, `medium`, `large-v3` (or `*.en` English-only). Bigger = more accurate, slower, more RAM. |
| `WHISPER_DEVICE` | `cpu` | `cuda` for an NVIDIA GPU. |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8` (CPU), `float16` (GPU). |

Approximate model sizes: tiny 75 MB · base 145 MB · small 485 MB · medium 1.5 GB · large-v3 3 GB.

## Text-to-Speech

| Variable | Default | Description |
|----------|---------|-------------|
| `PIPER_VOICE_PATH` | `models/en_US-lessac-medium.onnx` | Path to the voice model. The `.onnx.json` file must sit next to it. |

## Security & limits

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_AUDIO_BYTES` | `10485760` (10 MB) | Larger uploads get **413**. |
| `RATE_LIMIT_REQUESTS` | `10` | Requests allowed per client IP per window. |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Window length for the limit. |
| `CORS_ORIGINS` | `["http://localhost:5500","http://127.0.0.1:5500"]` | **JSON list** of browser origins allowed to call the API. |
| `ENABLE_DOCS` | `true` | Serve `/docs` and `/openapi.json`. Set `false` in production. |

## Conversation memory

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_HISTORY_TURNS` | `5` | Past exchanges remembered per session (0–20). `0` turns memory off. |
| `MAX_SESSIONS` | `1000` | Maximum sessions in RAM. The least recently used one is evicted. |

## Notes

- After changing `.env`, **restart** the server. Settings are read once (`lru_cache`).
- Never commit `.env`. It is in `.gitignore`. Commit changes to `.env.example` instead.
- Tests do not need a `.env`. `tests/conftest.py` sets a dummy key.
