# Skills: recipes for common tasks

Short, step-by-step recipes for the things you will most likely want to do with this project.
Each recipe lists exactly which files to touch.

---

## 1. Change the bot's personality

1. In `.env`, set `SYSTEM_PROMPT="You are a pirate. Answer in 2 short sentences."`
2. Restart the server.
3. Keep the instruction "no markdown, lists or emojis". TTS reads symbols out loud.

## 2. Change the voice (or language)

1. Pick a voice at https://rhasspy.github.io/piper-samples/ (e.g. `en_GB-alan-medium`).
2. `python scripts/download_voice.py en_GB-alan-medium`
3. In `.env`: `PIPER_VOICE_PATH=models/en_GB-alan-medium.onnx`
4. For a non-English voice, Whisper already detects the language automatically. Also
   update `SYSTEM_PROMPT` to "Answer in <language>".

## 3. Make speech recognition more accurate (or faster)

- More accurate: `WHISPER_MODEL_SIZE=small` (slower, ~460 MB).
- Faster: `WHISPER_MODEL_SIZE=tiny` (less accurate, ~75 MB).
- English only: `base.en` / `small.en` are a bit more accurate for English.
- NVIDIA GPU: `WHISPER_DEVICE=cuda` and `WHISPER_COMPUTE_TYPE=float16`.

## 4. Use a different Groq model

1. See available models at https://console.groq.com/docs/models.
2. In `.env`: `GROQ_MODEL=openai/gpt-oss-120b` (smarter, slightly slower).
3. Groq retires models from time to time. If you get a 502 and the server log says `model_not_found`,
   list the current models (see `docs/TROUBLESHOOTING.md`) and pick another one.

## 5. Change limits

| Want | Setting |
|------|---------|
| Allow longer recordings | `MAX_AUDIO_BYTES=20971520` (20 MB) |
| More requests per minute | `RATE_LIMIT_REQUESTS=30` |
| Longer memory | `MAX_HISTORY_TURNS=10` |
| No memory | `MAX_HISTORY_TURNS=0` |

## 6. Add a new setting

1. Add a typed field with a default to `Settings` in `app/config.py`.
2. Pass it into the service from `app/api/dependencies.py`.
3. Document it in `.env.example` and `docs/CONFIGURATION.md`.
4. Add a test.

## 7. Add a new error type

1. In `app/core/errors.py`, subclass `VoiceBotError` and set `status_code` and `code`.
2. Raise it from the service.
3. Add it to the error table in `README.md`.
4. Add an endpoint test that checks the status and `code`.
   (No handler change is needed. `app/main.py` handles all `VoiceBotError`s.)

## 8. Swap a provider (e.g. another TTS engine)

1. Create `app/services/my_tts.py` with a class that has `synthesize(self, text: str) -> bytes`.
2. In `app/api/dependencies.py`, build it instead of `TextToSpeech`.
3. Nothing else changes. The pipeline only needs that one method (the `TextToSpeechEngine` Protocol).

## 9. Run all quality checks

```bash
ruff format . && ruff check . && mypy app && pytest
```

## 10. Test the real pipeline without a microphone

```bash
python -c "from app.services.tts import TextToSpeech; open('q.wav','wb').write(TextToSpeech('models/en_US-lessac-medium.onnx').synthesize('What is the capital of France?'))"
curl -X POST http://localhost:8000/chat -F "audio=@q.wav;type=audio/wav" --output reply.wav
```
Piper speaks the question, and the API answers it. Play `reply.wav` to hear the answer.
