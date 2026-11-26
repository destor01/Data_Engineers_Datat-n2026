import type { AudioJob } from '../types';
import { apiUrl, demo } from './config';
import { finite, pause, record, request, send, uploadSigned } from './http';

export interface AudioRequest {
  file: File;
  model: string;
  denoise: boolean;
  diarize: boolean;
  minSpeakers: number | null;
  maxSpeakers: number | null;
}

/**
 * Con Supabase Storage configurado (despliegue): el audio se sube directo al bucket con una URL
 * firmada y la transcripción corre en la nube (AssemblyAI o Deepgram). Sin Supabase (desarrollo
 * local): se envía el archivo al servicio, que puede usar WhisperX con GPU.
 */
async function start(input: AudioRequest, signal: AbortSignal, stage: (text: string, pct: number) => void): Promise<string> {
  const sign = await send(apiUrl('/api/storage/upload-url'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
    body: JSON.stringify({ filename: input.file.name, content_type: input.file.type || 'audio/mpeg' })
  });
  const signed: unknown = await sign.json().catch(() => null);
  if (sign.ok) {
    if (!record(signed) || typeof signed.signed_upload_url !== 'string' || typeof signed.job_id !== 'string' || typeof signed.storage_path !== 'string') {
      throw new Error('El servicio no indicó dónde subir el audio.');
    }
    await uploadSigned(signed.signed_upload_url, input.file, signal, pct => stage(`Subiendo audio… ${pct}%`, Math.round(pct * 0.2)));
    stage('Iniciando la transcripción…', 22);
    const job = await request(apiUrl('/api/transcribe/cloud'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
      body: JSON.stringify({
        job_id: signed.job_id, filename: input.file.name, storage_path: signed.storage_path,
        content_type: input.file.type || 'audio/mpeg', provider: 'auto', diarize: input.diarize,
        min_speakers: input.minSpeakers, max_speakers: input.maxSpeakers
      })
    }, 300_000);
    if (!record(job) || typeof job.job_id !== 'string') throw new Error('El servicio no devolvió un identificador de transcripción.');
    return job.job_id;
  }
  if (sign.status !== 400) {
    throw new Error(record(signed) && typeof signed.detail === 'string' ? signed.detail : `El servicio respondió con un error (${sign.status}).`);
  }
  // 400: Supabase Storage no está configurado → envío directo (modo local).
  const form = new FormData();
  form.append('file', input.file);
  form.append('model', input.model);
  form.append('denoise', String(input.denoise));
  form.append('diarize', String(input.diarize));
  if (input.minSpeakers !== null) form.append('min_speakers', String(input.minSpeakers));
  if (input.maxSpeakers !== null) form.append('max_speakers', String(input.maxSpeakers));
  stage('Enviando audio al servicio…', 5);
  const created = await request(apiUrl('/api/transcribe'), { method: 'POST', body: form, signal }, 300_000);
  if (!record(created) || typeof created.job_id !== 'string' || !created.job_id) throw new Error('El servicio no devolvió un identificador de transcripción.');
  return created.job_id;
}

export async function transcribe(input: AudioRequest, signal: AbortSignal, progress: (job: AudioJob) => void): Promise<AudioJob> {
  if (demo) {
    for (const [value, stage] of [[15, 'Preparando ejemplo…'], [55, 'Mostrando transcripción de ejemplo…'], [100, 'Ejemplo disponible']] as const) {
      await pause(500, signal);
      progress({ job_id: 'demo', status: 'processing', progress: value, stage });
    }
    return { job_id: 'demo', status: 'completed', stage: 'Ejemplo disponible', progress: 100, result: {
      speakers: ['Hablante 1', 'Hablante 2'],
      warning: 'Texto de demostración. No corresponde al archivo seleccionado; los tiempos también son ilustrativos.',
      turns: [
        { speaker: 'Hablante 1', start: 0, end: 5, text: 'Buenos días. Gracias por participar en esta entrevista.' },
        { speaker: 'Hablante 2', start: 5, end: 9, text: 'Buenos días. Con gusto responderé sus preguntas.' },
        { speaker: 'Hablante 1', start: 9, end: 15, text: 'Para comenzar, ¿podría contarnos cómo ha sido su experiencia?' }
      ]
    } };
  }
  const jobId = await start(input, signal, (stage, value) => progress({ job_id: '', status: 'processing', progress: value, stage }));
  const deadline = Date.now() + 2 * 60 * 60 * 1000;
  while (Date.now() < deadline) {
    const value = await request(apiUrl(`/api/jobs/${encodeURIComponent(jobId)}`), { signal });
    if (!record(value) || !['queued', 'processing', 'completed', 'error'].includes(String(value.status)) || !finite(value.progress) || typeof value.stage !== 'string') throw new Error('El estado de transcripción tiene un formato incompatible.');
    const job = { ...value, job_id: jobId } as unknown as AudioJob;
    progress(job);
    if (job.status === 'error') throw new Error(typeof job.error === 'string' ? job.error : 'No se pudo procesar la entrevista.');
    if (job.status === 'completed') {
      if (!record(value.result) || !Array.isArray(value.result.turns) || !value.result.turns.every(t => record(t) && finite(t.start) && finite(t.end) && typeof t.text === 'string' && typeof t.speaker === 'string') || !Array.isArray(value.result.speakers) || !value.result.speakers.every(s => typeof s === 'string')) throw new Error('La transcripción recibida tiene un formato incompatible.');
      return job;
    }
    await pause(2500, signal);
  }
  throw new Error('Se alcanzó el límite de espera de dos horas. El servidor podría seguir procesando el audio.');
}
