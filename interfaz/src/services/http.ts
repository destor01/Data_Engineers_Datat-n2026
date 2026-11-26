import { authHeaders } from './auth';

export function message(error: unknown): string {
  if (error instanceof DOMException && error.name === 'AbortError') return 'Se dejó de esperar el resultado. El servidor podría seguir procesando el archivo.';
  if (error instanceof TypeError) return 'No se pudo conectar al servicio. Comprueba que esté disponible y permita el acceso desde esta interfaz.';
  return error instanceof Error ? error.message : 'Ocurrió un error inesperado. Intenta nuevamente.';
}

/** Se avisa a la interfaz cuando la API rechaza la sesión, para volver a pedir el inicio de sesión. */
let onUnauthorized: (() => void) | undefined;
export function setUnauthorizedHandler(handler: () => void) { onUnauthorized = handler; }

function detail(data: unknown, status: number): string {
  if (record(data) && typeof data.detail === 'string') return data.detail;
  if (status === 413) return 'El archivo supera el límite de tamaño permitido.';
  return `El servicio respondió con un error (${status}).`;
}

/** Petición a la API con el token de la sesión y tiempo límite. Devuelve el JSON de la respuesta. */
export async function request(url: string, init: RequestInit = {}, timeout = 30_000): Promise<unknown> {
  const response = await send(url, init, timeout);
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(detail(data, response.status));
  if (data === null) throw new Error('El servicio no devolvió una respuesta JSON válida.');
  return data;
}

/** Igual que request, pero entrega la respuesta sin interpretar (para descargas). */
export async function send(url: string, init: RequestInit = {}, timeout = 30_000): Promise<Response> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (init.signal?.aborted) controller.abort();
  init.signal?.addEventListener('abort', abort, { once: true });
  let timedOut = false;
  const timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
  try {
    const headers = new Headers(init.headers);
    for (const [name, value] of Object.entries(await authHeaders())) headers.set(name, value);
    const response = await fetch(url, { ...init, headers, signal: controller.signal });
    if (response.status === 401) onUnauthorized?.();
    return response;
  } catch (error) {
    if (timedOut) throw new Error('El servicio tardó demasiado en responder. Puedes volver a intentarlo; el procesamiento podría continuar en el servidor.');
    throw error;
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener('abort', abort);
  }
}

/** Sube un archivo con PUT a una URL firmada de Supabase Storage (sin el token de la sesión). */
export function uploadSigned(url: string, file: File, signal: AbortSignal, progress?: (pct: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => { xhr.abort(); reject(new DOMException('Aborted', 'AbortError')); };
    if (signal.aborted) { abort(); return; }
    signal.addEventListener('abort', abort, { once: true });
    xhr.open('PUT', url, true);
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
    xhr.upload.onprogress = event => { if (event.lengthComputable) progress?.(Math.round((event.loaded / event.total) * 100)); };
    xhr.onload = () => {
      signal.removeEventListener('abort', abort);
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(xhr.status === 413 ? 'El archivo supera el límite de tamaño de Supabase Storage.' : `No se pudo subir el archivo (HTTP ${xhr.status}).`));
    };
    xhr.onerror = () => { signal.removeEventListener('abort', abort); reject(new Error('Error de red al subir el archivo.')); };
    xhr.send(file);
  });
}

export function record(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value); }
export function finite(value: unknown): value is number { return typeof value === 'number' && Number.isFinite(value); }
export function pause(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
    const timer = window.setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    if (signal.aborted) abort(); else signal.addEventListener('abort', abort, { once: true });
  });
}
