/** Misma procedencia que la interfaz: Vite reenvía /api al backend integrado. */
export async function extensionRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 120_000);
  try {
    const response = await fetch(`/api/${path}`, { method, signal: controller.signal,
      headers: body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body) });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail));
    return result as T;
  } finally { clearTimeout(timer); }
}
