import type { AuditResult, Base } from '../types';
import { apiUrl, demo } from './config';
import { finite, pause, record, request } from './http';

export async function listBases(): Promise<Base[]> {
  if (demo) return [
    { codigo: 'DEFUNCIONES', nombre: 'Defunciones · RENAP' },
    { codigo: 'NACIMIENTOS', nombre: 'Nacimientos · RENAP' },
    { codigo: 'DETENIDOS', nombre: 'Detenidos · PNC' },
    { codigo: 'CALIDAD_AIRE', nombre: 'Calidad del aire · INSIVUMEH' },
    { codigo: 'EMERGENCIAS', nombre: 'Emergencias · SECONRED' }
  ];
  const data = await request(apiUrl('data', '/data-api/bases'));
  if (!Array.isArray(data) || !data.every(base => record(base) && typeof base.codigo === 'string' && typeof base.nombre === 'string')) {
    throw new Error('El catálogo de bases tiene un formato incompatible.');
  }
  return data as Base[];
}

export async function audit(form: FormData, signal: AbortSignal): Promise<AuditResult> {
  if (demo) {
    await pause(1200, signal);
    return { reporte: { base: String(form.get('base')), total_registros: 1250, registros_validos: 1198, registros_excluidos: 52, puntaje: 91.6,
      puntajes: { estructura: 100, completitud: 94.2, validez: 90.8, consistencia: 87.4, unicidad: 96, oportunidad: 81.2 },
      hallazgos: [
        { severidad: 'error', mensaje: 'Ejemplo: registros con campos obligatorios vacíos.', n: 32 },
        { severidad: 'advertencia', mensaje: 'Ejemplo: valores que requieren revisión de consistencia.', n: 20 },
        { severidad: 'info', mensaje: 'Ejemplo: se estandarizaron etiquetas de texto.', n: 84 }
      ] }, descargas: {} };
  }
  const data = await request(apiUrl('data', '/data-api/procesar'), { method: 'POST', body: form, signal }, 600_000);
  if (!record(data) || !record(data.reporte) || !record(data.descargas)) throw new Error('La auditoría devolvió un formato incompatible.');
  const r = data.reporte;
  if (![r.total_registros, r.registros_validos, r.registros_excluidos].every(n => finite(n) && n >= 0) ||
    !(r.puntaje === null || finite(r.puntaje)) || !record(r.puntajes) || !Object.values(r.puntajes).every(finite) ||
    !Array.isArray(r.hallazgos) || !r.hallazgos.every(h => record(h) && ['error', 'advertencia', 'info'].includes(String(h.severidad)) && typeof h.mensaje === 'string' && (h.n === undefined || finite(h.n))) ||
    !Object.values(data.descargas).every(value => typeof value === 'string')) throw new Error('El reporte recibido no cumple el contrato de datos esperado.');
  return data as unknown as AuditResult;
}
