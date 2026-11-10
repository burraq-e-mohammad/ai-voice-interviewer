# 🎙️ AI Voice Interviewer

An interactive, hands-free voice interview simulator powered by **Faster-Whisper** (local Speech-to-Text), **Google Gemini** (`gemini-3.5-flash-lite`, with optional Groq fallback), and **Piper** (offline neural Text-to-Speech), served with **FastAPI** and a vanilla HTML/CSS/JS web client.

```
🎤 Candidate Voice ──► Faster-Whisper STT ──► Gemini Interviewer ──► Piper TTS ──► 🔊 Spoken Question
                         (local CPU)          (resume + JD + role)    (offline WAV)
```

---

## ✨ Features

- **Hands-Free Voice Client:** Web Audio waveform visualizer, automatic silence detection (VAD), barge-in reply interruption, and dual countdown timers (`30:00` total interview / `01:30` per question).
- **Resume Parsing & Candidate Profiling:** Upload a **PDF, DOCX, or TXT** resume alongside candidate name, seniority level (`Junior` to `Lead / Staff`), target company, skills, and job description.
- **Structured Multi-Turn Interview:** Conducts up to `20` targeted technical and behavioral rounds (configurable via `MAX_INTERVIEW_TURNS`) grounded in the candidate's resume projects and job requirements.
- **Automated Performance Scorecard:** Generates an end-of-session Markdown assessment with an overall `X.X/10` score, executive summary, strengths, technical gaps, and coaching tips.
- **Built-In API Guardrails:** Audio MIME-type allow-list, upload size cap (`15 MB`), per-IP sliding-window rate limiting, and sanitized error responses.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python `3.11+`
- A Google Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) (or a Groq API key if using `LLM_PROVIDER=groq`)

### 2. Setup
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate

pip install -r requirements.txt
python scripts/download_voice.py          # Downloads Piper voice into models/

copy .env.example .env                    # macOS / Linux: cp .env.example .env
# Edit .env and set GEMINI_API_KEY
```

### 3. Start the Backend API
```bash
uvicorn app.main:app --port 8000
```
The API runs at `http://localhost:8000` (interactive Swagger docs at `http://localhost:8000/docs`).

### 4. Start the Web Client
In a second terminal:
```bash
python -m http.server 5500 --directory client
```
Open **`http://localhost:5500`** in Chrome or Edge and allow microphone access.

---

## 🛠️ API Endpoints

| Method & Path | Purpose |
| :--- | :--- |
| `POST /session/parse-resume` | Extracts raw text from uploaded PDF, DOCX, or TXT resumes (`filename`, `resume_text`, `char_count`, `word_count`). |
| `POST /session/start` | Registers the candidate profile and returns `session_id`, `opening_text`, and spoken `opening_audio_base64`. |
| `POST /chat` | Accepts uploaded speech audio (`wav`, `webm`, `mp3`, etc.) + `session_id`, transcribes via Faster-Whisper, generates the next interviewer question, and returns `audio/wav` with metadata headers (`X-Transcript`, `X-Reply-Text`, `X-Turn`, `X-Max-Turns`, `X-Is-Complete`). |
| `POST /session/evaluate` | Evaluates the session transcript against the target role, job description, and resume, returning `score` and `feedback_markdown`. |

---

## 📂 Project Structure

```text
ai-voice-interviewer/
├── app/
│   ├── api/            # FastAPI routes and dependency injection
│   ├── core/           # Validation, custom exceptions, sliding-window rate limiter
│   ├── models/         # Pydantic & dataclass schemas
│   ├── services/       # STT (faster-whisper), LLM (Gemini/Groq), TTS (Piper), memory, pipeline
│   ├── config.py       # Typed environment configuration
│   └── main.py         # FastAPI app entrypoint, CORS, exception handlers
├── client/             # Browser UI (HTML, CSS, Web Audio VAD client)
├── models/             # Downloaded Piper .onnx voice files (gitignored)
├── scripts/            # Voice downloader utility
├── tests/              # Offline pytest suite using service fakes
├── .env.example        # Environment variable template
├── pyproject.toml      # Tooling configuration (pytest, ruff, mypy)
└── requirements.txt    # Runtime Python dependencies
```

---

## 🧪 Running Tests

Install dev dependencies (`pytest`, `httpx`, `ruff`, `mypy`) and run the offline test suite (uses fake STT/LLM/TTS engines, so no API keys or model files are required):

```bash
pip install -r requirements-dev.txt
pytest
```
