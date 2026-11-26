import type { AuditResult, Base } from '../types';
import { apiUrl, demo } from './config';
import { finite, pause, record, request, send, uploadSigned } from './http';

export async function listBases(): Promise<Base[]> {
  if (demo) return [
    { codigo: 'DEFUNCIONES', nombre: 'Defunciones · RENAP' },
    { codigo: 'NACIMIENTOS', nombre: 'Nacimientos · RENAP' },
    { codigo: 'DETENIDOS', nombre: 'Detenidos · PNC' },
    { codigo: 'CALIDAD_AIRE', nombre: 'Calidad del aire · INSIVUMEH' },
    { codigo: 'EMERGENCIAS', nombre: 'Emergencias · SECONRED' }
  ];
  const data = await request(apiUrl('/api/qa/bases'));
  if (!Array.isArray(data) || !data.every(base => record(base) && typeof base.codigo === 'string' && typeof base.nombre === 'string')) {
    throw new Error('El catálogo de bases tiene un formato incompatible.');
  }
  // Solo las bases con una versión de esquema activa se pueden auditar.
  return (data as (Base & { version?: unknown; institucion?: unknown })[])
    .filter(base => base.version !== null)
    .map(base => ({ codigo: base.codigo, nombre: typeof base.institucion === 'string' ? `${base.nombre} · ${base.institucion}` : base.nombre }));
}

export interface AuditRequest { file: File; base: string; anio: number; mes: number }

/**
 * Tres pasos: la API registra la carga y entrega dónde subir el archivo; el navegador lo sube
 * (directo a Supabase Storage en el despliegue); la API valida la base y devuelve el reporte.
 */
export async function audit(input: AuditRequest, signal: AbortSignal, stage: (text: string) => void): Promise<AuditResult> {
  if (demo) {
    await pause(1200, signal);
    return { reporte: { base: input.base, total_registros: 1250, registros_validos: 1198, registros_excluidos: 52, puntaje: 91.6,
      puntajes: { estructura: 100, completitud: 94.2, validez: 90.8, consistencia: 87.4, unicidad: 96, oportunidad: 81.2 },
      hallazgos: [
        { severidad: 'error', mensaje: 'Ejemplo: registros con campos obligatorios vacíos.', n: 32 },
        { severidad: 'advertencia', mensaje: 'Ejemplo: valores que requieren revisión de consistencia.', n: 20 },
        { severidad: 'info', mensaje: 'Ejemplo: se estandarizaron etiquetas de texto.', n: 84 }
      ] }, descargas: {} };
  }
  stage('Registrando la carga…');
  const created = await request(apiUrl('/api/qa/cargas/subida'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
    body: JSON.stringify({ base: input.base, anio: input.anio, mes: input.mes, archivo: input.file.name, tamano: input.file.size })
  });
  if (!record(created) || typeof created.carga_id !== 'string' || !record(created.subida) || typeof created.subida.url !== 'string') {
    throw new Error('El servicio no indicó dónde subir el archivo.');
  }
  const id = created.carga_id;
  if (created.subida.directa === true) {
    await uploadSigned(created.subida.url, input.file, signal, pct => stage(`Subiendo el archivo… ${pct}%`));
  } else {
    stage('Subiendo el archivo…');
    await request(apiUrl(created.subida.url), { method: 'PUT', body: input.file, signal }, 600_000);
  }
  stage('Auditando la base. El tiempo depende del tamaño del archivo…');
  const data = await request(apiUrl(`/api/qa/cargas/${encodeURIComponent(id)}/procesar`), { method: 'POST', signal }, 600_000);
  if (!record(data) || !record(data.reporte) || !record(data.descargas)) throw new Error('La auditoría devolvió un formato incompatible.');
  const r = data.reporte;
  if (![r.total_registros, r.registros_validos, r.registros_excluidos].every(n => finite(n) && n >= 0) ||
    !(r.puntaje === null || finite(r.puntaje)) || !record(r.puntajes) || !Object.values(r.puntajes).every(v => v === null || finite(v)) ||
    !Array.isArray(r.hallazgos) || !r.hallazgos.every(h => record(h) && ['error', 'advertencia', 'info'].includes(String(h.severidad)) && typeof h.mensaje === 'string' && (h.n === undefined || finite(h.n))) ||
    !Object.values(data.descargas).every(value => typeof value === 'string')) throw new Error('El reporte recibido no cumple el contrato de datos esperado.');
  const puntajes = Object.fromEntries(Object.entries(r.puntajes as Record<string, number | null>).filter((entry): entry is [string, number] => entry[1] !== null));
  return { reporte: { ...(r as unknown as AuditResult['reporte']), puntajes }, descargas: data.descargas as Record<string, string> };
}

/** Descarga un resultado: la API entrega el archivo o una URL firmada de Supabase Storage. */
export async function download(path: string): Promise<void> {
  if (!path.startsWith('/api/qa/')) throw new Error('El enlace de descarga no es válido.');
  const response = await send(apiUrl(path), {}, 120_000);
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    throw new Error(record(data) && typeof data.detail === 'string' ? data.detail : 'No se pudo descargar el archivo.');
  }
  const disposition = response.headers.get('content-disposition') ?? '';
  if (!disposition && (response.headers.get('content-type') ?? '').includes('application/json')) {
    const data: unknown = await response.json();
    if (record(data) && typeof data.url === 'string') {
      const target = new URL(data.url);
      if (target.protocol !== 'https:' && target.hostname !== '127.0.0.1' && target.hostname !== 'localhost') throw new Error('El servicio devolvió una descarga no válida.');
      window.location.assign(target.href);
      return;
    }
    throw new Error('El servicio no devolvió el archivo.');
  }
  const name = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? 'resultado';
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
