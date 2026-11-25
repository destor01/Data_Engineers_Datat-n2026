export const demo = (import.meta.env.VITE_APP_MODE ?? 'demo') === 'demo';
if (!['demo', 'api'].includes(import.meta.env.VITE_APP_MODE ?? 'demo')) {
  throw new Error('VITE_APP_MODE debe ser demo o api.');
}

export function apiBase(module: 'audio' | 'data'): string {
  const value = module === 'audio' ? import.meta.env.VITE_AUDIO_API_URL : import.meta.env.VITE_DATA_API_URL;
  if (!value) throw new Error(`Falta configurar la dirección del servicio ${module}.`);
  let url: URL;
  try { url = new URL(value, window.location.origin); } catch { throw new Error(`La dirección del servicio ${module} no es válida.`); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error(`Usa una dirección HTTP o HTTPS sin credenciales ni parámetros para ${module}.`);
  }
  return url.href.replace(/\/$/, '');
}

export function apiUrl(module: 'audio' | 'data', path: string): string {
  return `${apiBase(module)}/${path.replace(/^\//, '')}`;
}

export function downloadUrl(path: string): string {
  const url = new URL(path, `${apiBase('data')}/`);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('El servicio devolvió una descarga no válida.');
  if (url.origin !== new URL(apiBase('data')).origin) throw new Error('La descarga debe pertenecer al servicio de datos.');
  return url.href;
}
