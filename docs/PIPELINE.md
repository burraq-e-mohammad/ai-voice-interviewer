# The STT → LLM → TTS pipeline

`app/services/pipeline.py` runs three steps for every request. Here is what each step
does, which library does it, and how.

```
 recording.webm ──► [1] SpeechToText ──► "what's the tallest mountain?"
                                                    │
                       history (if session_id) ───► [2] LLMService ──► "Mount Everest, at about 8,849 metres..."
                                                                                  │
                                                         reply.wav ◄── [3] TextToSpeech
```

Typical timings on a laptop CPU (warm models, short question):
STT ≈ 0.5–1.5 s, LLM ≈ 0.3–1 s (Groq is very fast), TTS ≈ 0.3–1 s.

---

## Step 1: Speech-to-Text with faster-whisper (`app/services/stt.py`)

**What is Whisper?** It is an open-source speech recognition model from OpenAI, trained on 680,000
hours of audio. It handles accents, background noise, and ~99 languages.

**What is faster-whisper?** It is a re-implementation of Whisper on *CTranslate2*, an optimised
inference engine. It gives the same accuracy, is up to 4× faster, and uses less memory. With `int8`
*quantisation* (storing weights as 8-bit integers instead of 32-bit floats), it runs well on
an ordinary CPU.

**How our code uses it:**
1. `WhisperModel("base", device="cpu", compute_type="int8")` is created once.
   On the first run it downloads the model from Hugging Face into your cache folder.
2. `model.transcribe(BytesIO(audio_bytes), beam_size=1, vad_filter=True)`
   - The audio is decoded by **FFmpeg** (through the `av` package). That is why the
     browser's webm/ogg recordings work without converting them first.
   - The audio is resampled to 16 kHz mono, the format Whisper expects.
   - **VAD** (Voice Activity Detection, Silero model) cuts out silence. This makes it faster and
     stops Whisper from "hallucinating" text in silence.
   - `beam_size=1` uses greedy decoding, which is the fastest. That is fine for chat.
3. The result is a lazy generator of *segments*. We join their text.
4. No text → `NoSpeechDetectedError` (422). A decoding failure → `InvalidAudioError` (400).

## Step 2: Answer with Groq (`app/services/llm.py`)

**What is Groq?** It is a cloud service that runs open LLMs (Qwen, OpenAI's gpt-oss and others) on its own
LPU chips, which are much faster than typical GPU hosting. Its free tier is enough for a demo.

**How our code uses it:**
1. It builds the message list in the standard chat format:
   ```
   [ {system: "You are a friendly voice assistant... short sentences, no markdown"},
     ...previous user/assistant messages for this session...,
     {user: "<transcript>"} ]
   ```
2. It calls `client.chat.completions.create(model=..., messages=..., max_tokens=300, temperature=0.7)`.
3. It returns `choices[0].message.content`.

**Why the special system prompt?** The answer will be *spoken*. Markdown (`**bold**`,
bullet lists), emojis, and long paragraphs sound terrible through TTS, so we ask for short, plain sentences.

**Errors:** any SDK error (wrong key, quota, network, timeout) → `LLMServiceError` (502).
The real reason is logged on the server and never sent to the client.

## Step 3: Text-to-Speech with Piper (`app/services/tts.py`)

**What is Piper?** It is a fast, local neural TTS system. Each voice is a VITS model exported to
**ONNX** (a portable model format) and runs with `onnxruntime` on the CPU.

**How it turns text into sound:**
1. **Phonemisation**: espeak-ng (bundled) converts text into phonemes (sound units),
   e.g. "hello" → `həlˈoʊ`.
2. **Neural synthesis**: the VITS model turns the phonemes into a raw audio waveform.
3. **WAV writing**: `voice.synthesize_wav(text, wav_file)` writes 16-bit mono PCM audio
   (22,050 Hz for "medium" voices) into an in-memory `BytesIO` buffer, so no temp files are needed.

Voices are downloaded by `scripts/download_voice.py` into `models/`: `<voice>.onnx`
(the model) plus `<voice>.onnx.json` (its config: sample rate, phoneme map).

## Conversation memory (`app/services/memory.py`)

If the client sends `session_id`:
- **before** step 2, the pipeline loads the last `MAX_HISTORY_TURNS` exchanges and passes them to the LLM;
- **after** step 3 succeeds, it saves the new (question, answer) pair.

So "Who wrote Hamlet?" → "Shakespeare" → "When was **he** born?" works, because the LLM
sees the earlier exchange. Without `session_id`, each request stands alone.

## Why sequential and not streaming?

A production voice assistant streams: it starts speaking while the LLM is still writing. That
needs WebSockets and much more complex code. The brief asked for one simple `POST /chat`
endpoint, and the total delay (~2–4 s) is fine for a demo. See `docs/DECISIONS.md`.
