import { apiUrl } from './config';
import { send } from './http';

/** API de Survey Audit y Quality Improvement, en la misma API unificada (/api/...). */
export async function extensionRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await send(apiUrl(`/api/${path}`), {
    method,
    headers: body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body)
  }, 120_000);
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail));
  return result as T;
}

/** Descarga un archivo de la API con la sesión activa (un enlace normal no enviaría el token). */
export async function extensionDownload(path: string, fallbackName: string): Promise<void> {
  const response = await send(apiUrl(`/api/${path}`), {}, 120_000);
  if (!response.ok) {
    const result: unknown = await response.json().catch(() => null);
    throw new Error(typeof result === 'object' && result !== null && 'detail' in result && typeof result.detail === 'string' ? result.detail : 'No se pudo descargar el archivo.');
  }
  const name = /filename="?([^";]+)"?/.exec(response.headers.get('content-disposition') ?? '')?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
