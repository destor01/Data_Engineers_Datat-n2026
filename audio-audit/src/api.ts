import type {
  AuditJob,
  CalibrationStatus,
  EvaluationRuleEditRequest,
  JobSummary,
  RuleCatalogItem,
  RuleOverrideInput,
  SpeakerRole,
  SttProvider,
  SystemStatus,
} from "./types";

async function parseJsonOrThrow<T>(res: Response, fallbackMsg: string): Promise<T> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // Non-JSON response (e.g., 413 from gateway)
    if (res.status === 413) {
      throw new Error(
        "El archivo supera el límite de carga directa del servidor (4.5 MB en Vercel). Configura Supabase Storage para subir grabaciones largas directamente."
      );
    }
    throw new Error(`${fallbackMsg} (HTTP ${res.status})`);
  }

  if (!res.ok) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `${fallbackMsg} (HTTP ${res.status})`;
    throw new Error(detail);
  }
  return body as T;
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const res = await fetch("/api/status");
  return parseJsonOrThrow<SystemStatus>(res, "No se pudo consultar el estado del servidor");
}

export async function saveApiKeys(payload: {
  hf_token?: string;
  openrouter_key?: string;
  assemblyai_key?: string;
  deepgram_key?: string;
  supabase_url?: string;
  supabase_key?: string;
}): Promise<{ ok: boolean; updated: string[]; note?: string | null }> {
  const res = await fetch("/api/config/keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow(res, "No se pudieron guardar las claves");
}

export async function listRecentJobs(limit = 20): Promise<JobSummary[]> {
  const res = await fetch(`/api/jobs?limit=${limit}`);
  const data = await parseJsonOrThrow<{ jobs: JobSummary[] }>(res, "Error cargando historial");
  return data.jobs;
}

export async function getJob(jobId: string): Promise<AuditJob> {
  const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
  return parseJsonOrThrow<AuditJob>(res, "No se pudo consultar el trabajo");
}

export async function uploadAudioDirectToSupabaseAndStart(params: {
  file: File;
  provider: SttProvider;
  diarize: boolean;
  minSpeakers: number | null;
  maxSpeakers: number | null;
  onUploadProgress?: (pct: number) => void;
}): Promise<{ job_id: string }> {
  // Step 1: Request signed upload URL from FastAPI
  const signRes = await fetch("/api/storage/upload-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: params.file.name,
      content_type: params.file.type || "audio/mpeg",
    }),
  });
  const signed = await parseJsonOrThrow<{
    job_id: string;
    filename: string;
    signed_upload_url: string;
    storage_path: string;
  }>(signRes, "No se pudo obtener URL firmada de Supabase Storage");

  // Step 2: Upload binary directly to Supabase Storage (no auth headers on signed URL PUT)
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", signed.signed_upload_url, true);
    xhr.setRequestHeader("Content-Type", params.file.type || "application/octet-stream");
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable && params.onUploadProgress) {
        params.onUploadProgress(Math.round((ev.loaded / ev.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(
          new Error(
            `Error subiendo audio a Supabase Storage (HTTP ${xhr.status}): ${xhr.responseText.slice(0, 200)}`
          )
        );
      }
    };
    xhr.onerror = () => reject(new Error("Error de red al subir el audio a Supabase Storage."));
    xhr.send(params.file);
  });

  // Step 3: Trigger cloud STT job using the Supabase Storage path
  const startRes = await fetch("/api/transcribe/cloud", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: signed.job_id,
      filename: params.file.name,
      storage_path: signed.storage_path,
      content_type: params.file.type || "audio/mpeg",
      provider: params.provider,
      diarize: params.diarize,
      min_speakers: params.minSpeakers,
      max_speakers: params.maxSpeakers,
    }),
  });
  const job = await parseJsonOrThrow<AuditJob>(startRes, "No se pudo iniciar la transcripción en la nube");
  return { job_id: job.job_id };
}

export async function uploadAudioMultipartAndStart(params: {
  file: File;
  provider: SttProvider;
  model: string;
  denoise: boolean;
  diarize: boolean;
  minSpeakers: number | null;
  maxSpeakers: number | null;
}): Promise<{ job_id: string }> {
  const formData = new FormData();
  formData.append("file", params.file);
  formData.append("provider", params.provider);
  formData.append("model", params.model);
  formData.append("denoise", String(params.denoise));
  formData.append("diarize", String(params.diarize));
  if (params.minSpeakers !== null) formData.append("min_speakers", String(params.minSpeakers));
  if (params.maxSpeakers !== null) formData.append("max_speakers", String(params.maxSpeakers));

  const res = await fetch("/api/transcribe", {
    method: "POST",
    body: formData,
  });
  return parseJsonOrThrow<{ job_id: string }>(res, "Error al iniciar la transcripción");
}

export async function uploadTranscriptFile(file: File): Promise<AuditJob> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/transcript/upload", {
    method: "POST",
    body: formData,
  });
  return parseJsonOrThrow<AuditJob>(res, "No se pudo cargar la transcripción");
}

export async function loadExampleTranscript(): Promise<AuditJob> {
  const res = await fetch("/api/transcript/example", { method: "POST" });
  return parseJsonOrThrow<AuditJob>(res, "No se pudo cargar el ejemplo ENCOVI");
}

export async function evaluateJobWithJev(
  jobId: string,
  payload: {
    speaker_map: Record<string, SpeakerRole>;
    first_contact: boolean;
    mock: boolean;
  }
): Promise<AuditJob> {
  const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<AuditJob>(res, "Error ejecutando la evaluación JEV");
}

export async function fetchRulesCatalog(): Promise<{
  rules: RuleCatalogItem[];
  customized_count: number;
}> {
  const res = await fetch("/api/rules");
  return parseJsonOrThrow(res, "No se pudo cargar el catálogo de reglas");
}

export async function saveGlobalRuleOverride(
  ruleId: string,
  payload: RuleOverrideInput
): Promise<{ rule: RuleCatalogItem; customized_count: number }> {
  const res = await fetch(`/api/rules/${encodeURIComponent(ruleId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow(res, "No se pudo guardar la regla personalizada");
}

export async function resetGlobalRuleOverride(
  ruleId: string
): Promise<{ rule: RuleCatalogItem; customized_count: number }> {
  const res = await fetch(`/api/rules/${encodeURIComponent(ruleId)}/override`, {
    method: "DELETE",
  });
  return parseJsonOrThrow(res, "No se pudo restaurar la regla original");
}

export async function editJobEvaluationRule(
  jobId: string,
  ruleId: string,
  payload: EvaluationRuleEditRequest
): Promise<{
  job: AuditJob;
  rule: RuleCatalogItem | null;
  customized_rules_count: number;
  calibration?: CalibrationStatus;
}> {
  const res = await fetch(
    `/api/jobs/${encodeURIComponent(jobId)}/evaluation/rules/${encodeURIComponent(ruleId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  return parseJsonOrThrow(res, "No se pudo guardar la edición de la evaluación");
}

export async function getCalibrationStatus(): Promise<CalibrationStatus> {
  const res = await fetch("/api/calibration");
  return parseJsonOrThrow<CalibrationStatus>(res, "No se pudo consultar la calibración JEV");
}

export async function fitCalibrationNow(): Promise<CalibrationStatus> {
  const res = await fetch("/api/calibration/fit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return parseJsonOrThrow<CalibrationStatus>(res, "No se pudo recalibrar el modelo JEV");
}
