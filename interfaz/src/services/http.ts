export function message(error: unknown): string {
  if (error instanceof DOMException && error.name === 'AbortError') return 'Se dejó de esperar el resultado. El servidor podría seguir procesando el archivo.';
  if (error instanceof TypeError) return 'No se pudo conectar al servicio. Comprueba que esté disponible y permita el acceso desde esta interfaz.';
  return error instanceof Error ? error.message : 'Ocurrió un error inesperado. Intenta nuevamente.';
}

export async function request(url: string, init: RequestInit = {}, timeout = 30_000): Promise<unknown> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (init.signal?.aborted) controller.abort();
  init.signal?.addEventListener('abort', abort, { once: true });
  let timedOut = false;
  const timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const data: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = record(data) && typeof data.detail === 'string' ? data.detail : `El servicio respondió con un error (${response.status}).`;
      throw new Error(detail);
    }
    if (data === null) throw new Error('El servicio no devolvió una respuesta JSON válida.');
    return data;
  } catch (error) {
    if (timedOut) throw new Error('El servicio tardó demasiado en responder. Puedes volver a intentarlo; el procesamiento podría continuar en el servidor.');
    throw error;
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener('abort', abort);
  }
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
