const dropzone = document.getElementById("dropzone");
const audioInput = document.getElementById("audioInput");
const fileSelectedBar = document.getElementById("fileSelectedBar");
const selectedFileName = document.getElementById("selectedFileName");
const selectedFileSize = document.getElementById("selectedFileSize");
const clearFileBtn = document.getElementById("clearFileBtn");
const speakersSelect = document.getElementById("speakersSelect");
const modelSelect = document.getElementById("modelSelect");
const denoiseCheckbox = document.getElementById("denoiseCheckbox");
const diarizeCheckbox = document.getElementById("diarizeCheckbox");
const transcribeBtn = document.getElementById("transcribeBtn");
const toggleTokenBtn = document.getElementById("toggleTokenBtn");

const gpuStatus = document.getElementById("gpuStatus");
const hfStatus = document.getElementById("hfStatus");
const hfSetupCard = document.getElementById("hfSetupCard");
const hfTokenInput = document.getElementById("hfTokenInput");
const saveTokenBtn = document.getElementById("saveTokenBtn");
const tokenFeedback = document.getElementById("tokenFeedback");

const progressCard = document.getElementById("progressCard");
const progressStage = document.getElementById("progressStage");
const progressMeta = document.getElementById("progressMeta");
const progressPercent = document.getElementById("progressPercent");
const progressFill = document.getElementById("progressFill");

const errorCard = document.getElementById("errorCard");
const errorMessage = document.getElementById("errorMessage");
const retryBtn = document.getElementById("retryBtn");

const resultCard = document.getElementById("resultCard");
const resultSummary = document.getElementById("resultSummary");
const resultWarning = document.getElementById("resultWarning");
const copyBtn = document.getElementById("copyBtn");
const downloadBtn = document.getElementById("downloadBtn");
const audioBar = document.getElementById("audioBar");
const audioPlayer = document.getElementById("audioPlayer");
const speakerLegend = document.getElementById("speakerLegend");
const transcriptList = document.getElementById("transcriptList");

let selectedFile = null;
let activeJobId = null;
let pollTimer = null;
let elapsedTimer = null;
let jobStartTime = null;
let currentTranscriptText = "";
let hasHfToken = false;

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDuration(seconds) {
  if (seconds == null || isNaN(seconds)) return "";
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function getSpeakerClass(speakerLabel, speakerOrder) {
  const idx = speakerOrder.indexOf(speakerLabel);
  if (idx === -1) return "spk-default";
  return `spk-${idx % 6}`;
}

async function fetchSystemStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();

    if (data.cuda_available) {
      gpuStatus.textContent = `GPU lista: ${data.gpu_name}`;
      gpuStatus.className = "pill pill-ok";
    } else {
      gpuStatus.textContent = "Modo CPU (sin CUDA)";
      gpuStatus.className = "pill pill-warn";
    }

    hasHfToken = Boolean(data.hf_token_configured);
    if (hasHfToken) {
      hfStatus.textContent = "Hablantes: listo";
      hfStatus.className = "pill pill-ok";
      hfSetupCard.classList.add("hidden");
      toggleTokenBtn.classList.remove("hidden");
      toggleTokenBtn.textContent = "Cambiar token HF";
    } else {
      hfStatus.textContent = "Falta token HF";
      hfStatus.className = "pill pill-warn";
      hfSetupCard.classList.remove("hidden");
      toggleTokenBtn.classList.add("hidden");
    }

    if (!data.ffmpeg_available) {
      showError("No se encontró ffmpeg en el sistema. Es necesario para procesar archivos de audio.");
    }
  } catch (err) {
    gpuStatus.textContent = "Sin conexión con el servidor";
    gpuStatus.className = "pill pill-warn";
  }
}

function setSelectedFile(file) {
  selectedFile = file;
  if (!file) {
    fileSelectedBar.classList.add("hidden");
    transcribeBtn.disabled = true;
    return;
  }
  selectedFileName.textContent = file.name;
  selectedFileSize.textContent = formatBytes(file.size);
  fileSelectedBar.classList.remove("hidden");
  transcribeBtn.disabled = false;
  errorCard.classList.add("hidden");
}

dropzone.addEventListener("click", () => audioInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    audioInput.click();
  }
});

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
    setSelectedFile(e.dataTransfer.files[0]);
  }
});

audioInput.addEventListener("change", () => {
  if (audioInput.files && audioInput.files.length > 0) {
    setSelectedFile(audioInput.files[0]);
  }
});

clearFileBtn.addEventListener("click", () => {
  audioInput.value = "";
  setSelectedFile(null);
});

toggleTokenBtn.addEventListener("click", () => {
  hfSetupCard.classList.toggle("hidden");
});

saveTokenBtn.addEventListener("click", async () => {
  const token = hfTokenInput.value.trim();
  if (!token) {
    tokenFeedback.textContent = "Ingresa un token válido de Hugging Face.";
    tokenFeedback.className = "feedback-msg err";
    tokenFeedback.classList.remove("hidden");
    return;
  }

  saveTokenBtn.disabled = true;
  tokenFeedback.classList.add("hidden");
  try {
    const res = await fetch("/api/config/hf-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "No se pudo guardar el token.");
    }
    hfTokenInput.value = "";
    tokenFeedback.textContent = "Token guardado localmente en .env.";
    tokenFeedback.className = "feedback-msg ok";
    tokenFeedback.classList.remove("hidden");
    await fetchSystemStatus();
  } catch (err) {
    tokenFeedback.textContent = err.message;
    tokenFeedback.className = "feedback-msg err";
    tokenFeedback.classList.remove("hidden");
  } finally {
    saveTokenBtn.disabled = false;
  }
});

function parseSpeakerBounds(value) {
  if (value === "2") return { min: 2, max: 2 };
  if (value === "3") return { min: 3, max: 3 };
  if (value === "2-4") return { min: 2, max: 4 };
  if (value === "2-6") return { min: 2, max: 6 };
  return { min: null, max: null };
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (elapsedTimer) {
    clearInterval(elapsedTimer);
    elapsedTimer = null;
  }
}

function showError(msg) {
  stopPolling();
  progressCard.classList.add("hidden");
  errorMessage.textContent = msg;
  errorCard.classList.remove("hidden");
  transcribeBtn.disabled = !selectedFile;
}

function updateElapsedDisplay(durationSeconds) {
  if (!jobStartTime) return;
  const elapsed = (Date.now() - jobStartTime) / 1000;
  let text = `Tiempo transcurrido: ${formatDuration(elapsed)}`;
  if (durationSeconds) {
    text += ` · Duración del audio: ${formatDuration(durationSeconds)}`;
  }
  progressMeta.textContent = text;
}

async function startTranscription() {
  if (!selectedFile) return;

  if (diarizeCheckbox.checked && !hasHfToken) {
    hfSetupCard.classList.remove("hidden");
    hfTokenInput.focus();
    showError(
      "Para identificar hablantes (Hablante 1, Hablante 2…) primero guarda tu token gratuito de Hugging Face arriba, o desmarca la opción «Identificar hablantes» para probar solo la transcripción."
    );
    return;
  }

  stopPolling();
  errorCard.classList.add("hidden");
  resultCard.classList.add("hidden");
  progressCard.classList.remove("hidden");
  transcribeBtn.disabled = true;

  jobStartTime = Date.now();
  progressStage.textContent = "Subiendo archivo al servidor local…";
  progressPercent.textContent = "2 %";
  progressFill.style.width = "2%";
  updateElapsedDisplay(null);
  elapsedTimer = setInterval(() => updateElapsedDisplay(null), 1000);

  const formData = new FormData();
  formData.append("file", selectedFile);
  formData.append("model", modelSelect.value);
  formData.append("denoise", String(denoiseCheckbox.checked));
  formData.append("diarize", String(diarizeCheckbox.checked));

  const bounds = parseSpeakerBounds(speakersSelect.value);
  if (bounds.min !== null) formData.append("min_speakers", String(bounds.min));
  if (bounds.max !== null) formData.append("max_speakers", String(bounds.max));

  try {
    const res = await fetch("/api/transcribe", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Error al iniciar la transcripción.");
    }

    activeJobId = data.job_id;
    pollJob(activeJobId);
    pollTimer = setInterval(() => pollJob(activeJobId), 1500);
  } catch (err) {
    showError(err.message || "Error de conexión con el servidor local.");
  }
}

async function pollJob(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "No se pudo consultar el estado del proceso.");
    }

    const pct = Math.max(0, Math.min(100, Math.round(data.progress || 0)));
    progressStage.textContent = data.stage || "Procesando…";
    progressPercent.textContent = `${pct} %`;
    progressFill.style.width = `${pct}%`;

    clearInterval(elapsedTimer);
    updateElapsedDisplay(data.duration_seconds);
    elapsedTimer = setInterval(() => updateElapsedDisplay(data.duration_seconds), 1000);

    if (data.status === "completed") {
      stopPolling();
      progressCard.classList.add("hidden");
      renderResult(jobId, data);
      transcribeBtn.disabled = false;
    } else if (data.status === "error") {
      showError(data.error || "Ocurrió un error inesperado durante la transcripción.");
    }
  } catch (err) {
    showError(err.message || "Se perdió la conexión con el servidor local.");
  }
}

function renderResult(jobId, data) {
  const result = data.result || {};
  const turns = result.turns || [];
  const speakers = result.speakers || [];

  const durationText = data.duration_seconds ? formatDuration(data.duration_seconds) : "—";
  const elapsedText = data.elapsed_seconds ? formatDuration(data.elapsed_seconds) : "—";
  const speakerCountText = speakers.length
    ? `${speakers.length} ${speakers.length === 1 ? "hablante" : "hablantes"}`
    : "Sin separación de hablantes";

  resultSummary.textContent = `${data.filename} · Duración: ${durationText} · ${speakerCountText} · Procesado en ${elapsedText}`;

  if (result.warning) {
    resultWarning.textContent = result.warning;
    resultWarning.classList.remove("hidden");
  } else {
    resultWarning.classList.add("hidden");
  }

  // Reproductor de audio
  audioPlayer.src = `/api/jobs/${jobId}/audio`;
  audioBar.classList.remove("hidden");

  // Leyenda de hablantes
  speakerLegend.innerHTML = "";
  speakers.forEach((spk) => {
    const chip = document.createElement("span");
    chip.className = `speaker-chip ${getSpeakerClass(spk, speakers)}`;
    chip.textContent = spk;
    speakerLegend.appendChild(chip);
  });

  // Lista de intervenciones
  transcriptList.innerHTML = "";
  const lines = [];

  if (turns.length === 0) {
    const empty = document.createElement("p");
    empty.className = "subtitle";
    empty.textContent = "No se detectó voz en el audio.";
    transcriptList.appendChild(empty);
  } else {
    turns.forEach((turn) => {
      const spkClass = getSpeakerClass(turn.speaker, speakers);
      const startStr = formatDuration(turn.start);
      const endStr = formatDuration(turn.end);

      lines.push(`[${startStr} - ${endStr}] ${turn.speaker}: ${turn.text}`);

      const article = document.createElement("article");
      article.className = `turn ${spkClass}`;

      const header = document.createElement("div");
      header.className = "turn-header";

      const spkEl = document.createElement("span");
      spkEl.className = `turn-speaker ${spkClass}`;
      spkEl.textContent = turn.speaker;

      const timeBtn = document.createElement("button");
      timeBtn.type = "button";
      timeBtn.className = "turn-time";
      timeBtn.textContent = `${startStr} – ${endStr}`;
      timeBtn.title = "Ir a este momento del audio";
      timeBtn.addEventListener("click", () => {
        audioPlayer.currentTime = Math.max(0, turn.start || 0);
        audioPlayer.play().catch(() => {});
      });

      header.appendChild(spkEl);
      header.appendChild(timeBtn);

      if (turn.has_overlap) {
        const overlap = document.createElement("span");
        overlap.className = "overlap-badge";
        overlap.textContent = "Voces superpuestas";
        header.appendChild(overlap);
      }

      const textEl = document.createElement("p");
      textEl.className = "turn-text";
      textEl.textContent = turn.text;

      article.appendChild(header);
      article.appendChild(textEl);
      transcriptList.appendChild(article);
    });
  }

  currentTranscriptText = lines.join("\n\n");
  resultCard.classList.remove("hidden");
  resultCard.scrollIntoView({ behavior: "smooth", block: "start" });
}

copyBtn.addEventListener("click", async () => {
  if (!currentTranscriptText) return;
  try {
    await navigator.clipboard.writeText(currentTranscriptText);
    const prev = copyBtn.textContent;
    copyBtn.textContent = "¡Copiado!";
    setTimeout(() => {
      copyBtn.textContent = prev;
    }, 1800);
  } catch {
    showError("No se pudo copiar al portapapeles.");
  }
});

downloadBtn.addEventListener("click", () => {
  if (!activeJobId) return;
  window.location.href = `/api/jobs/${activeJobId}/download`;
});

transcribeBtn.addEventListener("click", startTranscription);
retryBtn.addEventListener("click", () => {
  errorCard.classList.add("hidden");
  startTranscription();
});

fetchSystemStatus();
