# Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ValidationError: groq_api_key Field required` at startup | No key configured | `copy .env.example .env` and set `GROQ_API_KEY` |
| 502 `llm_unavailable` ("The AI service is currently unavailable") | Wrong/expired key, Groq quota hit, no internet, **or the model was retired** | Read the **server terminal**: it logs the real reason (the client only gets a friendly message on purpose) |
| Server log: `404 ... model_not_found` | Groq retired the model in `GROQ_MODEL` | List current models: `python -c "from app.config import get_settings as g; from groq import Groq; print([m.id for m in Groq(api_key=g().groq_api_key.get_secret_value()).models.list().data])"`, then set `GROQ_MODEL` in `.env` and restart |
| Hands-free client sends too early / cuts me off | Pauses longer than 1.2 s | Raise `SILENCE_MS` at the top of `client/app.js` |
| Hands-free client never sends / sends on background noise | Mic too quiet / room too loud | Adjust `MIN_THRESHOLD` in `client/app.js` (lower = more sensitive) |
| 500 and log says `Piper voice not found` | Voice not downloaded | `python scripts/download_voice.py` |
| Every request returns 400 `invalid_audio`, log shows `unexpected keyword argument 'metadata_errors'` | `av` 17+ installed (breaks faster-whisper 1.2.x) | `pip install "av<17"` |
| 422 `no_speech_detected` | Silence, a mic that's too quiet, or the wrong input device | Speak closer to the mic. Check the OS input device |
| First request takes 10–60 s | Models are loading (and downloading on the first ever run) | Normal. Do a warm-up request before demos |
| Browser: "Microphone access failed" | Page not served from localhost/https, or permission denied | Serve with `python -m http.server 5500 --directory client` and allow the mic |
| Browser: CORS error in the console | Page origin not in `CORS_ORIGINS` | Open the page at `http://localhost:5500`, or add your origin to `CORS_ORIGINS` |
| 429 `rate_limit_exceeded` | More than 10 requests/min | Wait `Retry-After` seconds, or raise `RATE_LIMIT_REQUESTS` |
| 413 `audio_too_large` | Recording over 10 MB | Record shorter clips, or raise `MAX_AUDIO_BYTES` |
| `ModuleNotFoundError: app` when running pytest | Running from the wrong folder | Run `pytest` from the project root |
| `.venv\Scripts\activate` is blocked in PowerShell | Script execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or use cmd |
| Hugging Face download fails | Network/firewall | Retry, or set `HF_ENDPOINT` to a mirror. Models are cached after one success |
