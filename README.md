# 🎙️ Voice Chatbot

Talk to an AI and hear it talk back. You send a voice recording to **one API endpoint**
(`POST /chat`), and you get a spoken answer back.

```
 🎤 your voice ──► Speech-to-Text ──► LLM ──► Text-to-Speech ──► 🔊 spoken reply
                  (faster-whisper)   (Groq)     (Piper)
```

| Step | Library | Why | Runs where | Cost |
|------|---------|-----|-----------|------|
| Speech-to-Text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | OpenAI's open Whisper model, ~4× faster on CPU | Your machine | Free (MIT) |
| LLM | [Groq](https://console.groq.com) + `qwen/qwen3.8-27b` | Very fast responses, free tier, open models | Groq cloud | Free tier |
| Text-to-Speech | [Piper](https://github.com/OHF-Voice/piper1-gpl) | Natural neural voices, fast and offline on CPU | Your machine | Free (GPL-3.0) |

---

## 📁 Project structure

```
voice-chatbot/
├── app/                        # The application code
│   ├── main.py                 # Creates the FastAPI app: CORS, error handlers
│   ├── config.py               # All settings, read from environment / .env
│   ├── api/
│   │   ├── routes.py           # The one endpoint: POST /chat
│   │   └── dependencies.py     # Builds shared objects (pipeline, rate limiter)
│   ├── core/
│   │   ├── errors.py           # Custom exceptions → HTTP status codes
│   │   ├── rate_limit.py       # Sliding-window rate limiter
│   │   └── validation.py       # Upload checks (type, size, empty)
│   ├── models/
│   │   └── schemas.py          # Data shapes: Message, ChatResult, ErrorResponse
│   └── services/
│       ├── stt.py              # Speech-to-Text (faster-whisper)
│       ├── llm.py              # Answer generation (Groq)
│       ├── tts.py              # Text-to-Speech (Piper)
│       ├── memory.py           # Short-term conversation history
│       └── pipeline.py         # Connects STT → LLM → TTS
├── tests/                      # 43 automated tests (pytest)
├── client/                     # Hands-free browser client (Gemini-Live style)
│   ├── index.html              #   page structure
│   ├── styles.css              #   dark theme, rising blue glow, wave pill
│   └── app.js                  #   mic, silence detection, auto-send, playback
├── scripts/download_voice.py   # Downloads the Piper voice model
├── models/                     # Downloaded voice files go here (not in git)
├── docs/                       # Detailed documentation (see below)
├── .claude/rules/              # 5 rule files: coding, security, architecture, testing, docs
├── CLAUDE.md                   # Project guide (for AI assistants and humans)
├── skills.md                   # Step-by-step recipes for common tasks
├── requirements.txt            # Runtime dependencies
├── requirements-dev.txt        # + test and code-quality tools
├── pyproject.toml              # Config for pytest, ruff, mypy
└── .env.example                # Template for your settings
```

---

## 🚀 Installation & setup

**You need:** Python 3.11+ and a free Groq API key. You do not need a GPU.

```bash
# 1. Go into the project folder
cd voice-chatbot

# 2. Create and activate a virtual environment (an isolated place for packages)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 3. Install dependencies (dev version includes the test tools)
pip install -r requirements-dev.txt

# 4. Download the Piper voice (~60 MB) into models/
python scripts/download_voice.py

# 5. Create your settings file and add your Groq key
copy .env.example .env          # Windows   (cp on macOS / Linux)
#    then edit .env:  GROQ_API_KEY=gsk_...   (get one at https://console.groq.com/keys)
```

The Whisper model (~140 MB for `base`) downloads **automatically** on the first request.

---

## ▶️ Running

```bash
uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000`. The first request takes longer because the
models are loaded (and downloaded on the very first run). After that it is fast.

### Demo in the browser (recommended)

Open a **second** terminal:

```bash
python -m http.server 5500 --directory client
```

Then open **http://localhost:5500** and click *Start talking*. Use it hands-free, like
Gemini Live:

- **Just talk.** When you pause for about 1.2 seconds, your speech is sent automatically.
- The **blue glow** rises from the bottom, and the **wave pill** grows and shrinks with your voice and the bot's voice.
- 🎤 **Mic button**: mutes your microphone so the bot can finish speaking without being interrupted.
- **Tap the wave** while the bot is speaking to interrupt it.
- ✕ **End button**: stops the conversation and releases the microphone.

How it works is explained in [docs/FRONTEND.md](docs/FRONTEND.md).

### Interactive API docs

Open **http://localhost:8000/docs**. Expand `POST /chat`, click *Try it out*, upload an
audio file, and click *Execute*.

---

## 📡 API usage

### `POST /chat`

| Part | Type | Required | Description |
|------|------|----------|-------------|
| `audio` | file (multipart) | ✅ | Voice recording: wav, mp3, webm, ogg, m4a, flac. Max 10 MB |
| `session_id` | form text | ❌ | Any id (`A-Z a-z 0-9 _ -`, max 64). Reuse it to keep conversation context |

**Success (200):** the body is the spoken reply as `audio/wav`. Two headers hold the
text versions, URL-encoded:
- `X-Transcript`: what you said
- `X-Reply-Text`: what the bot answered

**Example with curl:**

```bash
curl -X POST http://localhost:8000/chat \
     -F "audio=@question.wav;type=audio/wav" \
     -F "session_id=demo-1" \
     --output reply.wav -D -
```

**Errors** always use the same JSON shape:

```json
{ "error": { "code": "unsupported_media_type", "message": "Unsupported audio type 'text/plain'..." } }
```

| Status | `code` | When |
|--------|--------|------|
| 400 | `invalid_audio` | File is empty or not decodable audio |
| 413 | `audio_too_large` | File is bigger than `MAX_AUDIO_BYTES` |
| 415 | `unsupported_media_type` | Not an allowed audio type |
| 422 | `no_speech_detected` / `validation_error` | Silence, or a missing/invalid field |
| 429 | `rate_limit_exceeded` | Too many requests (see `Retry-After` header) |
| 502 | `llm_unavailable` | Groq failed (bad key, quota, network) |
| 500 | `speech_synthesis_failed` / `internal_error` | Something broke on the server |

---

## ⚙️ Configuration

All settings come from environment variables or `.env`. Only `GROQ_API_KEY` is required.
See [`.env.example`](.env.example) and [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for
the full list.

---

## 🧪 Testing

```bash
pytest                 # run all 44 tests (≈1 second, no internet or models needed)
ruff check .           # lint
ruff format .          # auto-format
mypy app               # type check
```

The tests replace the AI models with small fakes, so they are fast and free.
See [docs/TESTING.md](docs/TESTING.md).

---

## 📚 More documentation

| Document | What's inside |
|----------|---------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, request flow, design patterns |
| [docs/PIPELINE.md](docs/PIPELINE.md) | How STT → LLM → TTS works in detail |
| [docs/FRONTEND.md](docs/FRONTEND.md) | Hands-free client: silence detection, states, animations |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every environment variable explained |
| [docs/SECURITY.md](docs/SECURITY.md) | Validation, rate limiting, CORS, secrets |
| [docs/TESTING.md](docs/TESTING.md) | Test strategy and how to add tests |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Why each technology/design was chosen |
| [docs/PRESENTATION_GUIDE.md](docs/PRESENTATION_GUIDE.md) | How to demo & likely mentor questions |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common problems and fixes |
| [CLAUDE.md](CLAUDE.md) | One-page overview of the whole project |
