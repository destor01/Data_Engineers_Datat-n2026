/** Piezas de interfaz compartidas por Survey Audit y Quality Improvement. */
import { apiUrl } from './services/config';
import { send } from './services/http';

type Attrs = Record<string, string | number | boolean | undefined>;
type Child = Node | string | null | undefined | false;

export function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, ...children: Child[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === false) continue;
    if (key === 'class') el.className = String(value);
    else if (key === 'text') el.textContent = String(value);
    else if (value === true) el.setAttribute(key, '');
    else el.setAttribute(key, String(value));
  }
  for (const child of children) if (child) el.append(child);
  return el;
}

/** Igual que append/replaceChildren, pero ignora null y false. */
export function add(parent: Element, ...children: Child[]): void { parent.append(...children.filter((c): c is Node | string => Boolean(c))); }
export function fill(parent: Element, ...children: Child[]): void { parent.replaceChildren(...children.filter((c): c is Node | string => Boolean(c))); }

export function button(text: string, onClick: () => unknown, kind: 'primary' | 'secondary' | 'link' | 'danger' = 'secondary'): HTMLButtonElement {
  const b = h('button', { type: 'button', class: kind === 'link' ? 'text-button' : `button ${kind}` , text });
  b.addEventListener('click', () => { void onClick(); });
  return b;
}

/** Campo con etiqueta y ayuda opcional. */
export function field(label: string, control: HTMLElement, help?: string): HTMLDivElement {
  const id = control.id || `c${Math.random().toString(36).slice(2, 9)}`;
  control.id = id;
  return h('div', { class: 'campo' }, h('label', { for: id, text: label }), control, help ? h('p', { class: 'ayuda', text: help }) : null);
}

export function input(type = 'text', value = '', attrs: Attrs = {}): HTMLInputElement {
  const el = h('input', { type, ...attrs });
  el.value = value;
  return el;
}

export function textarea(value = '', rows = 3, attrs: Attrs = {}): HTMLTextAreaElement {
  const el = h('textarea', { rows, ...attrs });
  el.value = value;
  return el;
}

export function select(options: [string, string][], value = ''): HTMLSelectElement {
  const el = h('select');
  for (const [v, l] of options) el.add(new Option(l, v, false, v === value));
  return el;
}

export function chip(text: string, tone: 'ok' | 'warn' | 'bad' | 'info' | 'neutral' = 'neutral'): HTMLSpanElement {
  return h('span', { class: `chip ${tone}`, text });
}

export function card(title?: string, ...children: Child[]): HTMLElement {
  return h('section', { class: 'card' }, title ? h('h2', { text: title }) : null, ...children);
}

/** Mensaje de estado accesible (éxito o error). */
export function notice(): HTMLParagraphElement & { show: (text: string, error?: boolean) => void } {
  const el = h('p', { class: 'aviso', role: 'status', 'aria-live': 'polite' }) as HTMLParagraphElement & { show: (text: string, error?: boolean) => void };
  el.hidden = true;
  el.show = (text: string, error = false) => {
    el.textContent = text; el.hidden = !text; el.classList.toggle('error', error); el.classList.toggle('ok', !error && Boolean(text));
  };
  return el;
}

/** Error de la API con su mensaje en lenguaje claro y datos extra (p. ej. lista de errores). */
export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly data: Record<string, unknown>) { super(message); }
}

export async function api<T>(path: string, method = 'GET', body?: unknown, timeout = 120_000): Promise<T> {
  const isForm = body instanceof FormData || body instanceof Blob;
  let response: Response;
  try {
    response = await send(apiUrl(`/api/${path.replace(/^\//, '')}`), {
      method,
      headers: body === undefined || isForm ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : isForm ? body as BodyInit : JSON.stringify(body)
    }, timeout);
  } catch (error) {
    if (error instanceof Error && error.name !== 'TypeError') throw error;
    throw new ApiError('No se pudo conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.', 0, {});
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const record = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>;
    const detail = record.detail;
    const message = typeof detail === 'string' ? detail
      : response.status === 401 ? 'Tu sesión terminó. Vuelve a iniciar sesión.'
      : response.status === 413 ? 'El archivo es demasiado grande.'
      : response.status >= 500 ? 'El servidor tuvo un problema. Inténtalo de nuevo en unos minutos.'
      : 'No se pudo completar la acción. Revisa los datos e inténtalo de nuevo.';
    throw new ApiError(message, response.status, record);
  }
  return data as T;
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof DOMException && error.name === 'AbortError') return 'Se detuvo el proceso.';
  if (error instanceof Error && error.message) return error.message;
  return 'Ocurrió un problema inesperado. Inténtalo de nuevo.';
}

/** Ejecuta una acción desactivando el botón y mostrando el resultado en `msg`. */
export async function run(btn: HTMLButtonElement | null, msg: { show: (t: string, e?: boolean) => void }, action: () => Promise<string | void>): Promise<void> {
  if (btn) btn.disabled = true;
  try { const ok = await action(); if (ok) msg.show(ok); }
  catch (error) { msg.show(errorText(error), true); }
  finally { if (btn) btn.disabled = false; }
}

export function confirmar(texto: string): boolean { return window.confirm(texto); }

export function pause(ms: number): Promise<void> { return new Promise(resolve => window.setTimeout(resolve, ms)); }

export function fecha(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('es-GT', { dateStyle: 'medium', timeStyle: 'short' });
}

export function minutos(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos));
  return `${Math.floor(s / 60).toString().padStart(2, '0')}:${(s % 60).toString().padStart(2, '0')}`;
}

/** Descarga o muestra un archivo de la API con la sesión activa. */
export async function fetchBlob(path: string): Promise<{ blob: Blob; name: string }> {
  const response = await send(apiUrl(`/api/${path.replace(/^\//, '')}`), {}, 120_000);
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    const detail = data && typeof data === 'object' && 'detail' in data ? String((data as { detail: unknown }).detail) : 'No se pudo obtener el archivo.';
    throw new ApiError(detail, response.status, {});
  }
  const name = /filename="?([^";]+)"?/.exec(response.headers.get('content-disposition') ?? '')?.[1] ?? 'archivo';
  return { blob: await response.blob(), name };
}

export function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const link = h('a', { href: url, download: name });
  document.body.append(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** Sube un archivo con PUT: URL firmada de Supabase (sin sesión) o la API local (con sesión). */
export function uploadFile(url: string, file: File, direct: boolean, progress?: (pct: number) => void): Promise<void> {
  if (!direct) return api(url.replace(/^\/api\//, ''), 'PUT', file, 600_000).then(() => undefined);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url, true);
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
    xhr.upload.onprogress = e => { if (e.lengthComputable) progress?.(Math.round(e.loaded / e.total * 100)); };
    xhr.onload = () => xhr.status < 300 ? resolve() : reject(new Error(xhr.status === 413 ? 'El archivo supera el tamaño permitido por el almacenamiento.' : 'No se pudo subir el archivo. Inténtalo de nuevo.'));
    xhr.onerror = () => reject(new Error('Se perdió la conexión al subir el archivo.'));
    xhr.send(file);
  });
}

/** Pestañas simples dentro de una página. */
export function tabs(items: [string, string][], onChange: (key: string) => void, active: string): HTMLElement {
  const bar = h('div', { class: 'pestanas', role: 'tablist' });
  for (const [key, label] of items) {
    const b = h('button', { type: 'button', role: 'tab', class: 'pestana', text: label, 'aria-selected': key === active ? 'true' : 'false' });
    b.addEventListener('click', () => onChange(key));
    bar.append(b);
  }
  return bar;
}
