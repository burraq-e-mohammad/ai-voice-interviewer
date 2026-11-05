# Design decisions

Each important choice, the alternatives, and the reasoning, so you can defend it.

## faster-whisper for Speech-to-Text
**Decision:** faster-whisper, `base` model, `int8`, CPU.
**Alternatives:** original `openai-whisper` (needs PyTorch, slower), Vosk (lighter but less
accurate), whisper.cpp (needs C++ build tools on Windows), cloud STT (not free/open).
**Why:** it has the same accuracy as Whisper, is up to 4× faster, installs with `pip` (no PyTorch),
decodes any audio format through bundled FFmpeg, and has an MIT licence.
**Trade-off:** the first run downloads ~145 MB. `base` sometimes mishears unusual words (use `small` for better accuracy).

## Piper for Text-to-Speech
**Decision:** `piper-tts` with the `en_US-lessac-medium` voice.
**Alternatives:** Coqui XTTS / Kokoro (higher quality but need PyTorch and are slower on CPU),
pyttsx3 (uses robotic OS voices, not a model), cloud TTS (not free/open).
**Why:** it runs offline, faster than real time on a CPU, sounds natural, is a pure pip install,
and has many voices and languages.
**Trade-off:** the `piper-tts` package is GPL-3.0. That is fine for a learning/demo project, but check
the licence before shipping a closed-source product. Voice quality is good but below the largest models.

## Groq for the LLM
**Decision:** Groq with `qwen/qwen3.8-27b`.
**Why:** it is the brief's requirement. It is also extremely fast (low latency is critical when a user waits
in silence), has a free tier, serves open models, and has an official Python SDK.
**Trade-off:** it needs internet and a key, and the free tier has rate limits.

## One endpoint, audio in → audio out, text in headers
**Decision:** `POST /chat` takes a multipart upload and returns `audio/wav`. The text versions go in
URL-encoded `X-Transcript` / `X-Reply-Text` headers.
**Alternatives:** return JSON with base64 audio (33% bigger, harder to play), or add a second endpoint
for the text (this breaks the one-endpoint rule).
**Why:** the response *is* the audio, so a client can play it directly. The headers are an optional extra.
**Trade-off:** headers are ASCII-only, so the text must be URL-encoded (the client decodes it).

## Synchronous request/response, not streaming
**Decision:** the full pipeline runs, then one response is sent.
**Alternative:** WebSockets with streaming STT/LLM/TTS (lower latency).
**Why:** it is far simpler to build, test, and explain, and it fits the one-POST-endpoint requirement.
**Trade-off:** the user waits for the whole pipeline (~2–4 s).

## Run the pipeline in a thread pool
**Decision:** `await run_in_threadpool(pipeline.run, ...)` in an `async def` route.
**Why:** the models block the CPU. Calling them directly in async code would freeze the server for every
other user. A thread pool keeps the event loop responsive.

## Lazy model loading with `lru_cache`
**Decision:** models load on the first request, not at startup.
**Why:** startup is instant, and tests never trigger loading.
**Trade-off:** the first request is slow (do one warm-up request before a demo).

## Conversation memory: optional, in RAM, capped
**Decision:** keep the last 5 exchanges per `session_id` in memory, with at most 1000 sessions (LRU).
**Why:** follow-up questions ("and how old is he?") need context. It is ~50 lines with no database. It is
optional, so stateless clients still work. The caps prevent memory abuse.
**Trade-off:** it is lost on restart and not shared across processes.

## Custom rate limiter instead of a library
**Decision:** a ~40-line sliding-window limiter.
**Alternative:** `slowapi`.
**Why:** it has no extra dependency, is easy to read and explain, and is fully testable with a fake clock.
**Trade-off:** it is in memory only. For production, use Redis/slowapi or a gateway.

## Pin `av<17`
**Decision:** `requirements.txt` pins `av>=12,<17`.
**Why:** faster-whisper 1.2.x calls `av.open(..., metadata_errors=...)`, which av 17+ removed. With a newer
`av`, every transcription fails. We found this during real testing.

## Protocols and dependency injection
**Decision:** services receive their engines through their constructors. The pipeline depends on Protocols.
**Why:** tests run in ~1 second with fakes, and any provider can be swapped by changing one wiring file.
