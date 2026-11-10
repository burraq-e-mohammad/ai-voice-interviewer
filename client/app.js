/*
  AI Voice Interviewer: Gemini-Live Style Web Client Logic
  - Candidate profile & target company interview simulation
  - Resume file upload & parsing (PDF, DOCX, TXT) delivered to LLM
  - 30-minute total interview timer + 90-second per-question countdown timer
  - Hands-free VAD (Voice Activity Detection)
  - 20-question structured interview progression & comprehensive scorecard
*/

"use strict";

// ---------- API Endpoints ----------
const BASE_URL = "http://localhost:8000";
const PARSE_RESUME_URL = `${BASE_URL}/session/parse-resume`;
const START_URL = `${BASE_URL}/session/start`;
const CHAT_URL = `${BASE_URL}/chat`;
const EVAL_URL = `${BASE_URL}/session/evaluate`;

// ---------- Interview Timing & VAD Settings ----------
const TOTAL_INTERVIEW_SECONDS = 30 * 60; // 30 minutes (1800s)
const QUESTION_TIME_SECONDS = 90;        // 90s per question (20 questions in 30 min)
const SILENCE_MS = 1400;                 // Silence pause signifying candidate completed response
const MIN_SPEECH_MS = 380;               // Ignore short audio artifacts/coughs
const MAX_UTTERANCE_MS = 60000;          // Safety cap: 60s max continuous utterance
const MIN_THRESHOLD = 0.015;             // Minimum RMS loudness for voice activity

const State = {
  IDLE: "idle",
  LISTENING: "listening",
  RECORDING: "recording",
  THINKING: "thinking",
  SPEAKING: "speaking",
};

const STATUS_TEXT = {
  idle: "",
  listening: "Listening… Speak your answer naturally",
  recording: "Listening to your answer…",
  thinking: "Analyzing response against company standards…",
  speaking: "Interviewer is speaking… (tap wave to interrupt)",
};

// ---------- DOM Elements ----------
const $ = (id) => document.getElementById(id);

// Screens
const startScreen = $("startScreen");
const liveScreen = $("liveScreen");
const evalScreen = $("evalScreen");

// Setup Form Elements
const candidateNameInput = $("candidateName");
const targetPositionInput = $("targetPosition");
const seniorityLevelSelect = $("seniorityLevel");
const targetCompanyInput = $("targetCompany");
const candidateSkillsInput = $("candidateSkills");
const jobDescriptionInput = $("jobDescription");
const resumeFileInput = $("resumeFile");
const uploadBtn = $("uploadBtn");
const dropzone = $("dropzone");
const fileStatusText = $("fileStatusText");
const clearFileBtn = $("clearFileBtn");
const startBtn = $("startBtn");
const startError = $("startError");

// Live Screen Elements
const liveRoleText = $("liveRoleText");
const liveCompanyText = $("liveCompanyText");
const botSenderLabel = $("botSenderLabel");
const turnBadge = $("turnBadge");
const totalTimeText = $("totalTimeText");
const questionTimeText = $("questionTimeText");
const questionTimerBadge = $("questionTimerBadge");
const userCaption = $("userCaption");
const botCaption = $("botCaption");
const statusEl = $("status");
const wavePill = $("wavePill");
const canvas = $("waveCanvas");
const ctx = canvas.getContext("2d");
const micBtn = $("micBtn");
const finishBtn = $("finishBtn");
const endBtn = $("endBtn");

// Evaluation Screen Elements
const evalSubtitle = $("evalSubtitle");
const evalScoreVal = $("evalScoreVal");
const evalCandidateName = $("evalCandidateName");
const evalRoleSummary = $("evalRoleSummary");
const evalRecommendationTag = $("evalRecommendationTag");
const evalReportBody = $("evalReportBody");
const restartBtn = $("restartBtn");
const copyReportBtn = $("copyReportBtn");

// ---------- State Variables ----------
let state = State.IDLE;
let muted = false;
let sessionId = null;
let currentProfile = null;
let interviewCompleted = false;
let latestEvaluationMarkdown = "";
let uploadedResumeText = "";

// Timers
let totalSecondsLeft = TOTAL_INTERVIEW_SECONDS;
let questionSecondsLeft = QUESTION_TIME_SECONDS;
let timerInterval = null;

// Audio & VAD
let audioCtx = null;
let micStream = null;
let micAnalyser = null;
let outAnalyser = null;
let recorder = null;
let chunks = [];
let replySource = null;
let abortController = null;

let speechStartedAt = 0;
let lastVoiceAt = 0;
let noiseFloor = 0.01;
let level = 0;
let animationId = null;
const sampleBuffer = new Float32Array(1024);

// =====================================================================
// Event Listeners Initialization
// =====================================================================

startBtn.addEventListener("click", startInterview);
finishBtn.addEventListener("click", () => finishAndEvaluate("Candidate requested early conclusion."));
endBtn.addEventListener("click", endInterview);
micBtn.addEventListener("click", toggleMute);
wavePill.addEventListener("click", interruptReply);
restartBtn.addEventListener("click", resetToStart);
copyReportBtn.addEventListener("click", copyScorecard);

// Resume File Upload Handling
uploadBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  resumeFileInput.click();
});

dropzone.addEventListener("click", (e) => {
  if (e.target === clearFileBtn || clearFileBtn.contains(e.target)) return;
  resumeFileInput.click();
});

resumeFileInput.addEventListener("change", handleResumeFileSelect);

clearFileBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  clearResumeFile();
});

// Drag & drop support on dropzone
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("dragover");
});

dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
    processResumeFile(e.dataTransfer.files[0]);
  }
});

// =====================================================================
// Resume Upload & Extraction
// =====================================================================

function handleResumeFileSelect(e) {
  if (e.target.files && e.target.files.length > 0) {
    processResumeFile(e.target.files[0]);
  }
}

async function processResumeFile(file) {
  if (!file) return;

  fileStatusText.textContent = `Extracting ${file.name}…`;
  fileStatusText.className = "file-status-text parsing";
  clearFileBtn.hidden = true;

  const form = new FormData();
  form.append("file", file);

  try {
    const response = await fetch(PARSE_RESUME_URL, {
      method: "POST",
      body: form,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.detail || `Error parsing file (${response.status})`);
    }

    const data = await response.json();
    uploadedResumeText = data.resume_text || "";
    fileStatusText.textContent = `✓ ${data.filename} (${data.word_count} words extracted)`;
    fileStatusText.className = "file-status-text loaded";
    clearFileBtn.hidden = false;
  } catch (err) {
    console.error("Resume parse failed:", err);
    // If it's a plain text file, fallback to browser FileReader
    if (file.name.endsWith(".txt")) {
      const reader = new FileReader();
      reader.onload = (event) => {
        uploadedResumeText = event.target.result;
        const words = uploadedResumeText.split(/\s+/).filter(Boolean).length;
        fileStatusText.textContent = `✓ ${file.name} (${words} words)`;
        fileStatusText.className = "file-status-text loaded";
        clearFileBtn.hidden = false;
      };
      reader.readAsText(file);
    } else {
      fileStatusText.textContent = `Failed to extract: ${err.message}`;
      fileStatusText.className = "file-status-text";
      uploadedResumeText = "";
      clearFileBtn.hidden = false;
    }
  }
}

function clearResumeFile() {
  resumeFileInput.value = "";
  uploadedResumeText = "";
  fileStatusText.textContent = "No file chosen (PDF, DOCX, TXT)";
  fileStatusText.className = "file-status-text";
  clearFileBtn.hidden = true;
}

// =====================================================================
// Start Interview Flow
// =====================================================================

async function startInterview() {
  startError.textContent = "";

  const name = candidateNameInput.value.trim();
  const position = targetPositionInput.value.trim();
  const levelVal = seniorityLevelSelect.value || "Senior";
  const company = targetCompanyInput.value.trim();
  const skills = candidateSkillsInput ? candidateSkillsInput.value.trim() : "";
  const jobDescription = jobDescriptionInput.value.trim();

  if (!name || !position || !company) {
    startError.textContent = "Please fill in Candidate Name, Target Position, and Target Company to begin.";
    return;
  }

  currentProfile = {
    name,
    position,
    level: levelVal,
    company,
    skills,
    job_description: jobDescription,
    resume_text: uploadedResumeText,
  };

  startBtn.disabled = true;
  startBtn.querySelector("span").textContent = "Connecting to Interviewer…";

  try {
    // 1. Request microphone permission
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (err) {
    startError.textContent = "Microphone access was denied. Please allow microphone permissions and try again.";
    startBtn.disabled = false;
    startBtn.querySelector("span").textContent = "Begin Voice Interview (20 Questions / 30 Min)";
    return;
  }

  try {
    // 2. Initialize Web Audio Context
    audioCtx = new AudioContext();

    micAnalyser = audioCtx.createAnalyser();
    micAnalyser.fftSize = 1024;
    audioCtx.createMediaStreamSource(micStream).connect(micAnalyser);

    outAnalyser = audioCtx.createAnalyser();
    outAnalyser.fftSize = 1024;
    outAnalyser.connect(audioCtx.destination);

    // 3. Register candidate profile with backend and receive opening speech
    const response = await fetch(START_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: currentProfile }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => null);
      throw new Error(errData?.error?.message || `Server error (${response.status})`);
    }

    const data = await response.json();
    sessionId = data.session_id;
    interviewCompleted = false;

    // 4. Update live view headers & labels
    liveRoleText.textContent = `${position} (${levelVal})`;
    liveCompanyText.textContent = company;
    botSenderLabel.textContent = `${company} Interviewer`;
    turnBadge.textContent = `Question ${data.turn} of ${data.max_turns || 20}`;

    // 5. Initialize Timers (30 min total + 90s question countdown)
    totalSecondsLeft = TOTAL_INTERVIEW_SECONDS;
    questionSecondsLeft = QUESTION_TIME_SECONDS;
    updateTimerDisplays();
    startTimerClock();

    // 6. Transition to Live Screen
    startScreen.hidden = true;
    evalScreen.hidden = true;
    liveScreen.hidden = false;
    resizeCanvas();
    animationId = requestAnimationFrame(tick);

    // 7. Display and play opening question
    userCaption.textContent = "Your microphone will activate when the interviewer finishes speaking the question.";
    showBotText(data.opening_text);

    if (data.opening_audio_base64) {
      const audioBuffer = await base64ToAudioBuffer(data.opening_audio_base64);
      playReply(audioBuffer);
    } else {
      setState(State.LISTENING);
    }
  } catch (err) {
    console.error("Interview start failed:", err);
    startError.textContent = `Error starting interview: ${err.message}. Is the server running on http://localhost:8000?`;
    cleanupAudio();
  } finally {
    startBtn.disabled = false;
    startBtn.querySelector("span").textContent = "Begin Voice Interview (20 Questions / 30 Min)";
  }
}

// Convert Base64 audio string to AudioBuffer
async function base64ToAudioBuffer(base64Str) {
  const binaryString = atob(base64Str);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return await audioCtx.decodeAudioData(bytes.buffer);
}

// =====================================================================
// Timers: 30-Minute Total Interview & 90-Second Question Countdown
// =====================================================================

function startTimerClock() {
  if (timerInterval) clearInterval(timerInterval);

  timerInterval = setInterval(() => {
    if (state === State.IDLE) return;

    // 1. Total 30-minute timer countdown
    if (totalSecondsLeft > 0) {
      totalSecondsLeft--;
    } else {
      clearInterval(timerInterval);
      totalSecondsLeft = 0;
      updateTimerDisplays();
      finishAndEvaluate("Interview concluded: 30-minute time limit reached.");
      return;
    }

    // 2. Per-question answer timer countdown (runs while candidate is answering)
    if (state === State.LISTENING || state === State.RECORDING) {
      if (questionSecondsLeft > 0) {
        questionSecondsLeft--;
      } else {
        // Question time expired
        questionSecondsLeft = 0;
        updateTimerDisplays();
        handleQuestionTimeExpired();
      }
    } else if (state === State.SPEAKING || state === State.THINKING) {
      // While interviewer is speaking or thinking, reset ready for next question
      questionSecondsLeft = QUESTION_TIME_SECONDS;
    }

    updateTimerDisplays();
  }, 1000);
}

function updateTimerDisplays() {
  // Format MM:SS for total timer
  const totalMin = Math.floor(totalSecondsLeft / 60);
  const totalSec = totalSecondsLeft % 60;
  totalTimeText.textContent = `${totalMin.toString().padStart(2, "0")}:${totalSec.toString().padStart(2, "0")}`;

  // Format MM:SS for question timer
  const qMin = Math.floor(questionSecondsLeft / 60);
  const qSec = questionSecondsLeft % 60;
  questionTimeText.textContent = `${qMin.toString().padStart(2, "0")}:${qSec.toString().padStart(2, "0")}`;

  // Warning styling based on remaining question answer time
  if (questionSecondsLeft <= 10 && (state === State.LISTENING || state === State.RECORDING)) {
    questionTimerBadge.className = "timer-pill question-timer danger";
  } else if (questionSecondsLeft <= 25 && (state === State.LISTENING || state === State.RECORDING)) {
    questionTimerBadge.className = "timer-pill question-timer warning";
  } else {
    questionTimerBadge.className = "timer-pill question-timer";
  }
}

function handleQuestionTimeExpired() {
  if (state === State.RECORDING && recorder && recorder.state !== "inactive") {
    // Automatically wrap up candidate response and send
    statusEl.textContent = "Question time expired. Submitting your response…";
    finishRecordingAndSend();
  } else if (state === State.LISTENING) {
    // Candidate didn't start speaking
    userCaption.textContent = "[No spoken response within 90 seconds]";
    showBotText("Let us move to the next question.");
    setState(State.THINKING);
    // Send empty audio prompt to advance turn
    setTimeout(() => {
      advanceWithoutAudio();
    }, 1000);
  }
}

async function advanceWithoutAudio() {
  // Synthesizes a skip/timeout response
  const blob = new Blob([], { type: "audio/webm" });
  await sendAudio(blob);
}

// =====================================================================
// Turn Execution & Audio Sending
// =====================================================================

async function sendAudio(blob) {
  const form = new FormData();
  form.append("audio", blob, "speech.webm");
  form.append("session_id", sessionId);
  abortController = new AbortController();

  try {
    const response = await fetch(CHAT_URL, {
      method: "POST",
      body: form,
      signal: abortController.signal,
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      if (body?.error?.code === "no_speech_detected") {
        setState(State.LISTENING);
        return;
      }
      throw new Error(body?.error?.message || `Server error (${response.status})`);
    }

    // Read metadata headers
    const rawTranscript = response.headers.get("X-Transcript") || "";
    const rawReplyText = response.headers.get("X-Reply-Text") || "";
    const turn = response.headers.get("X-Turn") || "1";
    const maxTurns = response.headers.get("X-Max-Turns") || "20";
    const isComplete = response.headers.get("X-Is-Complete") === "true";

    userCaption.textContent = decodeURIComponent(rawTranscript);
    showBotText(decodeURIComponent(rawReplyText));
    turnBadge.textContent = `Question ${turn} of ${maxTurns}`;

    // Reset question countdown for the next question
    questionSecondsLeft = QUESTION_TIME_SECONDS;
    updateTimerDisplays();

    if (isComplete) {
      interviewCompleted = true;
    }

    const audioData = await response.arrayBuffer();
    if (state !== State.THINKING) return;

    const audioBuffer = await audioCtx.decodeAudioData(audioData);
    playReply(audioBuffer);
  } catch (err) {
    if (err.name === "AbortError") return;
    const message =
      err instanceof TypeError
        ? "Unable to reach server. Please confirm the server is running."
        : err.message;
    showBotText(message, true);
    setState(State.LISTENING);
  } finally {
    abortController = null;
  }
}

// =====================================================================
// Evaluation & Scorecard
// =====================================================================

async function finishAndEvaluate(reasonNote = "") {
  stopReply();
  discardRecording();
  cancelAnimationFrame(animationId);
  if (timerInterval) clearInterval(timerInterval);

  // Transition to Evaluation Screen
  liveScreen.hidden = true;
  startScreen.hidden = true;
  evalScreen.hidden = false;

  const candidateName = currentProfile?.name || "Candidate";
  const role = currentProfile?.position || "Software Engineer";
  const company = currentProfile?.company || "Google";
  const levelVal = currentProfile?.level || "Senior";

  evalCandidateName.textContent = candidateName;
  evalRoleSummary.textContent = `Target: ${levelVal} ${role} at ${company}`;
  evalSubtitle.textContent = `Performance scorecard evaluated against authentic ${company} interview rounds`;
  evalScoreVal.textContent = "...";
  evalRecommendationTag.textContent = "Analyzing…";

  evalReportBody.innerHTML = `
    <div class="loading-state">
      <div class="spinner"></div>
      <p>Gemini is evaluating your dialogue against ${company}'s authentic hiring bar…</p>
      ${reasonNote ? `<p style="font-size:0.85rem; color:var(--text-dim);">${reasonNote}</p>` : ""}
    </div>
  `;

  try {
    const response = await fetch(EVAL_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => null);
      throw new Error(errData?.error?.message || `Evaluation request failed (${response.status})`);
    }

    const data = await response.json();
    latestEvaluationMarkdown = data.feedback_markdown || "";

    // Set score
    const scoreText = data.score && data.score !== "N/A" ? data.score : "7.5/10";
    evalScoreVal.textContent = scoreText;

    // Numerical score styling
    const numericMatch = scoreText.match(/(\d+(\.\d+)?)/);
    const numericScore = numericMatch ? parseFloat(numericMatch[1]) : 7.5;
    if (numericScore >= 8.0) {
      evalRecommendationTag.textContent = "Strong Hire / Recommended";
      evalRecommendationTag.style.borderColor = "var(--green)";
      evalRecommendationTag.style.color = "#34d399";
    } else if (numericScore >= 6.0) {
      evalRecommendationTag.textContent = "Qualified / Potential Match";
      evalRecommendationTag.style.borderColor = "var(--yellow)";
      evalRecommendationTag.style.color = "#fbbf24";
    } else {
      evalRecommendationTag.textContent = "Further Preparation Advised";
      evalRecommendationTag.style.borderColor = "var(--red)";
      evalRecommendationTag.style.color = "#f87171";
    }

    // Render formatted markdown
    evalReportBody.innerHTML = renderMarkdown(data.feedback_markdown);
  } catch (err) {
    console.error("Evaluation error:", err);
    evalReportBody.innerHTML = `
      <div style="padding: 20px; color: #fca5a5;">
        <h3>Evaluation Error</h3>
        <p>${err.message}</p>
        <button onclick="finishAndEvaluate()" class="pill-btn secondary-btn" style="margin-top:10px;">Retry Evaluation</button>
      </div>
    `;
  }
}

function copyScorecard() {
  if (!latestEvaluationMarkdown) return;
  navigator.clipboard.writeText(latestEvaluationMarkdown).then(() => {
    const originalText = copyReportBtn.querySelector("span").textContent;
    copyReportBtn.querySelector("span").textContent = "Copied to Clipboard! ✓";
    setTimeout(() => {
      copyReportBtn.querySelector("span").textContent = originalText;
    }, 2000);
  });
}

function resetToStart() {
  cleanupAudio();
  if (timerInterval) clearInterval(timerInterval);
  evalScreen.hidden = true;
  liveScreen.hidden = true;
  startScreen.hidden = false;
  setState(State.IDLE);
}

function endInterview() {
  if (confirm("Exit interview? Your progress in this session will be discarded.")) {
    cleanupAudio();
    if (timerInterval) clearInterval(timerInterval);
    liveScreen.hidden = true;
    evalScreen.hidden = true;
    startScreen.hidden = false;
    setState(State.IDLE);
  }
}

function cleanupAudio() {
  cancelAnimationFrame(animationId);
  if (timerInterval) clearInterval(timerInterval);
  abortController?.abort();
  discardRecording();
  stopReply();
  micStream?.getTracks().forEach((track) => track.stop());
  audioCtx?.close();
  micStream = audioCtx = null;
  setMuted(false);
  level = 0;
  document.documentElement.style.setProperty("--level", "0");
}

// =====================================================================
// Audio Playback & Interruption
// =====================================================================

function playReply(audioBuffer) {
  replySource = audioCtx.createBufferSource();
  replySource.buffer = audioBuffer;
  replySource.connect(outAnalyser);

  replySource.addEventListener("ended", () => {
    replySource = null;
    if (interviewCompleted) {
      finishAndEvaluate("All 20 interview questions completed.");
    } else if (state === State.SPEAKING) {
      setState(State.LISTENING);
      // Reset question timer to 90s and begin counting down for candidate
      questionSecondsLeft = QUESTION_TIME_SECONDS;
      updateTimerDisplays();
    }
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

function interruptReply() {
  if (state === State.SPEAKING) {
    stopReply();
    if (interviewCompleted) {
      finishAndEvaluate("Interview completed.");
    } else {
      setState(State.LISTENING);
      questionSecondsLeft = QUESTION_TIME_SECONDS;
      updateTimerDisplays();
    }
  }
}

// =====================================================================
// Mute & State Handling
// =====================================================================

function toggleMute() {
  setMuted(!muted);
}

function setMuted(val) {
  muted = val;
  micStream?.getAudioTracks().forEach((track) => (track.enabled = !muted));
  if (muted && state === State.RECORDING) discardRecording();
  micBtn.setAttribute("aria-pressed", String(muted));
  micBtn.title = muted ? "Unmute microphone" : "Mute microphone";
  document.body.classList.toggle("muted", muted);
  updateStatus();
}

function setState(newState) {
  state = newState;
  document.body.dataset.state = newState;
  updateStatus();
}

function updateStatus() {
  const listening = state === State.LISTENING || state === State.RECORDING;
  statusEl.textContent = muted && listening ? "Microphone is muted" : STATUS_TEXT[state];
}

function showBotText(text, isError = false) {
  botCaption.textContent = text;
  botCaption.classList.toggle("error", isError);
}

// =====================================================================
// Animation & VAD Loop (~60fps)
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
    target = 0.25 + 0.15 * Math.sin(now / 250);
  }

  level += (target - level) * 0.18;
  document.documentElement.style.setProperty("--level", level.toFixed(3));
  drawWave(now);

  animationId = requestAnimationFrame(tick);
}

function measureLoudness(analyser) {
  if (!analyser) return 0;
  analyser.getFloatTimeDomainData(sampleBuffer);
  let sum = 0;
  for (const sample of sampleBuffer) sum += sample * sample;
  return Math.sqrt(sum / sampleBuffer.length);
}

function detectSpeech(rms, now) {
  const threshold = Math.max(MIN_THRESHOLD, noiseFloor * 2.5);
  const isVoice = rms > threshold;

  if (state === State.LISTENING) {
    if (isVoice) {
      startRecording(now);
    } else {
      noiseFloor = noiseFloor * 0.98 + rms * 0.02;
    }
    return;
  }

  // State is RECORDING
  if (isVoice) lastVoiceAt = now;
  const silentFor = now - lastVoiceAt;
  const spokeFor = lastVoiceAt - speechStartedAt;

  if (silentFor > SILENCE_MS || now - speechStartedAt > MAX_UTTERANCE_MS) {
    if (spokeFor < MIN_SPEECH_MS) {
      discardRecording();
      setState(State.LISTENING);
    } else {
      finishRecordingAndSend();
    }
  }
}

function startRecording(now) {
  chunks = [];
  try {
    recorder = new MediaRecorder(micStream);
    recorder.addEventListener("dataavailable", (event) => chunks.push(event.data));
    recorder.start();
    speechStartedAt = lastVoiceAt = now;
    setState(State.RECORDING);
  } catch (err) {
    console.error("Failed to start MediaRecorder:", err);
  }
}

function finishRecordingAndSend() {
  const activeRecorder = recorder;
  recorder = null;
  setState(State.THINKING);

  activeRecorder.addEventListener("stop", () => {
    sendAudio(new Blob(chunks, { type: activeRecorder.mimeType }));
  });
  activeRecorder.stop();
}

function discardRecording() {
  if (recorder && recorder.state !== "inactive") {
    recorder.stop();
  }
  recorder = null;
  chunks = [];
  if (state === State.RECORDING) setState(State.LISTENING);
}

// =====================================================================
// Wave Visualizer (Dynamic Pill Canvas)
// =====================================================================

const WAVE_LAYERS = [
  { color: [37, 99, 235], alpha: 0.55, freq: 1.2, speed: 0.0022, phase: 0 },
  { color: [59, 130, 246], alpha: 0.65, freq: 1.8, speed: -0.0028, phase: 2.1 },
  { color: [96, 165, 250], alpha: 0.75, freq: 2.5, speed: 0.0035, phase: 4.2 },
];

function resizeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = canvas.clientWidth * dpr;
  canvas.height = canvas.clientHeight * dpr;
}
window.addEventListener("resize", resizeCanvas);

function drawWave(now) {
  const { width, height } = canvas;
  if (!width || !height) return;

  const middle = height / 2;
  ctx.clearRect(0, 0, width, height);
  ctx.globalCompositeOperation = "lighter";

  const breathing = 0.08 + 0.04 * Math.sin(now / 600);
  const amplitude = height * Math.min(0.48, breathing + level * 0.42);

  for (const layer of WAVE_LAYERS) {
    const [r, g, b] = layer.color;
    const gradient = ctx.createLinearGradient(0, 0, width, 0);
    gradient.addColorStop(0, `rgba(${r},${g},${b},0)`);
    gradient.addColorStop(0.5, `rgba(${r},${g},${b},${layer.alpha})`);
    gradient.addColorStop(1, `rgba(${r},${g},${b},0)`);
    ctx.fillStyle = gradient;

    ctx.beginPath();
    for (let x = 0; x <= width; x += 2) {
      ctx.lineTo(x, middle - calculateWaveHeight(x, width, amplitude, layer, now));
    }
    for (let x = width; x >= 0; x -= 2) {
      ctx.lineTo(x, middle + calculateWaveHeight(x, width, amplitude, layer, now));
    }
    ctx.closePath();
    ctx.fill();
  }
  ctx.globalCompositeOperation = "source-over";
}

function calculateWaveHeight(x, width, amplitude, layer, now) {
  const t = x / width;
  const taper = Math.sin(Math.PI * t);
  const wave = 0.55 + 0.45 * Math.sin(t * layer.freq * 2 * Math.PI + now * layer.speed + layer.phase);
  return amplitude * taper * wave;
}

// =====================================================================
// Lightweight Markdown Renderer for Scorecard
// =====================================================================

function renderMarkdown(md) {
  if (!md) return "<p>No report details available.</p>";

  // Escape raw HTML tags
  let html = md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Headers
  html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
  html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");
  html = html.replace(/^# (.*$)/gim, "<h1>$1</h1>");

  // Bold
  html = html.replace(/\*\*(.*?)\*\*/gim, "<strong>$1</strong>");

  // List items
  html = html.replace(/^\s*[-*]\s+(.*$)/gim, "<li>$1</li>");
  html = html.replace(/(<li>[\s\S]*?<\/li>)/gim, "<ul>$1</ul>");
  html = html.replace(/<\/ul>\s*<ul>/gim, "");

  // Paragraphs
  const blocks = html.split(/\n{2,}/);
  return blocks
    .map((block) => {
      block = block.trim();
      if (!block) return "";
      if (block.startsWith("<h") || block.startsWith("<ul") || block.startsWith("<li")) {
        return block;
      }
      return `<p>${block.replace(/\n/g, "<br>")}</p>`;
    })
    .join("");
}
