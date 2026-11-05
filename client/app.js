/*
  Hands-free voice client logic.

  The conversation is a simple loop of states:

      LISTENING ──(you start talking)──► RECORDING
          ▲                                  │ (you pause for SILENCE_MS)
          │                                  ▼
      SPEAKING ◄──(reply arrives)────── THINKING  (POST /chat)
          │
          └──(reply finished)──► back to LISTENING

  How "send on silence" works (voice activity detection, VAD):
    The Web Audio API gives us the raw microphone signal. ~60 times per second
    we measure its loudness (RMS = root mean square). Loudness above a threshold
    counts as speech. Once speech has started, if it stays quiet for SILENCE_MS,
    we stop recording and send the audio to the server automatically.
*/

"use strict";

// ---------- Settings you can tweak ----------
const API_URL = "http://localhost:8000/chat";
const SILENCE_MS = 1200; // pause length that means "I'm done talking"
const MIN_SPEECH_MS = 350; // shorter sounds (a cough, a click) are ignored
const MAX_UTTERANCE_MS = 30000; // safety cap: send after 30 s no matter what
const MIN_THRESHOLD = 0.015; // minimum loudness that counts as speech

const State = {
  IDLE: "idle",
  LISTENING: "listening",
  RECORDING: "recording",
  THINKING: "thinking",
  SPEAKING: "speaking",
};

const STATUS_TEXT = {
  idle: "",
  listening: "Listening…",
  recording: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking… tap the wave to interrupt",
};

// ---------- Page elements ----------
const $ = (id) => document.getElementById(id);
const startScreen = $("startScreen");
const liveScreen = $("liveScreen");
const startBtn = $("startBtn");
const startError = $("startError");
const statusEl = $("status");
const userCaption = $("userCaption");
const botCaption = $("botCaption");
const micBtn = $("micBtn");
const endBtn = $("endBtn");
const wavePill = $("wavePill");
const canvas = $("waveCanvas");
const ctx = canvas.getContext("2d");

// ---------- Conversation state ----------
let state = State.IDLE;
let muted = false;
let sessionId = null; // lets the server remember earlier messages

let audioCtx = null; // Web Audio "engine"
let micStream = null; // the live microphone
let micAnalyser = null; // measures microphone loudness
let outAnalyser = null; // measures the bot's voice loudness (for the animation)
let recorder = null; // records one utterance
let chunks = [];
let replySource = null; // the reply audio that is currently playing
let abortController = null; // lets us cancel an in-flight request

let speechStartedAt = 0;
let lastVoiceAt = 0;
let noiseFloor = 0.01; // learned background-noise loudness
let level = 0; // smoothed loudness 0..1 that drives the animations
let animationId = null;
const sampleBuffer = new Float32Array(1024);

// =====================================================================
// Start / end
// =====================================================================

startBtn.addEventListener("click", startConversation);
endBtn.addEventListener("click", endConversation);
micBtn.addEventListener("click", toggleMute);
wavePill.addEventListener("click", interruptReply);

async function startConversation() {
  startError.textContent = "";
  try {
    // echoCancellation stops the mic from hearing the bot's own voice from the speakers.
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (err) {
    startError.textContent = "Microphone access was blocked. Allow it in the browser and try again.";
    return;
  }

  // The AudioContext must be created after a click (browser autoplay rules).
  audioCtx = new AudioContext();

  micAnalyser = audioCtx.createAnalyser();
  micAnalyser.fftSize = 1024;
  // Note: the mic is NOT connected to the speakers, which would cause feedback.
  audioCtx.createMediaStreamSource(micStream).connect(micAnalyser);

  outAnalyser = audioCtx.createAnalyser();
  outAnalyser.fftSize = 1024;
  outAnalyser.connect(audioCtx.destination);

  sessionId = crypto.randomUUID();
  userCaption.textContent = "";
  botCaption.textContent = "";
  startScreen.hidden = true;
  liveScreen.hidden = false;
  resizeCanvas();
  setState(State.LISTENING);
  animationId = requestAnimationFrame(tick);
}

function endConversation() {
  cancelAnimationFrame(animationId);
  abortController?.abort();
  discardRecording();
  stopReply();
  micStream?.getTracks().forEach((track) => track.stop()); // turns off the mic light
  audioCtx?.close();
  micStream = audioCtx = null;
  setMuted(false);
  level = 0;
  document.documentElement.style.setProperty("--level", "0");
  setState(State.IDLE);
  liveScreen.hidden = true;
  startScreen.hidden = false;
}

// =====================================================================
// Mute and interrupt
// =====================================================================

function toggleMute() {
  setMuted(!muted);
}

function setMuted(value) {
  muted = value;
  // Disabling the track makes the mic send silence. The browser keeps the permission.
  micStream?.getAudioTracks().forEach((track) => (track.enabled = !muted));
  if (muted && state === State.RECORDING) discardRecording(); // don't send half a sentence
  micBtn.setAttribute("aria-pressed", String(muted));
  micBtn.title = muted ? "Unmute microphone" : "Mute microphone";
  document.body.classList.toggle("muted", muted);
  updateStatus();
}

function interruptReply() {
  if (state === State.SPEAKING) {
    stopReply();
    setState(State.LISTENING);
  }
}

// =====================================================================
// The animation loop: runs every frame (~60 times per second)
// =====================================================================

function tick(now) {
  let target = 0;

  if (state === State.LISTENING || state === State.RECORDING) {
    const rms = measureLoudness(micAnalyser);
    if (!muted) detectSpeech(rms, now);
    target = muted ? 0 : Math.min(1, rms * 10);
  } else if (state === State.SPEAKING) {
    target = Math.min(1, measureLoudness(outAnalyser) * 6);
  } else if (state === State.THINKING) {
    target = 0.25 + 0.15 * Math.sin(now / 250); // gentle "thinking" pulse
  }

  // Smooth the value so the animation glides instead of jittering.
  level += (target - level) * 0.18;
  document.documentElement.style.setProperty("--level", level.toFixed(3));
  drawWave(now);

  animationId = requestAnimationFrame(tick);
}

/** Loudness of the latest audio samples (RMS, about 0..0.5 for speech). */
function measureLoudness(analyser) {
  analyser.getFloatTimeDomainData(sampleBuffer);
  let sum = 0;
  for (const sample of sampleBuffer) sum += sample * sample;
  return Math.sqrt(sum / sampleBuffer.length);
}

// =====================================================================
// Voice activity detection: decide when to start and stop recording
// =====================================================================

function detectSpeech(rms, now) {
  // The threshold adapts to the room: a noisy room needs a higher bar.
  const threshold = Math.max(MIN_THRESHOLD, noiseFloor * 2.5);
  const isVoice = rms > threshold;

  if (state === State.LISTENING) {
    if (isVoice) {
      startRecording(now);
    } else {
      // Slowly learn the background noise level while nobody is talking.
      noiseFloor = noiseFloor * 0.98 + rms * 0.02;
    }
    return;
  }

  // We are RECORDING.
  if (isVoice) lastVoiceAt = now;
  const silentFor = now - lastVoiceAt;
  const spokeFor = lastVoiceAt - speechStartedAt;

  if (silentFor > SILENCE_MS || now - speechStartedAt > MAX_UTTERANCE_MS) {
    if (spokeFor < MIN_SPEECH_MS) {
      discardRecording(); // just a short noise, not speech
      setState(State.LISTENING);
    } else {
      finishRecordingAndSend();
    }
  }
}

function startRecording(now) {
  chunks = [];
  recorder = new MediaRecorder(micStream);
  recorder.addEventListener("dataavailable", (event) => chunks.push(event.data));
  recorder.start();
  speechStartedAt = lastVoiceAt = now;
  setState(State.RECORDING);
}

function finishRecordingAndSend() {
  const activeRecorder = recorder;
  recorder = null;
  setState(State.THINKING);
  // "stop" fires after the last chunk of data is delivered.
  activeRecorder.addEventListener("stop", () => {
    sendAudio(new Blob(chunks, { type: activeRecorder.mimeType }));
  });
  activeRecorder.stop();
}

function discardRecording() {
  if (recorder && recorder.state !== "inactive") recorder.stop(); // no "stop" listener, so nothing is sent
  recorder = null;
  chunks = [];
  if (state === State.RECORDING) setState(State.LISTENING);
}

// =====================================================================
// Talking to the API
// =====================================================================

async function sendAudio(blob) {
  const form = new FormData();
  form.append("audio", blob, "speech.webm");
  form.append("session_id", sessionId);
  abortController = new AbortController();

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      body: form,
      signal: abortController.signal,
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      // Silence or noise that had no words: just keep listening quietly.
      if (body?.error?.code === "no_speech_detected") {
        setState(State.LISTENING);
        return;
      }
      throw new Error(body?.error?.message || `Server error (${response.status})`);
    }

    // The text arrives URL-encoded in headers. The body is the WAV audio.
    userCaption.textContent = decodeURIComponent(response.headers.get("X-Transcript") || "");
    showBotText(decodeURIComponent(response.headers.get("X-Reply-Text") || ""));

    const audioData = await response.arrayBuffer();
    if (state !== State.THINKING) return; // user ended or interrupted meanwhile
    playReply(await audioCtx.decodeAudioData(audioData));
  } catch (err) {
    if (err.name === "AbortError") return; // we cancelled it on purpose
    const message =
      err instanceof TypeError
        ? "Can't reach the server. Is it running on http://localhost:8000?"
        : err.message;
    showBotText(message, true);
    setState(State.LISTENING);
  } finally {
    abortController = null;
  }
}

function playReply(audioBuffer) {
  replySource = audioCtx.createBufferSource();
  replySource.buffer = audioBuffer;
  // Route through the analyser so the wave can "dance" to the bot's voice.
  replySource.connect(outAnalyser);
  replySource.addEventListener("ended", () => {
    replySource = null;
    if (state === State.SPEAKING) setState(State.LISTENING);
  });
  replySource.start();
  setState(State.SPEAKING);
}

function stopReply() {
  if (replySource) {
    try {
      replySource.stop();
    } catch {
      /* already stopped */
    }
    replySource = null;
  }
}

// =====================================================================
// UI helpers
// =====================================================================

function setState(newState) {
  state = newState;
  document.body.dataset.state = newState; // CSS uses this for state-specific styles
  updateStatus();
}

function updateStatus() {
  const listening = state === State.LISTENING || state === State.RECORDING;
  statusEl.textContent = muted && listening ? "Microphone is off" : STATUS_TEXT[state];
}

function showBotText(text, isError = false) {
  // textContent (never innerHTML), so server text can't inject HTML or scripts.
  botCaption.textContent = text;
  botCaption.classList.toggle("error", isError);
}

// =====================================================================
// Drawing the blue wave inside the pill
// =====================================================================

const WAVE_LAYERS = [
  { color: [26, 115, 232], alpha: 0.55, freq: 1.2, speed: 0.0021, phase: 0 },
  { color: [66, 133, 244], alpha: 0.6, freq: 1.9, speed: -0.0028, phase: 2.1 },
  { color: [138, 180, 248], alpha: 0.7, freq: 2.6, speed: 0.0034, phase: 4.2 },
];

function resizeCanvas() {
  // Draw at the screen's real pixel density so the wave stays sharp.
  const dpr = window.devicePixelRatio || 1;
  canvas.width = canvas.clientWidth * dpr;
  canvas.height = canvas.clientHeight * dpr;
}
window.addEventListener("resize", resizeCanvas);

function drawWave(now) {
  const { width, height } = canvas;
  const middle = height / 2;
  ctx.clearRect(0, 0, width, height);
  ctx.globalCompositeOperation = "lighter"; // overlapping layers glow brighter

  // Even when silent, keep a small "breathing" movement so it feels alive.
  const breathing = 0.08 + 0.04 * Math.sin(now / 600);
  const amplitude = height * Math.min(0.48, breathing + level * 0.42);

  for (const layer of WAVE_LAYERS) {
    const [r, g, b] = layer.color;
    const gradient = ctx.createLinearGradient(0, 0, width, 0);
    gradient.addColorStop(0, `rgba(${r},${g},${b},0)`);
    gradient.addColorStop(0.5, `rgba(${r},${g},${b},${layer.alpha})`);
    gradient.addColorStop(1, `rgba(${r},${g},${b},0)`);
    ctx.fillStyle = gradient;

    // A filled shape that is mirrored around the middle line, so it
    // expands and shrinks up AND down, like a sound wave.
    ctx.beginPath();
    for (let x = 0; x <= width; x += 2) {
      ctx.lineTo(x, middle - waveHeight(x, width, amplitude, layer, now));
    }
    for (let x = width; x >= 0; x -= 2) {
      ctx.lineTo(x, middle + waveHeight(x, width, amplitude, layer, now));
    }
    ctx.closePath();
    ctx.fill();
  }
  ctx.globalCompositeOperation = "source-over";
}

function waveHeight(x, width, amplitude, layer, now) {
  const t = x / width; // 0 at the left edge, 1 at the right edge
  const taper = Math.sin(Math.PI * t); // 0 at the edges, 1 in the centre
  const wave = 0.55 + 0.45 * Math.sin(t * layer.freq * 2 * Math.PI + now * layer.speed + layer.phase);
  return amplitude * taper * wave;
}
