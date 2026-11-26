import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  editJobEvaluationRule,
  evaluateJobWithJev,
  fetchRulesCatalog,
  fitCalibrationNow,
  getCalibrationStatus,
  getJob,
  getSystemStatus,
  listRecentJobs,
  loadExampleTranscript,
  resetGlobalRuleOverride,
  saveApiKeys,
  saveGlobalRuleOverride,
  uploadAudioDirectToSupabaseAndStart,
  uploadAudioMultipartAndStart,
  uploadTranscriptFile,
} from "./api";
import { CalibrationModal } from "./components/CalibrationModal";
import { EvaluationRuleModal } from "./components/EvaluationRuleModal";
import { RulesCatalogModal } from "./components/RulesCatalogModal";
import type {
  AuditJob,
  CalibrationStatus,
  EvaluatedInstruction,
  EvaluationRuleEditRequest,
  JobSummary,
  RuleCatalogItem,
  RuleOverrideInput,
  SpeakerRole,
  SttProvider,
  SystemStatus,
} from "./types";

const ROLE_OPTIONS: SpeakerRole[] = ["ENCUESTADOR", "INFORMANTE", "OTRA_PERSONA"];

const KIND_LABELS: Record<string, string> = {
  obligation: "Obligación",
  prohibition: "Prohibición",
  conditional: "Condicional",
  evidence: "Evidencia",
};

const WEIGHT_LABELS: Record<number, string> = {
  1: "Baja (1)",
  2: "Media (2)",
  3: "Alta (3)",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "";
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function formatPct(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return "n/a";
  return `${(value * 100).toFixed(digits)} %`;
}

function formatTimeRange(timeArr?: [number | null, number | null] | null): string | null {
  if (!Array.isArray(timeArr) || (timeArr[0] == null && timeArr[1] == null)) return null;
  const a = timeArr[0] != null ? formatDuration(timeArr[0]) : "—";
  const b = timeArr[1] != null ? formatDuration(timeArr[1]) : "—";
  return a === b ? a : `${a} – ${b}`;
}

function getRateColorClass(rate: number | null | undefined): string {
  if (rate == null) return "";
  if (rate >= 0.85) return "rate-ok";
  if (rate >= 0.7) return "rate-warn";
  return "rate-danger";
}

function getSpeakerClass(speakerLabel: string, speakerOrder: string[]): string {
  const idx = speakerOrder.indexOf(speakerLabel);
  if (idx === -1) return "spk-default";
  return `spk-${idx % 6}`;
}

function parseSpeakerBounds(val: string): { min: number | null; max: number | null } {
  if (val === "2") return { min: 2, max: 2 };
  if (val === "3") return { min: 3, max: 3 };
  if (val === "2-4") return { min: 2, max: 4 };
  if (val === "2-6") return { min: 2, max: 6 };
  return { min: null, max: null };
}

function classifyRule(ins: EvaluatedInstruction): string {
  const c = Number(ins.p_followed || 0);
  const v = Number(ins.p_broken || 0);
  const u = Number(ins.p_unknown || 0);
  const wf = Number(ins.windows_flagged || 0);
  const wr = Number(ins.windows_review || 0);
  if (v >= 0.7 || wf > 0) return "broken";
  if (v >= 0.3 || wr > 0) return "review";
  if (u >= 0.7 && c < 0.3) return "unknown";
  return "followed";
}

export const App: React.FC = () => {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [calibrationStatus, setCalibrationStatus] = useState<CalibrationStatus | null>(null);
  const [showCalibrationModal, setShowCalibrationModal] = useState<boolean>(false);
  const [recentJobs, setRecentJobs] = useState<JobSummary[]>([]);
  const [rulesCatalog, setRulesCatalog] = useState<RuleCatalogItem[]>([]);

  // Settings drawer
  const [showKeysPanel, setShowKeysPanel] = useState<boolean>(false);
  const [assemblyKeyInput, setAssemblyKeyInput] = useState<string>("");
  const [deepgramKeyInput, setDeepgramKeyInput] = useState<string>("");
  const [openrouterKeyInput, setOpenrouterKeyInput] = useState<string>("");
  const [hfTokenInput, setHfTokenInput] = useState<string>("");
  const [supabaseUrlInput, setSupabaseUrlInput] = useState<string>("");
  const [supabaseKeyInput, setSupabaseKeyInput] = useState<string>("");
  const [keysFeedback, setKeysFeedback] = useState<{ text: string; ok: boolean } | null>(null);
  const [savingKeys, setSavingKeys] = useState<boolean>(false);

  // Upload tabs & options
  const [modeTab, setModeTab] = useState<"audio" | "transcript">("audio");
  const [selectedAudioFile, setSelectedAudioFile] = useState<File | null>(null);
  const [selectedTranscriptFile, setSelectedTranscriptFile] = useState<File | null>(null);
  const [sttProvider, setSttProvider] = useState<SttProvider>("assemblyai");
  const [providerInitialized, setProviderInitialized] = useState<boolean>(false);
  const [speakersOption, setSpeakersOption] = useState<string>("auto");
  const [whisperModel, setWhisperModel] = useState<string>("large-v3-turbo");
  const [denoise, setDenoise] = useState<boolean>(true);
  const [diarize, setDiarize] = useState<boolean>(true);

  // Active job & polling
  const [activeJob, setActiveJob] = useState<AuditJob | null>(null);
  const [isUploadingOrStarting, setIsUploadingOrStarting] = useState<boolean>(false);
  const [uploadStageOverride, setUploadStageOverride] = useState<string | null>(null);
  const [uploadPctOverride, setUploadPctOverride] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Speaker role mapper & JEV evaluation
  const [speakerRoleMap, setSpeakerRoleMap] = useState<Record<string, SpeakerRole>>({});
  const [firstContact, setFirstContact] = useState<boolean>(true);
  const [mockMode, setMockMode] = useState<boolean>(false);
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);
  const [jevInlineError, setJevInlineError] = useState<string | null>(null);
  const [copiedBanner, setCopiedBanner] = useState<boolean>(false);
  const [highlightedTurnIdx, setHighlightedTurnIdx] = useState<number | null>(null);

  // Report table filters
  const [ruleStatusFilter, setRuleStatusFilter] = useState<string>("all");
  const [ruleSectionFilter, setRuleSectionFilter] = useState<string>("ALL");
  const [ruleSearch, setRuleSearch] = useState<string>("");

  // Evaluation & Rule Editing Modals
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [editingGlobalOnly, setEditingGlobalOnly] = useState<boolean>(false);
  const [showCatalogModal, setShowCatalogModal] = useState<boolean>(false);

  const audioInputRef = useRef<HTMLInputElement | null>(null);
  const transcriptInputRef = useRef<HTMLInputElement | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const transcriptListRef = useRef<HTMLDivElement | null>(null);
  const reportCardRef = useRef<HTMLElement | null>(null);

  const refreshMetadata = useCallback(async () => {
    try {
      const [st, jobsList, rulesData, calData] = await Promise.all([
        getSystemStatus(),
        listRecentJobs(20).catch(() => [] as JobSummary[]),
        fetchRulesCatalog().catch(() => ({ rules: [] as RuleCatalogItem[], customized_count: 0 })),
        getCalibrationStatus().catch(() => null),
      ]);
      setStatus(st);
      setCalibrationStatus(calData || st.calibration || null);
      setRecentJobs(jobsList);
      setRulesCatalog(rulesData.rules);

      if (!providerInitialized) {
        setSttProvider(st.recommended_stt_provider);
        setProviderInitialized(true);
      }
    } catch {
      // Server temporarily unreachable
    }
  }, [providerInitialized]);

  useEffect(() => {
    void refreshMetadata();
  }, [refreshMetadata]);

  // Sync speaker role map whenever a new transcript result arrives
  const hydrateJobIntoView = useCallback((job: AuditJob) => {
    setActiveJob(job);
    const res = job.result;
    if (res) {
      const spks =
        res.speakers && res.speakers.length > 0
          ? res.speakers
          : Array.from(new Set((res.turns || []).map((t) => t.speaker)));
      const baseMap: Record<string, SpeakerRole> = {
        ...(job.evaluation?.speaker_map || res.suggested_roles || {}),
      };
      spks.forEach((spk, idx) => {
        if (!baseMap[spk]) {
          baseMap[spk] = idx === 0 ? "ENCUESTADOR" : idx === 1 ? "INFORMANTE" : "OTRA_PERSONA";
        }
      });
      setSpeakerRoleMap(baseMap);
    }
  }, []);

  // Poll active transcription job while queued/processing
  useEffect(() => {
    if (!activeJob || (activeJob.status !== "queued" && activeJob.status !== "processing")) {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const updated = await getJob(activeJob.job_id);
        if (updated.status === "completed") {
          hydrateJobIntoView(updated);
          void refreshMetadata();
        } else if (updated.status === "error") {
          setActiveJob(updated);
          setErrorMessage(updated.error || "Ocurrió un error procesando el audio.");
        } else {
          setActiveJob(updated);
        }
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : "Error consultando el avance.");
      }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [activeJob, hydrateJobIntoView, refreshMetadata]);

  const activeTurns = useMemo(() => activeJob?.result?.turns || [], [activeJob]);
  const activeSpeakers = useMemo(() => {
    const raw = activeJob?.result?.speakers || [];
    if (raw.length > 0) return raw;
    return Array.from(new Set(activeTurns.map((t) => t.speaker)));
  }, [activeJob, activeTurns]);

  const handleSaveKeys = async () => {
    setSavingKeys(true);
    setKeysFeedback(null);
    try {
      const resp = await saveApiKeys({
        assemblyai_key: assemblyKeyInput || undefined,
        deepgram_key: deepgramKeyInput || undefined,
        openrouter_key: openrouterKeyInput || undefined,
        hf_token: hfTokenInput || undefined,
        supabase_url: supabaseUrlInput || undefined,
        supabase_key: supabaseKeyInput || undefined,
      });
      setAssemblyKeyInput("");
      setDeepgramKeyInput("");
      setOpenrouterKeyInput("");
      setHfTokenInput("");
      setSupabaseKeyInput("");
      setKeysFeedback({
        text: resp.note || `Claves actualizadas: ${resp.updated.join(", ")}`,
        ok: true,
      });
      await refreshMetadata();
    } catch (err) {
      setKeysFeedback({
        text: err instanceof Error ? err.message : "Error guardando configuración.",
        ok: false,
      });
    } finally {
      setSavingKeys(false);
    }
  };

  const handleStartAudioTranscription = async () => {
    if (!selectedAudioFile) return;
    setErrorMessage(null);
    setJevInlineError(null);

    if (sttProvider === "local_whisperx" && diarize && !status?.hf_token_configured) {
      setShowKeysPanel(true);
      setErrorMessage(
        "Para usar Pyannote local necesitas HF_TOKEN, o cambia el motor arriba a AssemblyAI / Deepgram (no requieren HF_TOKEN ni GPU)."
      );
      return;
    }
    if (sttProvider === "assemblyai" && !status?.assemblyai_configured) {
      setShowKeysPanel(true);
      setErrorMessage(
        "Configura ASSEMBLYAI_API_KEY arriba (incluye $50 USD gratis y diarización en español a ~$0.17/h sin HF_TOKEN)."
      );
      return;
    }
    if (sttProvider === "deepgram" && !status?.deepgram_configured) {
      setShowKeysPanel(true);
      setErrorMessage(
        "Configura DEEPGRAM_API_KEY arriba (incluye $200 USD gratis y diarización rápida sin HF_TOKEN)."
      );
      return;
    }

    const bounds = parseSpeakerBounds(speakersOption);
    setIsUploadingOrStarting(true);
    setUploadStageOverride("Subiendo archivo de audio…");
    setUploadPctOverride(4);

    try {
      let jobId: string;
      const useDirectSupabase =
        Boolean(status?.supabase_configured) && sttProvider !== "local_whisperx";

      if (useDirectSupabase) {
        setUploadStageOverride("Subiendo audio directamente a Supabase Storage…");
        const res = await uploadAudioDirectToSupabaseAndStart({
          file: selectedAudioFile,
          provider: sttProvider,
          diarize,
          minSpeakers: bounds.min,
          maxSpeakers: bounds.max,
          onUploadProgress: (pct) => {
            setUploadPctOverride(Math.max(5, Math.min(95, pct)));
            setUploadStageOverride(`Subiendo audio a Supabase Storage (${pct} %)…`);
          },
        });
        jobId = res.job_id;
      } else {
        if (status?.is_vercel && selectedAudioFile.size > 4.2 * 1024 * 1024) {
          throw new Error(
            "Este archivo supera los 4.5 MB del límite serverless de Vercel. Configura SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY para subir grabaciones largas directo a Supabase Storage."
          );
        }
        const res = await uploadAudioMultipartAndStart({
          file: selectedAudioFile,
          provider: sttProvider,
          model: whisperModel,
          denoise,
          diarize,
          minSpeakers: bounds.min,
          maxSpeakers: bounds.max,
        });
        jobId = res.job_id;
      }

      const initialJob = await getJob(jobId);
      hydrateJobIntoView(initialJob);
      void refreshMetadata();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Error iniciando la transcripción.");
    } finally {
      setIsUploadingOrStarting(false);
      setUploadStageOverride(null);
      setUploadPctOverride(null);
    }
  };

  const handleUploadTranscript = async () => {
    if (!selectedTranscriptFile) return;
    setErrorMessage(null);
    setJevInlineError(null);
    setIsUploadingOrStarting(true);
    try {
      const job = await uploadTranscriptFile(selectedTranscriptFile);
      hydrateJobIntoView(job);
      void refreshMetadata();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Error leyendo la transcripción.");
    } finally {
      setIsUploadingOrStarting(false);
    }
  };

  const handleLoadExample = async () => {
    setErrorMessage(null);
    setJevInlineError(null);
    setIsUploadingOrStarting(true);
    try {
      const job = await loadExampleTranscript();
      hydrateJobIntoView(job);
      void refreshMetadata();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "No se pudo cargar el ejemplo ENCOVI.");
    } finally {
      setIsUploadingOrStarting(false);
    }
  };

  const handleSelectHistoryJob = async (jobId: string) => {
    if (!jobId) return;
    setErrorMessage(null);
    setJevInlineError(null);
    try {
      const job = await getJob(jobId);
      hydrateJobIntoView(job);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "No se pudo abrir la entrevista.");
    }
  };

  const runEvaluation = useCallback(
    async (jobId: string, roles: Record<string, SpeakerRole>) => {
      if (!Object.values(roles).includes("ENCUESTADOR")) {
        setJevInlineError(
          "Asigna al menos un hablante como ENCUESTADOR antes de ejecutar la evaluación con JEV."
        );
        return;
      }
      if (!mockMode && !status?.openrouter_configured) {
        setShowKeysPanel(true);
        setJevInlineError(
          "Falta OPENROUTER_API_KEY. Agrégala en Configuración de claves arriba o activa el «Modo prueba sin conexión»."
        );
        return;
      }

      setIsEvaluating(true);
      setJevInlineError(null);
      try {
        const updatedJob = await evaluateJobWithJev(jobId, {
          speaker_map: roles,
          first_contact: firstContact,
          mock: mockMode,
        });
        hydrateJobIntoView(updatedJob);
        void refreshMetadata();
        window.setTimeout(() => {
          reportCardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 120);
      } catch (err) {
        setJevInlineError(err instanceof Error ? err.message : "Error al evaluar con JEV.");
      } finally {
        setIsEvaluating(false);
      }
    },
    [firstContact, hydrateJobIntoView, mockMode, refreshMetadata, status?.openrouter_configured]
  );

  const jumpToMoment = (seconds: number | null | undefined) => {
    if (seconds == null || Number.isNaN(seconds)) return;
    if (activeJob?.has_audio && audioPlayerRef.current) {
      audioPlayerRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
      audioPlayerRef.current.currentTime = Math.max(0, seconds);
      audioPlayerRef.current.play().catch(() => {});
    }

    if (!activeTurns.length) return;
    let bestIdx = 0;
    let bestDiff = Infinity;
    activeTurns.forEach((t, idx) => {
      if (t.start != null) {
        const diff = Math.abs(t.start - seconds);
        if (diff < bestDiff) {
          bestDiff = diff;
          bestIdx = idx;
        }
      }
    });

    setHighlightedTurnIdx(bestIdx);
    const el = transcriptListRef.current?.querySelector(`[data-turn-idx="${bestIdx}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    window.setTimeout(() => setHighlightedTurnIdx(null), 2200);
  };

  const handleCopyTranscript = async () => {
    if (!activeTurns.length) return;
    const text = activeTurns
      .map((t) => {
        const startStr = t.start != null ? formatDuration(t.start) : "";
        const endStr = t.end != null ? formatDuration(t.end) : "";
        const ts =
          startStr && endStr && startStr !== endStr
            ? `[${startStr} - ${endStr}] `
            : startStr
            ? `[${startStr}] `
            : "";
        return `${ts}${t.speaker}: ${t.text}`;
      })
      .join("\n\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopiedBanner(true);
      window.setTimeout(() => setCopiedBanner(false), 1800);
    } catch {
      setErrorMessage("No se pudo copiar al portapapeles.");
    }
  };

  // Editing handlers
  const openRuleEditorFromEvaluation = (ruleId: string) => {
    setEditingGlobalOnly(false);
    setEditingRuleId(ruleId);
  };

  const openRuleEditorGlobal = (rule: RuleCatalogItem) => {
    setShowCatalogModal(false);
    setEditingGlobalOnly(true);
    setEditingRuleId(rule.id);
  };

  const activeEditingRuleSpec = useMemo(
    () => rulesCatalog.find((r) => r.id === editingRuleId) || null,
    [rulesCatalog, editingRuleId]
  );

  const activeEditingEvaluatedRule = useMemo(() => {
    if (editingGlobalOnly || !editingRuleId || !activeJob?.evaluation) return null;
    return activeJob.evaluation.instructions.find((i) => i.id === editingRuleId) || null;
  }, [editingGlobalOnly, editingRuleId, activeJob]);

  const handleSaveInterviewAndRule = async (
    ruleId: string,
    payload: EvaluationRuleEditRequest,
    reEvaluateNow: boolean
  ) => {
    if (!activeJob) return;
    const resp = await editJobEvaluationRule(activeJob.job_id, ruleId, payload);
    hydrateJobIntoView(resp.job);
    await refreshMetadata();
    if (reEvaluateNow) {
      await runEvaluation(activeJob.job_id, speakerRoleMap);
    }
  };

  const handleSaveGlobalRuleOnly = async (ruleId: string, payload: RuleOverrideInput) => {
    await saveGlobalRuleOverride(ruleId, payload);
    await refreshMetadata();
  };

  const handleResetGlobalRule = async (ruleId: string) => {
    await resetGlobalRuleOverride(ruleId);
    await refreshMetadata();
  };

  const filteredInstructions = useMemo(() => {
    const all = activeJob?.evaluation?.instructions || [];
    const q = ruleSearch.trim().toLowerCase();
    return all.filter((ins) => {
      if (ruleSectionFilter !== "ALL" && ins.section !== ruleSectionFilter) return false;
      if (ruleStatusFilter === "edited") {
        if (!ins.manual_override && !ins.is_rule_customized) return false;
      } else if (ruleStatusFilter !== "all" && classifyRule(ins) !== ruleStatusFilter) {
        return false;
      }
      if (q) {
        const hay = `${ins.id} ${ins.text} ${ins.note || ""} ${
          ins.manual_override?.comment || ""
        } ${ins.auditor_guidance || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [activeJob?.evaluation, ruleSectionFilter, ruleStatusFilter, ruleSearch]);

  const isJobRunning =
    isUploadingOrStarting ||
    activeJob?.status === "queued" ||
    activeJob?.status === "processing";

  const currentProgressPct =
    uploadPctOverride != null
      ? uploadPctOverride
      : Math.max(2, Math.min(100, Math.round(activeJob?.progress || 0)));

  const currentProgressStage =
    uploadStageOverride || activeJob?.stage || "Procesando entrevista…";

  const evaluation = activeJob?.evaluation || null;
  const overall = evaluation?.overall;

  return (
    <div className="page">
      {/* HEADER */}
      <header className="header">
        <div>
          <h1>Auditoría de Entrevistas ENCOVI</h1>
          <p className="subtitle">
            Frontend TypeScript + Backend Python FastAPI · Despliegue listo para Vercel + Supabase · Evaluación JEV editable
          </p>
        </div>

        <div className="status-pills">
          <span className={`pill ${status?.is_vercel ? "pill-blue" : status?.cuda_available ? "pill-ok" : "pill-muted"}`}>
            {status?.is_vercel
              ? "Entorno: Vercel Serverless"
              : status?.cuda_available
              ? `GPU Local: ${status.gpu_name}`
              : status
              ? "Servidor Local"
              : "Conectando…"}
          </span>

          <button
            type="button"
            className={`pill pill-btn ${status?.supabase_configured ? "pill-ok" : "pill-warn"}`}
            onClick={() => setShowKeysPanel((v) => !v)}
            title="Configurar Supabase y claves de API"
          >
            {status?.supabase_configured ? "Supabase: conectado" : "Persistencia local"}
          </button>

          <button
            type="button"
            className={`pill pill-btn ${
              status?.assemblyai_configured || status?.deepgram_configured || status?.hf_token_configured
                ? "pill-ok"
                : "pill-warn"
            }`}
            onClick={() => setShowKeysPanel((v) => !v)}
          >
            {status?.assemblyai_configured
              ? "STT: AssemblyAI listo"
              : status?.deepgram_configured
              ? "STT: Deepgram listo"
              : status?.hf_token_configured
              ? "STT: WhisperX local listo"
              : "Configurar STT"}
          </button>

          <button
            type="button"
            className={`pill pill-btn ${status?.openrouter_configured ? "pill-ok" : "pill-warn"}`}
            onClick={() => setShowKeysPanel((v) => !v)}
          >
            {status?.openrouter_configured ? "JEV OpenRouter: listo" : "Falta OPENROUTER_API_KEY"}
          </button>

          <button
            type="button"
            className="pill pill-blue pill-btn"
            onClick={() => setShowCatalogModal(true)}
          >
            51 Reglas JEV
            {status?.customized_rules_count ? ` (${status.customized_rules_count} editadas)` : ""}
          </button>

          <button
            type="button"
            className={`pill pill-btn ${calibrationStatus?.is_calibrated ? "pill-ok" : "pill-muted"}`}
            onClick={() => setShowCalibrationModal(true)}
            title="Ver progreso de calibración desde correcciones del supervisor"
          >
            {calibrationStatus?.is_calibrated
              ? `Calibración: activa (${
                  Object.values(calibrationStatus.groups || {}).filter((g) => g.fitted).length
                } grupos)`
              : `Calibración: ${calibrationStatus?.total_labels ?? 0} etiquetas`}
          </button>
        </div>
      </header>

      <main className="main">
        {/* API KEYS & SUPABASE CONFIG DRAWER */}
        {showKeysPanel && (
          <section className="card notice-card notice-blue">
            <div className="notice-header">
              <strong>Configuración de claves (STT sin Hugging Face, OpenRouter JEV y Supabase)</strong>
              <button type="button" className="btn-link" onClick={() => setShowKeysPanel(false)}>
                Ocultar
              </button>
            </div>
            <p className="notice-text">
              Para distinguir hablantes en Vercel o sin token de Hugging Face, usa{" "}
              <strong>AssemblyAI (~$0.17 USD/hora con diarización incluida + $50 gratis)</strong> o{" "}
              <strong>Deepgram Nova-3 ($200 gratis)</strong>. En producción en Vercel define estas variables en{" "}
              <em>Project Settings → Environment Variables</em>.
            </p>

            <div className="keys-grid">
              <div className="field">
                <label>ASSEMBLYAI_API_KEY (Recomendado · sin HF_TOKEN)</label>
                <input
                  type="password"
                  placeholder={status?.assemblyai_configured ? "Configurada (pega otra para reemplazar)" : "Clave de AssemblyAI…"}
                  value={assemblyKeyInput}
                  onChange={(e) => setAssemblyKeyInput(e.target.value)}
                />
              </div>

              <div className="field">
                <label>DEEPGRAM_API_KEY (Alternativa rápida · sin HF_TOKEN)</label>
                <input
                  type="password"
                  placeholder={status?.deepgram_configured ? "Configurada (pega otra para reemplazar)" : "Clave de Deepgram…"}
                  value={deepgramKeyInput}
                  onChange={(e) => setDeepgramKeyInput(e.target.value)}
                />
              </div>

              <div className="field">
                <label>OPENROUTER_API_KEY (Evaluación JEV typesafe/jev-1.14)</label>
                <input
                  type="password"
                  placeholder={status?.openrouter_configured ? "Configurada (sk-or-...)" : "sk-or-..."}
                  value={openrouterKeyInput}
                  onChange={(e) => setOpenrouterKeyInput(e.target.value)}
                />
              </div>

              <div className="field">
                <label>HF_TOKEN (Opcional · solo para Pyannote local en tu GPU)</label>
                <input
                  type="password"
                  placeholder={status?.hf_token_configured ? "Configurado (hf_...)" : "hf_..."}
                  value={hfTokenInput}
                  onChange={(e) => setHfTokenInput(e.target.value)}
                />
              </div>

              <div className="field">
                <label>SUPABASE_URL (Base de datos y Storage de audios)</label>
                <input
                  type="text"
                  placeholder={status?.supabase_configured ? "Configurada (https://...supabase.co)" : "https://xyz.supabase.co"}
                  value={supabaseUrlInput}
                  onChange={(e) => setSupabaseUrlInput(e.target.value)}
                />
              </div>

              <div className="field">
                <label>SUPABASE_SERVICE_ROLE_KEY</label>
                <input
                  type="password"
                  placeholder={status?.supabase_configured ? "Configurada" : "service_role secret…"}
                  value={supabaseKeyInput}
                  onChange={(e) => setSupabaseKeyInput(e.target.value)}
                />
              </div>
            </div>

            <div className="actions-row" style={{ marginTop: 14 }}>
              <button
                type="button"
                className="btn btn-primary"
                disabled={savingKeys}
                onClick={handleSaveKeys}
              >
                {savingKeys ? "Guardando…" : "Guardar claves"}
              </button>
              {keysFeedback && (
                <span className={`feedback-msg ${keysFeedback.ok ? "ok" : "err"}`}>
                  {keysFeedback.text}
                </span>
              )}
            </div>
          </section>
        )}

        {/* RECENT AUDITS BAR (SUPABASE / LOCAL HISTORY) */}
        {recentJobs.length > 0 && (
          <section className="history-bar">
            <span className="history-label">Entrevistas recientes:</span>
            <div className="history-pills">
              {recentJobs.slice(0, 8).map((j) => {
                const isSelected = activeJob?.job_id === j.job_id;
                return (
                  <button
                    key={j.job_id}
                    type="button"
                    className={`history-chip ${isSelected ? "active" : ""}`}
                    onClick={() => handleSelectHistoryJob(j.job_id)}
                  >
                    <span className="history-name">{j.filename}</span>
                    {j.compliance_rate_weighted != null && (
                      <span className={`history-score ${getRateColorClass(j.compliance_rate_weighted)}`}>
                        {formatPct(j.compliance_rate_weighted)}
                      </span>
                    )}
                    {(j.manual_edit_count || 0) > 0 && (
                      <span className="history-edit-dot" title="Contiene evaluaciones editadas">
                        ✎ {j.manual_edit_count}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </section>
        )}

        {/* UPLOAD CARD */}
        <section className="card upload-card">
          <div className="mode-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={modeTab === "audio"}
              className={`mode-tab ${modeTab === "audio" ? "active" : ""}`}
              onClick={() => {
                setModeTab("audio");
                setErrorMessage(null);
              }}
            >
              1. Subir audio (con separación de hablantes)
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={modeTab === "transcript"}
              className={`mode-tab ${modeTab === "transcript" ? "active" : ""}`}
              onClick={() => {
                setModeTab("transcript");
                setErrorMessage(null);
              }}
            >
              2. Subir transcripción (.json / .txt)
            </button>
          </div>

          {modeTab === "audio" ? (
            <div>
              <div
                className="dropzone"
                tabIndex={0}
                role="button"
                onClick={() => audioInputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    audioInputRef.current?.click();
                  }
                }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (e.dataTransfer.files?.[0]) {
                    setSelectedAudioFile(e.dataTransfer.files[0]);
                  }
                }}
              >
                <input
                  ref={audioInputRef}
                  type="file"
                  hidden
                  accept="audio/*,video/mp4,video/webm,.mp3,.wav,.m4a,.ogg,.flac,.aac,.opus,.wma,.mp4,.webm"
                  onChange={(e) => {
                    if (e.target.files?.[0]) setSelectedAudioFile(e.target.files[0]);
                  }}
                />
                <p className="dropzone-title">
                  Arrastra tu grabación aquí o haz clic para seleccionarla
                </p>
                <p className="dropzone-hint">
                  Soporta MP3, WAV, M4A, OGG, FLAC y MP4 · Con Supabase Storage admite entrevistas largas (30 min – 2 h) en Vercel sin límite de 4.5 MB
                </p>
              </div>

              {selectedAudioFile && (
                <div className="file-selected">
                  <div className="file-info">
                    <span className="file-name">{selectedAudioFile.name}</span>
                    <span className="file-size">{formatBytes(selectedAudioFile.size)}</span>
                  </div>
                  <button
                    type="button"
                    className="btn-link"
                    onClick={() => {
                      setSelectedAudioFile(null);
                      if (audioInputRef.current) audioInputRef.current.value = "";
                    }}
                  >
                    Cambiar archivo
                  </button>
                </div>
              )}

              <div className="options-grid">
                <div className="field">
                  <label htmlFor="providerSelect">Motor de voz a texto y hablantes</label>
                  <select
                    id="providerSelect"
                    value={sttProvider}
                    onChange={(e) => setSttProvider(e.target.value as SttProvider)}
                  >
                    <option value="assemblyai">
                      AssemblyAI Universal-2 (~$0.17/h · Sin HF_TOKEN · Ideal Vercel)
                    </option>
                    <option value="deepgram">
                      Deepgram Nova-3 ($200 créditos gratis · Sin HF_TOKEN · Ideal Vercel)
                    </option>
                    <option
                      value="local_whisperx"
                      disabled={Boolean(status?.is_vercel || !status?.local_whisper_available)}
                    >
                      WhisperX + Pyannote Local (100 % en tu GPU · Solo servidor local)
                    </option>
                  </select>
                </div>

                <div className="field">
                  <label htmlFor="speakersSelect">Número de hablantes</label>
                  <select
                    id="speakersSelect"
                    value={speakersOption}
                    onChange={(e) => setSpeakersOption(e.target.value)}
                  >
                    <option value="auto">Automático</option>
                    <option value="2">Exactamente 2 hablantes (entrevista 1 a 1)</option>
                    <option value="3">Exactamente 3 hablantes</option>
                    <option value="2-4">Entre 2 y 4 hablantes</option>
                    <option value="2-6">Entre 2 y 6 hablantes</option>
                  </select>
                </div>

                {sttProvider === "local_whisperx" && (
                  <div className="field">
                    <label htmlFor="whisperModelSelect">Modelo WhisperX local</label>
                    <select
                      id="whisperModelSelect"
                      value={whisperModel}
                      onChange={(e) => setWhisperModel(e.target.value)}
                    >
                      <option value="large-v3-turbo">large-v3-turbo (rápido y preciso)</option>
                      <option value="medium">medium (más ligero)</option>
                      <option value="large-v3">large-v3 (máxima precisión)</option>
                    </select>
                  </div>
                )}
              </div>

              <div className="toggles-row">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={diarize}
                    onChange={(e) => setDiarize(e.target.checked)}
                  />
                  <span>Identificar y separar hablantes (Hablante 1, Hablante 2…)</span>
                </label>

                {sttProvider === "local_whisperx" && (
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={denoise}
                      onChange={(e) => setDenoise(e.target.checked)}
                    />
                    <span>Reducir ruido de fondo y nivelar voces con FFmpeg</span>
                  </label>
                )}
              </div>

              <div className="actions-row">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!selectedAudioFile || isJobRunning}
                  onClick={handleStartAudioTranscription}
                >
                  Transcribir entrevista
                </button>
                <button
                  type="button"
                  className="btn-link"
                  onClick={() => setShowKeysPanel((v) => !v)}
                >
                  Configurar claves API / Supabase
                </button>
              </div>
            </div>
          ) : (
            <div>
              <div
                className="dropzone"
                tabIndex={0}
                role="button"
                onClick={() => transcriptInputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    transcriptInputRef.current?.click();
                  }
                }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (e.dataTransfer.files?.[0]) {
                    setSelectedTranscriptFile(e.dataTransfer.files[0]);
                  }
                }}
              >
                <input
                  ref={transcriptInputRef}
                  type="file"
                  hidden
                  accept=".json,.txt,application/json,text/plain"
                  onChange={(e) => {
                    if (e.target.files?.[0]) setSelectedTranscriptFile(e.target.files[0]);
                  }}
                />
                <p className="dropzone-title">
                  Arrastra tu transcripción (.json o .txt) o haz clic para seleccionarla
                </p>
                <p className="dropzone-hint">
                  Compatible con JSON de turnos o TXT con marcas de hablante exportados por esta aplicación
                </p>
              </div>

              {selectedTranscriptFile && (
                <div className="file-selected">
                  <div className="file-info">
                    <span className="file-name">{selectedTranscriptFile.name}</span>
                    <span className="file-size">{formatBytes(selectedTranscriptFile.size)}</span>
                  </div>
                  <button
                    type="button"
                    className="btn-link"
                    onClick={() => {
                      setSelectedTranscriptFile(null);
                      if (transcriptInputRef.current) transcriptInputRef.current.value = "";
                    }}
                  >
                    Cambiar archivo
                  </button>
                </div>
              )}

              <div className="actions-row">
                <div className="btn-group">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={!selectedTranscriptFile || isJobRunning}
                    onClick={handleUploadTranscript}
                  >
                    Cargar transcripción
                  </button>
                  {status?.example_available !== false && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={isJobRunning}
                      onClick={handleLoadExample}
                    >
                      Cargar ejemplo ENCOVI
                    </button>
                  )}
                </div>
                <button
                  type="button"
                  className="btn-link"
                  onClick={() => setShowCatalogModal(true)}
                >
                  Ver / editar reglas JEV
                </button>
              </div>
            </div>
          )}
        </section>

        {/* PROGRESS CARD */}
        {isJobRunning && (
          <section className="card progress-card" aria-live="polite">
            <div className="progress-top">
              <div>
                <h2 className="progress-title">{currentProgressStage}</h2>
                <p className="progress-meta">
                  {activeJob?.elapsed_seconds
                    ? `Tiempo transcurrido: ${formatDuration(activeJob.elapsed_seconds)}`
                    : "Iniciando proceso…"}
                  {activeJob?.duration_seconds
                    ? ` · Duración del audio: ${formatDuration(activeJob.duration_seconds)}`
                    : ""}
                </p>
              </div>
              <span className="progress-percent">{currentProgressPct} %</span>
            </div>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${currentProgressPct}%` }} />
            </div>
          </section>
        )}

        {/* ERROR CARD */}
        {errorMessage && (
          <section className="card error-card" role="alert">
            <h2>No se pudo completar la operación</h2>
            <p>{errorMessage}</p>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setErrorMessage(null)}
            >
              Cerrar aviso
            </button>
          </section>
        )}

        {/* TRANSCRIPT + ROLE MAPPER + JEV LAUNCHER */}
        {activeJob && activeJob.status === "completed" && activeJob.result && (
          <section className="card result-card">
            <div className="result-header">
              <div>
                <h2>Transcripción</h2>
                <p className="result-summary">
                  {[
                    activeJob.filename,
                    `${activeTurns.length} intervenciones`,
                    activeSpeakers.length
                      ? `${activeSpeakers.length} ${
                          activeSpeakers.length === 1 ? "hablante" : "hablantes"
                        }`
                      : "Sin separación de hablantes",
                    activeJob.duration_seconds
                      ? `Duración: ${formatDuration(activeJob.duration_seconds)}`
                      : null,
                    activeJob.stt_provider ? `Motor: ${activeJob.stt_provider}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>

              <div className="result-actions">
                <button type="button" className="btn btn-secondary" onClick={handleCopyTranscript}>
                  {copiedBanner ? "¡Copiado!" : "Copiar texto"}
                </button>
                <a
                  className="btn btn-secondary"
                  href={`/api/jobs/${encodeURIComponent(activeJob.job_id)}/download`}
                >
                  Descargar .txt
                </a>
              </div>
            </div>

            {activeJob.result.warning && (
              <div className="warning-banner">{activeJob.result.warning}</div>
            )}
            {activeJob.result.note && <div className="info-banner">{activeJob.result.note}</div>}

            {activeJob.has_audio && activeJob.audio_url && (
              <div className="audio-bar">
                <audio ref={audioPlayerRef} src={activeJob.audio_url} controls preload="metadata" />
                <span className="audio-hint">
                  Haz clic en cualquier marca de tiempo (en la transcripción o en las reglas JEV) para reproducir ese momento exacto.
                </span>
              </div>
            )}

            {/* JEV LAUNCHER */}
            <div className="jev-launcher">
              <div className="jev-launcher-head">
                <div>
                  <h3>Evaluar entrevista con JEV (ENCOVI A1–A2)</h3>
                  <p className="jev-launcher-sub">
                    Confirma quién es el <strong>ENCUESTADOR</strong> y quién es el{" "}
                    <strong>INFORMANTE</strong>, luego ejecuta la auditoría automática (incluye cualquier regla que hayas reescrito).
                  </p>
                </div>
              </div>

              <div className="role-mapper-grid">
                {activeSpeakers.map((spk) => (
                  <div key={spk} className="role-item">
                    <span className={`speaker-chip ${getSpeakerClass(spk, activeSpeakers)}`}>
                      {spk}
                    </span>
                    <select
                      aria-label={`Rol de ${spk}`}
                      value={speakerRoleMap[spk] || "OTRA_PERSONA"}
                      onChange={(e) =>
                        setSpeakerRoleMap((prev) => ({
                          ...prev,
                          [spk]: e.target.value as SpeakerRole,
                        }))
                      }
                    >
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>

              <div className="jev-options-row">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={firstContact}
                    onChange={(e) => setFirstContact(e.target.checked)}
                  />
                  <span>Primera visita / contacto inicial (evaluar reglas de apertura A1)</span>
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={mockMode}
                    onChange={(e) => setMockMode(e.target.checked)}
                  />
                  <span>Modo prueba sin conexión (puntajes simulados, sin consumir OpenRouter)</span>
                </label>
              </div>

              <div className="jev-launcher-actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={isEvaluating || activeTurns.length === 0}
                  onClick={() => runEvaluation(activeJob.job_id, speakerRoleMap)}
                >
                  {isEvaluating
                    ? "Evaluando entrevista…"
                    : evaluation
                    ? "Re-evaluar con JEV"
                    : "Evaluar con JEV"}
                </button>
                {isEvaluating && (
                  <span className="jev-running-hint">
                    {mockMode
                      ? "Ejecutando evaluación simulada…"
                      : "Consultando modelo JEV en OpenRouter…"}
                  </span>
                )}
              </div>

              {jevInlineError && <div className="jev-error-inline">{jevInlineError}</div>}
            </div>

            {/* SPEAKER LEGEND */}
            <div className="speaker-legend">
              {activeSpeakers.map((spk) => (
                <span key={spk} className={`speaker-chip ${getSpeakerClass(spk, activeSpeakers)}`}>
                  {spk} → {speakerRoleMap[spk] || "OTRA_PERSONA"}
                </span>
              ))}
            </div>

            {/* TRANSCRIPT TURNS */}
            <div ref={transcriptListRef} className="transcript-list">
              {activeTurns.map((turn, idx) => {
                const spkCls = getSpeakerClass(turn.speaker, activeSpeakers);
                const startStr = turn.start != null ? formatDuration(turn.start) : "";
                const endStr = turn.end != null ? formatDuration(turn.end) : "";
                const role = speakerRoleMap[turn.speaker];
                return (
                  <article
                    key={idx}
                    data-turn-idx={idx}
                    className={`turn ${spkCls} ${highlightedTurnIdx === idx ? "turn-highlight" : ""}`}
                  >
                    <div className="turn-header">
                      <span className={`turn-speaker ${spkCls}`}>{turn.speaker}</span>
                      {role && role.toUpperCase() !== turn.speaker.toUpperCase() && (
                        <span className="turn-role-tag">{role}</span>
                      )}
                      {turn.start != null && (
                        <button
                          type="button"
                          className="turn-time"
                          onClick={() => jumpToMoment(turn.start)}
                        >
                          {endStr && endStr !== startStr ? `${startStr} – ${endStr}` : startStr}
                        </button>
                      )}
                      {turn.has_overlap && (
                        <span className="overlap-badge">Voces superpuestas</span>
                      )}
                    </div>
                    <p className="turn-text">{turn.text}</p>
                  </article>
                );
              })}
            </div>
          </section>
        )}

        {/* JEV REPORT CARD WITH EDITABLE EVALUATIONS */}
        {activeJob && evaluation && overall && (
          <section ref={reportCardRef} className="card jev-report-card">
            <div className="result-header">
              <div>
                <div className="report-title-row">
                  <h2>Reporte de Auditoría JEV</h2>
                  <span className={`pill pill-${overall.verdict.level}`}>
                    {overall.verdict.label}
                  </span>
                  {(overall.manual_edit_count || 0) > 0 && (
                    <span className="pill pill-blue">
                      {overall.manual_edit_count}{" "}
                      {overall.manual_edit_count === 1
                        ? "evaluación corregida"
                        : "evaluaciones corregidas"}
                    </span>
                  )}
                </div>
                <p className="result-summary">
                  Modelo: {evaluation.model || "typesafe/jev-1.14"} · {evaluation.windows.length}{" "}
                  {evaluation.windows.length === 1 ? "ventana" : "ventanas"} ·{" "}
                  {evaluation.usage.requests} consultas
                  {evaluation.usage.cache_hits ? ` (${evaluation.usage.cache_hits} en caché)` : ""} ·{" "}
                  {evaluation.usage.input_tokens.toLocaleString("es-GT")} tokens · $
                  {evaluation.usage.cost_usd.toFixed(4)} USD
                  {activeJob.eval_elapsed_seconds
                    ? ` · ${activeJob.eval_elapsed_seconds.toFixed(1)} s`
                    : ""}
                </p>
              </div>

              <div className="result-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowCatalogModal(true)}
                >
                  Catálogo global de reglas
                </button>
                <a
                  className="btn btn-primary"
                  href={`/api/jobs/${encodeURIComponent(activeJob.job_id)}/evaluation/download`}
                >
                  Descargar reporte .json
                </a>
              </div>
            </div>

            {evaluation.warning && <div className="warning-banner">{evaluation.warning}</div>}

            {/* GLOBAL KPI STRIP */}
            <div className="kpi-strip">
              <div className="kpi-box">
                <div className="kpi-label">Cumplimiento global</div>
                <div
                  className={`kpi-value ${getRateColorClass(
                    overall.compliance_rate_weighted ?? overall.compliance_rate
                  )}`}
                >
                  {formatPct(overall.compliance_rate_weighted ?? overall.compliance_rate)}
                </div>
                <div className="kpi-sub">
                  Simple: {formatPct(overall.compliance_rate)} · Cobertura:{" "}
                  {formatPct(overall.coverage)}
                </div>
              </div>

              <div className="kpi-box">
                <div className="kpi-label">Conducta: marcadas / hora</div>
                <div
                  className={`kpi-value ${
                    (overall.conduct_flagged_per_hour ?? 0) >= 2.5
                      ? "rate-danger"
                      : (overall.conduct_flagged_per_hour ?? 0) >= 0.5
                      ? "rate-warn"
                      : "rate-ok"
                  }`}
                >
                  {(overall.conduct_flagged_per_hour ?? 0).toFixed(2)} / h
                </div>
                <div className="kpi-sub">
                  {overall.conduct_flagged_windows ?? 0}{" "}
                  {(overall.conduct_flagged_windows ?? 0) === 1
                    ? "ventana marcada"
                    : "ventanas marcadas"}{" "}
                  (≥ 70 %)
                </div>
              </div>

              <div className="kpi-box">
                <div className="kpi-label">Riesgos altos (≥ 70 %)</div>
                <div
                  className={`kpi-value ${
                    overall.high_risk_count > 0 ? "rate-danger" : "rate-ok"
                  }`}
                >
                  {overall.high_risk_count}
                </div>
                <div className="kpi-sub">En revisión (30–69 %): {overall.review_count}</div>
              </div>

              <div className="kpi-box">
                <div className="kpi-label">Compuertas / Calibración</div>
                <div className="kpi-value">
                  {evaluation.gates.opening != null ? formatPct(evaluation.gates.opening) : "Omit."}{" "}
                  / {evaluation.gates.closing != null ? formatPct(evaluation.gates.closing) : "n/a"}
                </div>
                <div className="kpi-sub">
                  {evaluation.calibration?.is_calibrated
                    ? `Calibrado (${evaluation.calibration.fitted_groups.length} grupos)`
                    : `Sin calibrar (${calibrationStatus?.total_labels ?? 0} etiquetas)`}
                </div>
              </div>
            </div>

            {/* A1 & A2 SECTION CARDS */}
            <div className="sections-grid">
              {Object.entries(evaluation.sections).map(([sid, sec]) => {
                const rate = sec.compliance_rate_weighted ?? sec.compliance_rate;
                const rateCls = getRateColorClass(rate);
                const pctWidth = rate != null ? Math.round(rate * 100) : 0;
                return (
                  <div key={sid} className="section-card">
                    <div className="section-card-head">
                      <div>
                        <h3>
                          {sid} · {sec.title}
                        </h3>
                        <span className="block-hint">{sec.n_instructions} instrucciones</span>
                      </div>
                      <span className={`section-big-rate ${rateCls}`}>{formatPct(rate)}</span>
                    </div>
                    <div className="section-bar">
                      <div
                        className={`section-bar-fill ${rateCls}`}
                        style={{ width: `${pctWidth}%` }}
                      />
                    </div>
                    <div className="section-metrics">
                      <div className="metric-row">
                        <span>Cumplimiento simple</span>
                        <strong>{formatPct(sec.compliance_rate)}</strong>
                      </div>
                      <div className="metric-row">
                        <span>Conducta: marcadas / hora</span>
                        <strong>
                          {(sec.conduct_flagged_per_hour ?? 0).toFixed(2)} / h (
                          {sec.conduct_flagged_windows ?? 0} vent.)
                        </strong>
                      </div>
                      <div className="metric-row">
                        <span>Incumplimientos esperados</span>
                        <strong>
                          {sec.expected_broken != null ? sec.expected_broken.toFixed(1) : "—"}
                        </strong>
                      </div>
                      <div className="metric-row">
                        <span>Cobertura evaluable</span>
                        <strong>{formatPct(sec.coverage)}</strong>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* TOP RISKS */}
            <div className="report-block">
              <div className="report-block-head">
                <h3>Principales riesgos detectados</h3>
                <span className="block-hint">
                  Haz clic en «Editar evaluación» si no estás de acuerdo con un dictamen para corregirlo aquí y para próximas transcripciones
                </span>
              </div>
              <div className="risks-list">
                {overall.top_risks.length === 0 ? (
                  <div className="no-risks-box">
                    No se detectaron incumplimientos probables (probabilidad ≥ 30 %).
                  </div>
                ) : (
                  overall.top_risks.map((risk) => {
                    const isHigh = risk.p_broken >= 0.7;
                    const rangeStr = formatTimeRange(risk.time);
                    return (
                      <div
                        key={risk.id}
                        className={`risk-item ${isHigh ? "" : "risk-review"}`}
                      >
                        <div className="risk-top">
                          <span className="rule-id-badge">{risk.id}</span>
                          <span className={`pill ${isHigh ? "pill-danger" : "pill-warn"}`}>
                            {formatPct(risk.p_broken)} incumplimiento
                          </span>
                          {risk.manual_override && (
                            <span className="pill pill-blue">Corregida manualmente</span>
                          )}
                          {risk.is_rule_customized && (
                            <span className="pill pill-muted">Criterio reescrito</span>
                          )}
                          {rangeStr && (
                            <button
                              type="button"
                              className="turn-time"
                              onClick={() => jumpToMoment(risk.time?.[0])}
                            >
                              {risk.worst_window != null ? `Ventana ${risk.worst_window + 1} · ` : ""}
                              {rangeStr}
                            </button>
                          )}
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm risk-edit-btn"
                            onClick={() => openRuleEditorFromEvaluation(risk.id)}
                          >
                            ✎ Editar evaluación
                          </button>
                        </div>
                        <p className="risk-text">{risk.text}</p>
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* ALL EVALUATIONS TABLE (OPEN BY DEFAULT SO USER SEES & CAN EDIT EVERY EVALUATION) */}
            <details className="rules-details" open>
              <summary className="rules-summary">
                <span>
                  Todas las evaluaciones ({evaluation.instructions.length} reglas A1 y A2) — edita cualquiera para corregir o reescribir el criterio
                </span>
                <span className="rules-count-pill">
                  {filteredInstructions.length} de {evaluation.instructions.length}
                </span>
              </summary>

              <div className="rules-controls">
                <div className="filter-pills">
                  {[
                    { id: "all", label: "Todas" },
                    { id: "broken", label: "Incumplimiento (≥ 70 %)" },
                    { id: "review", label: "Revisar (30–69 %)" },
                    { id: "followed", label: "Cumplidas" },
                    { id: "unknown", label: "No aplica / Sin evidencia" },
                    { id: "edited", label: "✎ Editadas / Reescritas" },
                  ].map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      className={`filter-pill ${ruleStatusFilter === f.id ? "active" : ""}`}
                      onClick={() => setRuleStatusFilter(f.id)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>

                <div className="rules-secondary-filters">
                  <select
                    aria-label="Filtrar por sección"
                    value={ruleSectionFilter}
                    onChange={(e) => setRuleSectionFilter(e.target.value)}
                  >
                    <option value="ALL">Sección: Todas (A1 y A2)</option>
                    <option value="A1">Solo A1 — Apertura</option>
                    <option value="A2">Solo A2 — Conducta y actitud</option>
                  </select>
                  <input
                    type="search"
                    placeholder="Buscar evaluación por ID, texto o nota del auditor…"
                    value={ruleSearch}
                    onChange={(e) => setRuleSearch(e.target.value)}
                  />
                </div>
              </div>

              <div className="rules-table-wrap">
                <table className="rules-table">
                  <thead>
                    <tr>
                      <th>Evaluación / Regla</th>
                      <th>Tipo / Peso</th>
                      <th>Resultado (Cumplida / Incumplida / N.A.)</th>
                      <th>Momento</th>
                      <th>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredInstructions.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="subtitle">
                          No hay evaluaciones que coincidan con este filtro.
                        </td>
                      </tr>
                    ) : (
                      filteredInstructions.map((ins) => {
                        const c = Number(ins.p_followed || 0);
                        const v = Number(ins.p_broken || 0);
                        const u = Number(ins.p_unknown || 0);
                        const ww = ins.worst_window;
                        const rangeStr = ww ? formatTimeRange(ww.time) : null;
                        return (
                          <tr key={ins.id} className={ins.manual_override ? "row-edited" : ""}>
                            <td>
                              <div className="rule-cell-top">
                                <span className="rule-id-badge">{ins.id}</span>
                                {ins.manual_override && (
                                  <span className="pill pill-blue">Corregida aquí</span>
                                )}
                                {ins.is_rule_customized && (
                                  <span className="pill pill-muted">Criterio reescrito</span>
                                )}
                              </div>
                              <div style={{ marginTop: 4 }}>{ins.text}</div>
                              <div className="rule-meta-line">
                                {[
                                  ins.pages ? `Manual ${ins.pages}` : null,
                                  ins.verifiability ? `Audibilidad: ${ins.verifiability}` : null,
                                  ins.note || null,
                                ]
                                  .filter(Boolean)
                                  .join(" · ")}
                              </div>
                              {ins.manual_override?.comment && (
                                <div className="auditor-note-inline">
                                  <strong>Auditor:</strong> {ins.manual_override.comment}
                                </div>
                              )}
                              {ins.auditor_guidance && (
                                <div className="auditor-note-inline">
                                  <strong>Criterio próximas entrevistas:</strong>{" "}
                                  {ins.auditor_guidance}
                                </div>
                              )}
                            </td>

                            <td>
                              <div>{KIND_LABELS[ins.kind] || ins.kind}</div>
                              <div className="rule-meta-line">
                                Peso: {WEIGHT_LABELS[ins.weight] || ins.weight}
                              </div>
                            </td>

                            <td>
                              <div
                                className="prob-bar"
                                title={`Cumplida ${formatPct(c)} · Incumplida ${formatPct(
                                  v
                                )} · No aplica ${formatPct(u)}`}
                              >
                                <div className="prob-c" style={{ width: `${(c * 100).toFixed(1)}%` }} />
                                <div className="prob-v" style={{ width: `${(v * 100).toFixed(1)}%` }} />
                                <div className="prob-u" style={{ width: `${(u * 100).toFixed(1)}%` }} />
                              </div>
                              <div className="prob-nums">
                                <span className="p-ok">C: {formatPct(c)}</span>
                                <span className="p-bad">I: {formatPct(v)}</span>
                                <span className="p-na">N/A: {formatPct(u)}</span>
                              </div>
                              {ins.kind === "prohibition" && (ins.windows_flagged || 0) > 0 && (
                                <div className="rule-meta-line">
                                  <strong>{ins.windows_flagged}</strong>{" "}
                                  {ins.windows_flagged === 1 ? "ventana marcada" : "ventanas marcadas"}
                                  {ins.flagged_per_hour != null ? ` (${ins.flagged_per_hour.toFixed(2)} / h)` : ""}
                                </div>
                              )}
                              {ins.kind === "conditional" && ins.triggered_windows != null && (
                                <div className="rule-meta-line">
                                  {ins.triggered_windows > 0
                                    ? `Situación detectada en ${ins.triggered_windows} ${
                                        ins.triggered_windows === 1 ? "ventana" : "ventanas"
                                      }`
                                    : "Sin activación en esta entrevista"}
                                </div>
                              )}
                            </td>

                            <td>
                              {ww && rangeStr ? (
                                <button
                                  type="button"
                                  className="turn-time"
                                  onClick={() => jumpToMoment(ww.time?.[0])}
                                >
                                  {rangeStr}
                                </button>
                              ) : ww ? (
                                `Ventana ${ww.window + 1}`
                              ) : (
                                "—"
                              )}
                            </td>

                            <td>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => openRuleEditorFromEvaluation(ins.id)}
                              >
                                ✎ Editar
                              </button>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </details>
          </section>
        )}
      </main>

      {/* MODAL: EDIT INDIVIDUAL EVALUATION + FUTURE RULE */}
      <EvaluationRuleModal
        isOpen={Boolean(editingRuleId && activeEditingRuleSpec)}
        ruleSpec={activeEditingRuleSpec}
        evaluatedRule={activeEditingEvaluatedRule}
        onClose={() => setEditingRuleId(null)}
        onSaveInterviewAndRule={handleSaveInterviewAndRule}
        onSaveGlobalRuleOnly={handleSaveGlobalRuleOnly}
        onResetGlobalRule={handleResetGlobalRule}
      />

      {/* MODAL: GLOBAL 51-RULE CATALOG */}
      <RulesCatalogModal
        isOpen={showCatalogModal}
        rules={rulesCatalog}
        onClose={() => setShowCatalogModal(false)}
        onSelectRuleToEdit={openRuleEditorGlobal}
      />

      {/* MODAL: CALIBRATION STATUS */}
      <CalibrationModal
        isOpen={showCalibrationModal}
        calibration={calibrationStatus}
        onClose={() => setShowCalibrationModal(false)}
        onRefit={async () => {
          const updated = await fitCalibrationNow();
          setCalibrationStatus(updated);
          await refreshMetadata();
        }}
      />
    </div>
  );
};
