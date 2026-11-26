export const demo = (import.meta.env.VITE_APP_MODE ?? 'demo') === 'demo';
if (!['demo', 'api'].includes(import.meta.env.VITE_APP_MODE ?? 'demo')) {
  throw new Error('VITE_APP_MODE debe ser demo o api.');
}

/**
 * La API unificada vive en el mismo dominio que la interfaz (/api/*). VITE_API_URL solo hace
 * falta si se sirve desde otro dominio.
 */
export function apiBase(): string {
  const value = import.meta.env.VITE_API_URL || window.location.origin;
  let url: URL;
  try { url = new URL(value, window.location.origin); } catch { throw new Error('La dirección de la API no es válida.'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('Usa una dirección HTTP o HTTPS sin credenciales ni parámetros para la API.');
  }
  return url.href.replace(/\/$/, '');
}

export function apiUrl(path: string): string {
  return `${apiBase()}/${path.replace(/^\//, '')}`;
}
