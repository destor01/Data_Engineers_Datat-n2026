// Tabs & upload elements
const tabAudio = document.getElementById("tabAudio");
const tabTranscript = document.getElementById("tabTranscript");
const audioModePanel = document.getElementById("audioModePanel");
const transcriptModePanel = document.getElementById("transcriptModePanel");

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

const transcriptDropzone = document.getElementById("transcriptDropzone");
const transcriptInput = document.getElementById("transcriptInput");
const transcriptFileBar = document.getElementById("transcriptFileBar");
const selectedTranscriptName = document.getElementById("selectedTranscriptName");
const selectedTranscriptSize = document.getElementById("selectedTranscriptSize");
const clearTranscriptBtn = document.getElementById("clearTranscriptBtn");
const uploadTranscriptBtn = document.getElementById("uploadTranscriptBtn");
const loadExampleBtn = document.getElementById("loadExampleBtn");

// Status & API key setup
const gpuStatus = document.getElementById("gpuStatus");
const hfStatus = document.getElementById("hfStatus");
const openrouterStatus = document.getElementById("openrouterStatus");
const hfSetupCard = document.getElementById("hfSetupCard");
const hfTokenInput = document.getElementById("hfTokenInput");
const saveTokenBtn = document.getElementById("saveTokenBtn");
const tokenFeedback = document.getElementById("tokenFeedback");
const toggleTokenBtn = document.getElementById("toggleTokenBtn");

const openrouterSetupCard = document.getElementById("openrouterSetupCard");
const openrouterKeyInput = document.getElementById("openrouterKeyInput");
const saveOpenrouterBtn = document.getElementById("saveOpenrouterBtn");
const openrouterFeedback = document.getElementById("openrouterFeedback");
const toggleOpenrouterBtn = document.getElementById("toggleOpenrouterBtn");
const toggleOpenrouterBtn2 = document.getElementById("toggleOpenrouterBtn2");

// Progress & errors
const progressCard = document.getElementById("progressCard");
const progressStage = document.getElementById("progressStage");
const progressMeta = document.getElementById("progressMeta");
const progressPercent = document.getElementById("progressPercent");
const progressFill = document.getElementById("progressFill");

const errorCard = document.getElementById("errorCard");
const errorMessage = document.getElementById("errorMessage");
const retryBtn = document.getElementById("retryBtn");

// Transcript & JEV launcher
const resultCard = document.getElementById("resultCard");
const resultSummary = document.getElementById("resultSummary");
const resultWarning = document.getElementById("resultWarning");
const resultNote = document.getElementById("resultNote");
const copyBtn = document.getElementById("copyBtn");
const downloadBtn = document.getElementById("downloadBtn");
const audioBar = document.getElementById("audioBar");
const audioPlayer = document.getElementById("audioPlayer");
const speakerLegend = document.getElementById("speakerLegend");
const transcriptList = document.getElementById("transcriptList");

const speakerRoleGrid = document.getElementById("speakerRoleGrid");
const firstContactCheckbox = document.getElementById("firstContactCheckbox");
const mockModeCheckbox = document.getElementById("mockModeCheckbox");
const evaluateBtn = document.getElementById("evaluateBtn");
const jevRunningHint = document.getElementById("jevRunningHint");
const jevErrorInline = document.getElementById("jevErrorInline");

// JEV Report
const jevReportCard = document.getElementById("jevReportCard");
const jevVerdictBadge = document.getElementById("jevVerdictBadge");
const jevReportMeta = document.getElementById("jevReportMeta");
const downloadJevBtn = document.getElementById("downloadJevBtn");
const jevMockWarning = document.getElementById("jevMockWarning");
const jevKpiStrip = document.getElementById("jevKpiStrip");
const jevSectionsGrid = document.getElementById("jevSectionsGrid");
const jevRisksList = document.getElementById("jevRisksList");
const jevRulesDetails = document.getElementById("jevRulesDetails");
const jevRulesCountPill = document.getElementById("jevRulesCountPill");
const ruleStatusFilters = document.getElementById("ruleStatusFilters");
const ruleSectionFilter = document.getElementById("ruleSectionFilter");
const ruleSearchInput = document.getElementById("ruleSearchInput");
const jevRulesTableBody = document.getElementById("jevRulesTableBody");

const ROLE_OPTIONS = [
  { value: "ENCUESTADOR", label: "ENCUESTADOR" },
  { value: "INFORMANTE", label: "INFORMANTE" },
  { value: "OTRA_PERSONA", label: "OTRA_PERSONA" },
];

const KIND_LABELS = {
  obligation: "Obligación",
  prohibition: "Prohibición",
  conditional: "Condicional",
  evidence: "Evidencia",
};

const WEIGHT_LABELS = {
  1: "Baja (1)",
  2: "Media (2)",
  3: "Alta (3)",
};

let selectedFile = null;
let selectedTranscriptFile = null;
let activeJobId = null;
let activeHasAudio = false;
let activeTurns = [];
let activeSpeakers = [];
let speakerRoleMap = {};
let activeEvaluation = null;

let pollTimer = null;
let evalPollTimer = null;
let elapsedTimer = null;
let jobStartTime = null;
let currentTranscriptText = "";
let hasHfToken = false;
let hasOpenrouterKey = false;
let currentRuleFilter = "all";

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

function formatPct(value, digits = 0) {
  if (value == null || isNaN(value)) return "n/a";
  return `${(value * 100).toFixed(digits)} %`;
}

function formatTimeRange(timeArr) {
  if (!Array.isArray(timeArr) || (timeArr[0] == null && timeArr[1] == null)) return null;
  const a = timeArr[0] != null ? formatDuration(timeArr[0]) : "—";
  const b = timeArr[1] != null ? formatDuration(timeArr[1]) : "—";
  return a === b ? a : `${a} – ${b}`;
}

function getRateColorClass(rate) {
  if (rate == null) return "";
  if (rate >= 0.85) return "rate-ok";
  if (rate >= 0.7) return "rate-warn";
  return "rate-danger";
}

function getSpeakerClass(speakerLabel, speakerOrder) {
  const idx = speakerOrder.indexOf(speakerLabel);
  if (idx === -1) return "spk-default";
  return `spk-${idx % 6}`;
}

function switchTab(mode) {
  const isAudio = mode === "audio";
  tabAudio.classList.toggle("active", isAudio);
  tabAudio.setAttribute("aria-selected", String(isAudio));
  tabTranscript.classList.toggle("active", !isAudio);
  tabTranscript.setAttribute("aria-selected", String(!isAudio));
  audioModePanel.classList.toggle("hidden", !isAudio);
  transcriptModePanel.classList.toggle("hidden", isAudio);
  errorCard.classList.add("hidden");
}

tabAudio.addEventListener("click", () => switchTab("audio"));
tabTranscript.addEventListener("click", () => switchTab("transcript"));

async function fetchSystemStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();

    if (data.cuda_available) {
      gpuStatus.textContent = `GPU: ${data.gpu_name}`;
      gpuStatus.className = "pill pill-ok";
    } else {
      gpuStatus.textContent = "Modo CPU (sin CUDA)";
      gpuStatus.className = "pill pill-warn";
    }

    hasHfToken = Boolean(data.hf_token_configured);
    if (hasHfToken) {
      hfStatus.textContent = "HF hablantes: listo";
      hfStatus.className = "pill pill-ok pill-btn";
      hfSetupCard.classList.add("hidden");
    } else {
      hfStatus.textContent = "Falta HF_TOKEN";
      hfStatus.className = "pill pill-warn pill-btn";
      hfSetupCard.classList.remove("hidden");
    }

    hasOpenrouterKey = Boolean(data.openrouter_configured);
    if (hasOpenrouterKey) {
      openrouterStatus.textContent = "JEV OpenRouter: listo";
      openrouterStatus.className = "pill pill-ok pill-btn";
      openrouterSetupCard.classList.add("hidden");
    } else {
      openrouterStatus.textContent = "Falta OPENROUTER_API_KEY";
      openrouterStatus.className = "pill pill-warn pill-btn";
    }

    loadExampleBtn.classList.toggle("hidden", !data.example_available);

    if (!data.ffmpeg_available) {
      showError("No se encontró ffmpeg en el sistema. Es necesario para procesar archivos de audio.");
    }
  } catch {
    gpuStatus.textContent = "Sin conexión con el servidor";
    gpuStatus.className = "pill pill-warn";
  }
}

hfStatus.addEventListener("click", () => hfSetupCard.classList.toggle("hidden"));
toggleTokenBtn.addEventListener("click", () => hfSetupCard.classList.toggle("hidden"));

openrouterStatus.addEventListener("click", () => openrouterSetupCard.classList.toggle("hidden"));
toggleOpenrouterBtn.addEventListener("click", () => openrouterSetupCard.classList.toggle("hidden"));
toggleOpenrouterBtn2.addEventListener("click", () => openrouterSetupCard.classList.toggle("hidden"));

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
    if (!res.ok) throw new Error(data.detail || "No se pudo guardar el token.");
    hfTokenInput.value = "";
    tokenFeedback.textContent = "HF_TOKEN guardado en .env.";
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

saveOpenrouterBtn.addEventListener("click", async () => {
  const token = openrouterKeyInput.value.trim();
  if (!token) {
    openrouterFeedback.textContent = "Ingresa una clave válida de OpenRouter (sk-or-...).";
    openrouterFeedback.className = "feedback-msg err";
    openrouterFeedback.classList.remove("hidden");
    return;
  }

  saveOpenrouterBtn.disabled = true;
  openrouterFeedback.classList.add("hidden");
  try {
    const res = await fetch("/api/config/openrouter-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "No se pudo guardar la clave.");
    openrouterKeyInput.value = "";
    openrouterFeedback.textContent = "OPENROUTER_API_KEY guardada en .env.";
    openrouterFeedback.className = "feedback-msg ok";
    openrouterFeedback.classList.remove("hidden");
    await fetchSystemStatus();
  } catch (err) {
    openrouterFeedback.textContent = err.message;
    openrouterFeedback.className = "feedback-msg err";
    openrouterFeedback.classList.remove("hidden");
  } finally {
    saveOpenrouterBtn.disabled = false;
  }
});

// Audio file selection
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

function wireDropzone(zone, input, onFile) {
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      input.click();
    }
  });
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("dragover");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      onFile(e.dataTransfer.files[0]);
    }
  });
  input.addEventListener("change", () => {
    if (input.files && input.files.length > 0) {
      onFile(input.files[0]);
    }
  });
}

wireDropzone(dropzone, audioInput, setSelectedFile);
clearFileBtn.addEventListener("click", () => {
  audioInput.value = "";
  setSelectedFile(null);
});

// Existing transcript selection
function setSelectedTranscriptFile(file) {
  selectedTranscriptFile = file;
  if (!file) {
    transcriptFileBar.classList.add("hidden");
    uploadTranscriptBtn.disabled = true;
    return;
  }
  selectedTranscriptName.textContent = file.name;
  selectedTranscriptSize.textContent = formatBytes(file.size);
  transcriptFileBar.classList.remove("hidden");
  uploadTranscriptBtn.disabled = false;
  errorCard.classList.add("hidden");
}

wireDropzone(transcriptDropzone, transcriptInput, setSelectedTranscriptFile);
clearTranscriptBtn.addEventListener("click", () => {
  transcriptInput.value = "";
  setSelectedTranscriptFile(null);
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

function stopEvalPolling() {
  if (evalPollTimer) {
    clearInterval(evalPollTimer);
    evalPollTimer = null;
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
  stopEvalPolling();
  errorCard.classList.add("hidden");
  resultCard.classList.add("hidden");
  jevReportCard.classList.add("hidden");
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
    if (!res.ok) throw new Error(data.detail || "Error al iniciar la transcripción.");

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
    if (!res.ok) throw new Error(data.detail || "No se pudo consultar el estado del proceso.");

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

async function uploadExistingTranscript() {
  if (!selectedTranscriptFile) return;
  stopPolling();
  stopEvalPolling();
  errorCard.classList.add("hidden");
  jevReportCard.classList.add("hidden");
  uploadTranscriptBtn.disabled = true;

  const formData = new FormData();
  formData.append("file", selectedTranscriptFile);

  try {
    const res = await fetch("/api/transcript/upload", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "No se pudo cargar la transcripción.");
    activeJobId = data.job_id;
    renderResult(data.job_id, data);
  } catch (err) {
    showError(err.message || "Error al leer la transcripción.");
  } finally {
    uploadTranscriptBtn.disabled = !selectedTranscriptFile;
  }
}

async function loadExampleTranscript() {
  stopPolling();
  stopEvalPolling();
  errorCard.classList.add("hidden");
  jevReportCard.classList.add("hidden");
  loadExampleBtn.disabled = true;

  try {
    const res = await fetch("/api/transcript/example", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "No se pudo cargar el ejemplo ENCOVI.");
    activeJobId = data.job_id;
    renderResult(data.job_id, data);
  } catch (err) {
    showError(err.message || "Error cargando la entrevista de ejemplo.");
  } finally {
    loadExampleBtn.disabled = false;
  }
}

function renderRoleMapper() {
  speakerRoleGrid.innerHTML = "";
  activeSpeakers.forEach((spk) => {
    const row = document.createElement("div");
    row.className = "role-item";

    const chip = document.createElement("span");
    chip.className = `speaker-chip ${getSpeakerClass(spk, activeSpeakers)}`;
    chip.textContent = spk;

    const select = document.createElement("select");
    select.setAttribute("aria-label", `Rol de ${spk}`);
    ROLE_OPTIONS.forEach((opt) => {
      const o = document.createElement("option");
      o.value = opt.value;
      o.textContent = opt.label;
      if ((speakerRoleMap[spk] || "OTRA_PERSONA") === opt.value) {
        o.selected = true;
      }
      select.appendChild(o);
    });

    select.addEventListener("change", () => {
      speakerRoleMap[spk] = select.value;
      updateTurnRoleBadges();
    });

    row.appendChild(chip);
    row.appendChild(select);
    speakerRoleGrid.appendChild(row);
  });
}

function updateTurnRoleBadges() {
  const tags = transcriptList.querySelectorAll("[data-role-for]");
  tags.forEach((el) => {
    const rawSpk = el.getAttribute("data-role-for");
    const role = speakerRoleMap[rawSpk];
    el.textContent = role || "";
    el.classList.toggle("hidden", !role || role.toUpperCase() === rawSpk.toUpperCase());
  });
}

function jumpToMoment(seconds) {
  if (seconds == null || isNaN(seconds)) return;

  if (activeHasAudio) {
    audioBar.scrollIntoView({ behavior: "smooth", block: "nearest" });
    audioPlayer.currentTime = Math.max(0, seconds);
    audioPlayer.play().catch(() => {});
  }

  // Highlight and scroll to the closest turn in the transcript
  const turnEls = Array.from(transcriptList.querySelectorAll(".turn[data-start]"));
  if (!turnEls.length) return;

  let bestEl = turnEls[0];
  let bestDiff = Infinity;
  for (const el of turnEls) {
    const s = parseFloat(el.getAttribute("data-start"));
    if (isNaN(s)) continue;
    const diff = Math.abs(s - seconds);
    if (diff < bestDiff) {
      bestDiff = diff;
      bestEl = el;
    }
  }

  bestEl.scrollIntoView({ behavior: "smooth", block: "center" });
  bestEl.classList.add("turn-highlight");
  setTimeout(() => bestEl.classList.remove("turn-highlight"), 2200);
}

function renderResult(jobId, data) {
  const result = data.result || {};
  activeTurns = result.turns || [];
  activeSpeakers = result.speakers || [];
  activeHasAudio = Boolean(data.has_audio);
  activeEvaluation = data.evaluation || null;

  if (!activeSpeakers.length && activeTurns.length) {
    activeSpeakers = [...new Set(activeTurns.map((t) => t.speaker))];
  }

  speakerRoleMap = { ...(result.suggested_roles || {}) };
  activeSpeakers.forEach((spk, idx) => {
    if (!speakerRoleMap[spk]) {
      speakerRoleMap[spk] = idx === 0 ? "ENCUESTADOR" : idx === 1 ? "INFORMANTE" : "OTRA_PERSONA";
    }
  });

  const durationText = data.duration_seconds ? formatDuration(data.duration_seconds) : null;
  const elapsedText = data.elapsed_seconds ? formatDuration(data.elapsed_seconds) : null;
  const speakerCountText = activeSpeakers.length
    ? `${activeSpeakers.length} ${activeSpeakers.length === 1 ? "hablante" : "hablantes"}`
    : "Sin separación de hablantes";

  const summaryParts = [data.filename, `${activeTurns.length} intervenciones`, speakerCountText];
  if (durationText) summaryParts.push(`Duración: ${durationText}`);
  if (elapsedText && data.source === "audio") summaryParts.push(`Procesado en ${elapsedText}`);
  resultSummary.textContent = summaryParts.join(" · ");

  if (result.warning) {
    resultWarning.textContent = result.warning;
    resultWarning.classList.remove("hidden");
  } else {
    resultWarning.classList.add("hidden");
  }

  if (result.note) {
    resultNote.textContent = result.note;
    resultNote.classList.remove("hidden");
  } else {
    resultNote.classList.add("hidden");
  }

  if (activeHasAudio) {
    audioPlayer.src = `/api/jobs/${jobId}/audio`;
    audioBar.classList.remove("hidden");
  } else {
    audioPlayer.removeAttribute("src");
    audioBar.classList.add("hidden");
  }

  // Speaker role mapper
  renderRoleMapper();
  jevErrorInline.classList.add("hidden");
  jevRunningHint.classList.add("hidden");
  evaluateBtn.disabled = activeTurns.length === 0;
  evaluateBtn.textContent = activeEvaluation ? "Re-evaluar con JEV" : "Evaluar con JEV";

  // Speaker legend
  speakerLegend.innerHTML = "";
  activeSpeakers.forEach((spk) => {
    const chip = document.createElement("span");
    chip.className = `speaker-chip ${getSpeakerClass(spk, activeSpeakers)}`;
    chip.textContent = spk;
    speakerLegend.appendChild(chip);
  });

  // Transcript turns
  transcriptList.innerHTML = "";
  const lines = [];

  if (activeTurns.length === 0) {
    const empty = document.createElement("p");
    empty.className = "subtitle";
    empty.textContent = "No se detectó voz en el audio.";
    transcriptList.appendChild(empty);
  } else {
    activeTurns.forEach((turn) => {
      const spkClass = getSpeakerClass(turn.speaker, activeSpeakers);
      const hasStart = turn.start != null && !isNaN(turn.start);
      const hasEnd = turn.end != null && !isNaN(turn.end);
      const startStr = hasStart ? formatDuration(turn.start) : "";
      const endStr = hasEnd ? formatDuration(turn.end) : "";

      if (hasStart) {
        const rangeTxt = hasEnd && endStr !== startStr ? `${startStr} - ${endStr}` : startStr;
        lines.push(`[${rangeTxt}] ${turn.speaker}: ${turn.text}`);
      } else {
        lines.push(`${turn.speaker}: ${turn.text}`);
      }

      const article = document.createElement("article");
      article.className = `turn ${spkClass}`;
      if (hasStart) article.setAttribute("data-start", String(turn.start));

      const header = document.createElement("div");
      header.className = "turn-header";

      const spkEl = document.createElement("span");
      spkEl.className = `turn-speaker ${spkClass}`;
      spkEl.textContent = turn.speaker;
      header.appendChild(spkEl);

      const roleTag = document.createElement("span");
      roleTag.className = "turn-role-tag";
      roleTag.setAttribute("data-role-for", turn.speaker);
      header.appendChild(roleTag);

      if (hasStart) {
        const timeBtn = document.createElement("button");
        timeBtn.type = "button";
        timeBtn.className = "turn-time";
        timeBtn.textContent = hasEnd && endStr !== startStr ? `${startStr} – ${endStr}` : startStr;
        timeBtn.title = activeHasAudio ? "Ir a este momento del audio" : "Marca de tiempo";
        timeBtn.addEventListener("click", () => jumpToMoment(turn.start));
        header.appendChild(timeBtn);
      }

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

  updateTurnRoleBadges();
  currentTranscriptText = lines.join("\n\n");
  resultCard.classList.remove("hidden");

  if (activeEvaluation) {
    renderJevReport(activeEvaluation, data.eval_elapsed_seconds);
  } else {
    jevReportCard.classList.add("hidden");
  }

  resultCard.scrollIntoView({ behavior: "smooth", block: "start" });
}

// JEV evaluation flow
async function startJevEvaluation() {
  if (!activeJobId) return;

  const isMock = mockModeCheckbox.checked;
  const hasInterviewer = Object.values(speakerRoleMap).includes("ENCUESTADOR");
  if (!hasInterviewer) {
    jevErrorInline.textContent =
      "Asigna al menos un hablante como ENCUESTADOR antes de ejecutar la evaluación con JEV.";
    jevErrorInline.classList.remove("hidden");
    return;
  }

  // Refresh status in case user just edited .env manually
  await fetchSystemStatus();
  if (!isMock && !hasOpenrouterKey) {
    openrouterSetupCard.classList.remove("hidden");
    jevErrorInline.textContent =
      "No se encontró OPENROUTER_API_KEY en el archivo .env. Agrégala en tu .env (o arriba) o activa el «Modo prueba sin conexión».";
    jevErrorInline.classList.remove("hidden");
    return;
  }

  stopEvalPolling();
  jevErrorInline.classList.add("hidden");
  evaluateBtn.disabled = true;
  jevRunningHint.textContent = isMock
    ? "Ejecutando evaluación simulada (modo prueba)…"
    : "Consultando modelo JEV en OpenRouter (evaluando 51 reglas ENCOVI A1–A2)…";
  jevRunningHint.classList.remove("hidden");

  try {
    const res = await fetch(`/api/jobs/${activeJobId}/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        speaker_map: speakerRoleMap,
        first_contact: firstContactCheckbox.checked,
        mock: isMock,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "No se pudo iniciar la evaluación con JEV.");

    pollEvaluation(activeJobId);
    evalPollTimer = setInterval(() => pollEvaluation(activeJobId), 1000);
  } catch (err) {
    jevRunningHint.classList.add("hidden");
    evaluateBtn.disabled = false;
    jevErrorInline.textContent = err.message || "Error al conectar con el servidor.";
    jevErrorInline.classList.remove("hidden");
  }
}

async function pollEvaluation(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Error consultando estado de la evaluación.");

    if (data.eval_status === "processing") {
      const secs = data.eval_elapsed_seconds != null ? `${data.eval_elapsed_seconds.toFixed(0)} s` : "";
      jevRunningHint.textContent = `Evaluando entrevista con JEV… ${secs}`;
      return;
    }

    stopEvalPolling();
    jevRunningHint.classList.add("hidden");
    evaluateBtn.disabled = false;

    if (data.eval_status === "completed" && data.evaluation) {
      activeEvaluation = data.evaluation;
      evaluateBtn.textContent = "Re-evaluar con JEV";
      renderJevReport(data.evaluation, data.eval_elapsed_seconds);
      jevReportCard.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (data.eval_status === "error") {
      jevErrorInline.textContent = data.eval_error || "Ocurrió un error al evaluar con JEV.";
      jevErrorInline.classList.remove("hidden");
    }
  } catch (err) {
    stopEvalPolling();
    jevRunningHint.classList.add("hidden");
    evaluateBtn.disabled = false;
    jevErrorInline.textContent = err.message || "Se perdió la conexión al consultar la evaluación.";
    jevErrorInline.classList.remove("hidden");
  }
}

function renderJevReport(report, elapsedSeconds) {
  const overall = report.overall || {};
  const verdict = overall.verdict || { label: "Evaluado", level: "muted" };
  const usage = report.usage || {};
  const windows = report.windows || [];
  const gates = report.gates || {};

  jevVerdictBadge.textContent = verdict.label;
  jevVerdictBadge.className = `pill pill-${verdict.level}`;

  const costVal = typeof usage.cost_usd === "number" ? `$${usage.cost_usd.toFixed(4)} USD` : "—";
  const tokensVal = typeof usage.input_tokens === "number" ? `${usage.input_tokens.toLocaleString("es-GT")} tokens` : "—";
  const cacheStr = usage.cache_hits ? ` (${usage.cache_hits} en caché)` : "";
  const timeStr = elapsedSeconds ? ` · ${elapsedSeconds.toFixed(1)} s` : "";
  jevReportMeta.textContent = `Modelo: ${report.model || "typesafe/jev-1.14"} · ${windows.length} ${windows.length === 1 ? "ventana" : "ventanas"} · ${usage.requests || 0} consultas${cacheStr} · ${tokensVal} · ${costVal}${timeStr}`;

  if (report.warning) {
    jevMockWarning.textContent = report.warning;
    jevMockWarning.classList.remove("hidden");
  } else {
    jevMockWarning.classList.add("hidden");
  }

  // Global KPI strip
  const openingGate = gates.opening != null ? formatPct(gates.opening) : "Omitida";
  const closingGate = gates.closing != null ? formatPct(gates.closing) : "n/a";
  const globalRate = overall.compliance_rate_weighted != null ? overall.compliance_rate_weighted : overall.compliance_rate;

  jevKpiStrip.innerHTML = "";
  const kpis = [
    {
      label: "Cumplimiento global",
      value: formatPct(globalRate),
      sub: `Simple: ${formatPct(overall.compliance_rate)} · Cobertura: ${formatPct(overall.coverage)}`,
      cls: getRateColorClass(globalRate),
    },
    {
      label: "Incumplimientos esperados",
      value: overall.expected_broken != null ? overall.expected_broken.toFixed(1) : "—",
      sub: `de ${overall.n_instructions || 51} instrucciones`,
      cls: "",
    },
    {
      label: "Riesgos altos (≥ 70 %)",
      value: String(overall.high_risk_count ?? 0),
      sub: `En revisión (30–69 %): ${overall.review_count ?? 0}`,
      cls: (overall.high_risk_count || 0) > 0 ? "rate-danger" : "rate-ok",
    },
    {
      label: "Compuertas detectadas",
      value: `${openingGate} / ${closingGate}`,
      sub: "Apertura / Cierre en el audio",
      cls: "",
    },
  ];

  kpis.forEach((k) => {
    const box = document.createElement("div");
    box.className = "kpi-box";
    box.innerHTML = `
      <div class="kpi-label">${k.label}</div>
      <div class="kpi-value ${k.cls}">${k.value}</div>
      <div class="kpi-sub">${k.sub}</div>
    `;
    jevKpiStrip.appendChild(box);
  });

  // A1 & A2 section cards
  jevSectionsGrid.innerHTML = "";
  const sections = report.sections || {};
  Object.entries(sections).forEach(([sid, sec]) => {
    const rate = sec.compliance_rate_weighted != null ? sec.compliance_rate_weighted : sec.compliance_rate;
    const rateCls = getRateColorClass(rate);
    const pctWidth = rate != null ? Math.round(rate * 100) : 0;

    const card = document.createElement("div");
    card.className = "section-card";
    card.innerHTML = `
      <div class="section-card-head">
        <div>
          <h3>${sid} · ${sec.title || sid}</h3>
          <span class="block-hint">${sec.n_instructions} instrucciones</span>
        </div>
        <span class="section-big-rate ${rateCls}">${formatPct(rate)}</span>
      </div>
      <div class="section-bar">
        <div class="section-bar-fill ${rateCls}" style="width: ${pctWidth}%"></div>
      </div>
      <div class="section-metrics">
        <div class="metric-row"><span>Cumplimiento simple</span><strong>${formatPct(sec.compliance_rate)}</strong></div>
        <div class="metric-row"><span>Conducta: marcadas / hora</span><strong>${sec.conduct_flagged_per_hour != null ? `${sec.conduct_flagged_per_hour.toFixed(2)} / h (${sec.conduct_flagged_windows || 0} vent.)` : "0.00 / h"}</strong></div>
        <div class="metric-row"><span>Incumplimientos esperados</span><strong>${sec.expected_broken != null ? sec.expected_broken.toFixed(1) : "—"}</strong></div>
        <div class="metric-row"><span>Cobertura evaluable</span><strong>${formatPct(sec.coverage)}</strong></div>
      </div>
    `;
    jevSectionsGrid.appendChild(card);
  });

  // Top risks list
  jevRisksList.innerHTML = "";
  const topRisks = overall.top_risks || [];
  if (topRisks.length === 0) {
    const okBox = document.createElement("div");
    okBox.className = "no-risks-box";
    okBox.textContent = "No se detectaron incumplimientos probables (probabilidad ≥ 30 %).";
    jevRisksList.appendChild(okBox);
  } else {
    topRisks.forEach((risk) => {
      const pBroken = Number(risk.p_broken || 0);
      const isHigh = pBroken >= 0.7;

      const item = document.createElement("div");
      item.className = `risk-item ${isHigh ? "" : "risk-review"}`;

      const topRow = document.createElement("div");
      topRow.className = "risk-top";

      const idBadge = document.createElement("span");
      idBadge.className = "rule-id-badge";
      idBadge.textContent = risk.id;
      topRow.appendChild(idBadge);

      const probPill = document.createElement("span");
      probPill.className = `pill ${isHigh ? "pill-danger" : "pill-warn"}`;
      probPill.textContent = `${formatPct(pBroken)} incumplimiento`;
      topRow.appendChild(probPill);

      const rangeStr = formatTimeRange(risk.time);
      if (rangeStr) {
        const tsBtn = document.createElement("button");
        tsBtn.type = "button";
        tsBtn.className = "turn-time";
        tsBtn.textContent = `Ventana ${risk.worst_window + 1} · ${rangeStr}`;
        tsBtn.title = "Ir a este momento de la entrevista";
        tsBtn.addEventListener("click", () => jumpToMoment(risk.time[0]));
        topRow.appendChild(tsBtn);
      }

      const txt = document.createElement("p");
      txt.className = "risk-text";
      txt.textContent = risk.text;

      item.appendChild(topRow);
      item.appendChild(txt);
      jevRisksList.appendChild(item);
    });
  }

  // Full 51-rule table
  renderRulesTable();
  jevReportCard.classList.remove("hidden");
}

function classifyRule(ins) {
  const c = Number(ins.p_followed || 0);
  const v = Number(ins.p_broken || 0);
  const u = Number(ins.p_unknown || 0);
  if (v >= 0.7) return "broken";
  if (v >= 0.3) return "review";
  if (u >= 0.7 && c < 0.3) return "unknown";
  return "followed";
}

function renderRulesTable() {
  if (!activeEvaluation) return;
  const all = activeEvaluation.instructions || [];
  const secFilter = ruleSectionFilter.value;
  const query = ruleSearchInput.value.trim().toLowerCase();

  const filtered = all.filter((ins) => {
    if (secFilter !== "ALL" && ins.section !== secFilter) return false;
    if (currentRuleFilter !== "all" && classifyRule(ins) !== currentRuleFilter) return false;
    if (query) {
      const hay = `${ins.id} ${ins.text} ${ins.note || ""}`.toLowerCase();
      if (!hay.includes(query)) return false;
    }
    return true;
  });

  jevRulesCountPill.textContent = `${filtered.length} de ${all.length} reglas`;
  jevRulesTableBody.innerHTML = "";

  if (!filtered.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.className = "subtitle";
    td.textContent = "No hay reglas que coincidan con este filtro.";
    tr.appendChild(td);
    jevRulesTableBody.appendChild(tr);
    return;
  }

  filtered.forEach((ins) => {
    const tr = document.createElement("tr");

    // Col 1: Rule ID + text + page/note
    const tdRule = document.createElement("td");
    const idEl = document.createElement("span");
    idEl.className = "rule-id-badge";
    idEl.textContent = ins.id;
    tdRule.appendChild(idEl);

    const textNode = document.createTextNode(` ${ins.text}`);
    tdRule.appendChild(textNode);

    const metaBits = [];
    if (ins.pages) metaBits.push(`Manual p. ${ins.pages}`);
    if (ins.verifiability) metaBits.push(`Audibilidad: ${ins.verifiability}`);
    if (ins.note) metaBits.push(ins.note);
    if (metaBits.length) {
      const metaDiv = document.createElement("div");
      metaDiv.className = "rule-meta-line";
      metaDiv.textContent = metaBits.join(" · ");
      tdRule.appendChild(metaDiv);
    }

    // Col 2: Kind
    const tdKind = document.createElement("td");
    tdKind.textContent = KIND_LABELS[ins.kind] || ins.kind;

    // Col 3: Weight
    const tdWeight = document.createElement("td");
    tdWeight.textContent = WEIGHT_LABELS[ins.weight] || String(ins.weight || "1");

    // Col 4: Probabilities bar
    const tdProb = document.createElement("td");
    const c = Number(ins.p_followed || 0);
    const v = Number(ins.p_broken || 0);
    const u = Number(ins.p_unknown || 0);
    tdProb.innerHTML = `
      <div class="prob-bar" title="Cumplida ${formatPct(c)} · Incumplida ${formatPct(v)} · No aplica ${formatPct(u)}">
        <div class="prob-c" style="width:${(c * 100).toFixed(1)}%"></div>
        <div class="prob-v" style="width:${(v * 100).toFixed(1)}%"></div>
        <div class="prob-u" style="width:${(u * 100).toFixed(1)}%"></div>
      </div>
      <div class="prob-nums">
        <span class="p-ok">C: ${formatPct(c)}</span>
        <span class="p-bad">I: ${formatPct(v)}</span>
        <span class="p-na">N/A: ${formatPct(u)}</span>
      </div>
    `;

    // Col 5: Worst window timestamp
    const tdTime = document.createElement("td");
    const ww = ins.worst_window;
    const rangeStr = ww ? formatTimeRange(ww.time) : null;
    if (ww && rangeStr) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "turn-time";
      btn.textContent = rangeStr;
      btn.title = `Ventana ${ww.window + 1} (${formatPct(ww.p_broken)} incumplimiento)`;
      btn.addEventListener("click", () => jumpToMoment(ww.time[0]));
      tdTime.appendChild(btn);
    } else if (ww) {
      tdTime.textContent = `Ventana ${ww.window + 1}`;
    } else {
      tdTime.textContent = "—";
    }

    tr.appendChild(tdRule);
    tr.appendChild(tdKind);
    tr.appendChild(tdWeight);
    tr.appendChild(tdProb);
    tr.appendChild(tdTime);
    jevRulesTableBody.appendChild(tr);
  });
}

ruleStatusFilters.addEventListener("click", (e) => {
  const btn = e.target.closest(".filter-pill");
  if (!btn) return;
  currentRuleFilter = btn.getAttribute("data-filter") || "all";
  ruleStatusFilters.querySelectorAll(".filter-pill").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  renderRulesTable();
});

ruleSectionFilter.addEventListener("change", renderRulesTable);
ruleSearchInput.addEventListener("input", renderRulesTable);

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

downloadJevBtn.addEventListener("click", () => {
  if (!activeJobId) return;
  window.location.href = `/api/jobs/${activeJobId}/evaluation/download`;
});

transcribeBtn.addEventListener("click", startTranscription);
uploadTranscriptBtn.addEventListener("click", uploadExistingTranscript);
loadExampleBtn.addEventListener("click", loadExampleTranscript);
evaluateBtn.addEventListener("click", startJevEvaluation);

retryBtn.addEventListener("click", () => {
  errorCard.classList.add("hidden");
  if (!audioModePanel.classList.contains("hidden") && selectedFile) {
    startTranscription();
  } else if (selectedTranscriptFile) {
    uploadExistingTranscript();
  }
});

fetchSystemStatus();
