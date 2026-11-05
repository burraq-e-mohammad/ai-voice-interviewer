# Frontend: the hands-free voice client

The `client/` folder holds a small web page that talks to `POST /chat` hands-free, in the
style of Gemini Live. It is **not** part of the API. It is a separate static site (plain HTML/CSS/JS, no
build step), served with `python -m http.server 5500 --directory client`.

| File | Job |
|------|-----|
| `index.html` | Page structure: start screen, live screen, glow, wave pill, buttons |
| `styles.css` | Dark theme, rising blue glow, pill and button styles |
| `app.js` | Microphone, silence detection, API calls, playback, wave drawing |

## The conversation loop (state machine)

```
 LISTENING ──(voice detected)──► RECORDING
     ▲                               │ (quiet for 1.2 s)
     │                               ▼
 SPEAKING ◄──(reply arrives)──── THINKING   ── POST /chat ──► server
     │
     └──(reply ends / wave tapped)──► LISTENING
```

The current state is stored on `<body data-state="...">`, so the CSS can style each state
(for example, the glow pulses while `thinking`).

## Sending on silence (Voice Activity Detection)

1. `getUserMedia` opens the mic with **echo cancellation**, so the bot's voice from the
   speakers is not heard as the user.
2. A Web Audio `AnalyserNode` provides the raw samples. Every animation frame (~60×/s),
   `measureLoudness()` computes the **RMS** (root mean square), which is the average loudness.
3. **Threshold:** `max(MIN_THRESHOLD, noiseFloor × 2.5)`. While nobody speaks, `noiseFloor`
   slowly learns the room's background noise, so a noisy room needs louder speech.
4. Loudness above the threshold → start a `MediaRecorder` (state `RECORDING`).
5. Quiet for `SILENCE_MS` (1200 ms) → stop and send. If the speech was shorter than
   `MIN_SPEECH_MS` (350 ms), it was a cough or click, so it is thrown away.
6. Speech longer than 30 s is sent anyway (`MAX_UTTERANCE_MS`).
7. While the bot is `THINKING` or `SPEAKING`, the mic is not checked, so the bot can't
   interrupt itself.

## Buttons

| Control | Effect |
|---------|--------|
| 🎤 Mic | Toggles **mute**. It disables the mic track (the browser sends silence) and cancels a half-recorded sentence. The bot keeps speaking. Listening resumes after you unmute. |
| ✕ End | Aborts any request, stops playback, releases the mic, and returns to the start screen. A new start gets a new `session_id` (fresh memory). |
| Wave pill | While the bot is speaking: tap to **interrupt** and start listening again. |

## The animations

- One CSS variable, `--level` (0–1), is updated every frame from the loudness of the **mic**
  (while listening) or the **bot's voice** (while speaking, measured by a second analyser on the
  playback). In the `THINKING` state it is a gentle sine pulse.
- `.glow` is a blurred blue gradient fixed to the bottom. It slides up (`translateY(100%) → 0`)
  when the conversation starts, and its height and opacity grow with `--level`.
- `.wave-pill` scales with `--level`. Inside, a `<canvas>` draws three translucent blue
  waves. Each one is mirrored around the middle line, tapered at the edges, and blended with
  `"lighter"` so that overlaps glow. Their amplitude follows `--level`.
- `prefers-reduced-motion` turns off the transitions for users who want less motion.

## How the reply is played

The response body (WAV) is decoded with `audioCtx.decodeAudioData` and played through an
`AudioBufferSourceNode → outAnalyser → speakers`. Routing the audio through the analyser is
what lets the wave "dance" to the bot's voice. The text comes from the `X-Transcript` and
`X-Reply-Text` headers (URL-decoded) and is inserted with `textContent` (XSS-safe).

## Error handling

| Situation | What the user sees |
|-----------|--------------------|
| `no_speech_detected` (422) | Nothing. The client quietly goes back to listening |
| Any other API error | The friendly server message, in red, in place of the reply |
| Server not running | "Can't reach the server. Is it running on http://localhost:8000?" |
| Mic permission denied | Message on the start screen |

## Tuning (constants at the top of `app.js`)

| Constant | Default | Change it when... |
|----------|---------|-------------------|
| `API_URL` | `http://localhost:8000/chat` | the API runs elsewhere |
| `SILENCE_MS` | 1200 | it cuts you off (raise it) or feels slow (lower it) |
| `MIN_SPEECH_MS` | 350 | short words like "yes" are ignored (lower it) |
| `MIN_THRESHOLD` | 0.015 | it misses quiet speech (lower it) or triggers on noise (raise it) |

Note: every utterance is one `/chat` request, so the server's rate limit (10/min by default)
applies. A fast back-and-forth conversation will not get near it.
