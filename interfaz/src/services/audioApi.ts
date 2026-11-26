import type { AudioJob } from '../types';
import { apiUrl, demo } from './config';
import { finite, pause, record, request } from './http';

export async function transcribe(form: FormData, signal: AbortSignal, progress: (job: AudioJob) => void): Promise<AudioJob> {
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
  const created = await request(apiUrl('audio', '/api/transcribe'), { method: 'POST', body: form, signal }, 300_000);
  if (!record(created) || typeof created.job_id !== 'string' || !created.job_id) throw new Error('El servicio no devolvió un identificador de transcripción.');
  const deadline = Date.now() + 2 * 60 * 60 * 1000;
  while (Date.now() < deadline) {
    const value = await request(apiUrl('audio', `/api/jobs/${encodeURIComponent(created.job_id)}`), { signal });
    if (!record(value) || !['queued', 'processing', 'completed', 'error'].includes(String(value.status)) || !finite(value.progress) || typeof value.stage !== 'string') throw new Error('El estado de transcripción tiene un formato incompatible.');
    const job = { ...value, job_id: created.job_id } as unknown as AudioJob;
    progress(job);
    if (job.status === 'error') throw new Error(typeof job.error === 'string' ? job.error : 'No se pudo procesar la entrevista.');
    if (job.status === 'completed') {
      if (!record(value.result) || !Array.isArray(value.result.turns) || !value.result.turns.every(t => record(t) && finite(t.start) && finite(t.end) && typeof t.text === 'string' && typeof t.speaker === 'string') || !Array.isArray(value.result.speakers) || !value.result.speakers.every(s => typeof s === 'string')) throw new Error('La transcripción recibida tiene un formato incompatible.');
      return job;
    }
    await pause(1500, signal);
  }
  throw new Error('Se alcanzó el límite de espera de dos horas. El servidor podría seguir procesando el audio.');
}
