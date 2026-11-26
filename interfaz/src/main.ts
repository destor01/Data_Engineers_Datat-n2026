import './styles.css';
import './ine-theme.css';
import { mountExtensions } from './extensions';
import { mountAudio } from './audio';
import { mountDatos } from './datos';
import type { AudioJob, AuditResult } from './types';
import { demo } from './services/config';
import { listBases, audit } from './services/dataApi';
import { transcribe } from './services/audioApi';
import { message, setUnauthorizedHandler } from './services/http';
import { currentSession, loginEnabled, onSessionChange, signIn, signOut } from './services/auth';

function el<T extends HTMLElement = HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Falta el elemento ${id}`);
  return element as T;
}
function node<K extends keyof HTMLElementTagNameMap>(tag: K, text = '', className = ''): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag); element.textContent = text; element.className = className; return element;
}
function status(id: string, text: string, error = false) { el(id).textContent = text; el(id).classList.toggle('error', error); }
function processingError(error: unknown): string {
  return demo && error instanceof DOMException && error.name === 'AbortError'
    ? 'Se detuvo la demostración. Ningún archivo fue enviado.' : message(error);
}
function save(name: string, text: string, type = 'text/plain;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = node('a'); link.href = url; link.download = name; link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

mountExtensions();
const audioModulo = demo ? null : mountAudio();
const datosModulo = demo ? null : mountDatos();
el('modeBadge').textContent = demo ? 'Demostración' : loginEnabled ? 'Conectado' : 'Modo API · local';
el('modeBadge').classList.toggle('demo', demo);
el('demoNotice').hidden = !demo;
if (demo) { el('audioSubmit').textContent = 'Ver ejemplo de transcripción'; el('dataSubmit').textContent = 'Ver ejemplo de auditoría'; }
let basesLoaded = false;
// Supabase Storage (plan gratuito) acepta archivos de hasta 50 MB; se puede ajustar en el despliegue.
const maxMb = { audio: Number(import.meta.env.VITE_MAX_AUDIO_MB) || 50, data: Number(import.meta.env.VITE_MAX_DATA_MB) || 50 };
el('audioMax').textContent = String(maxMb.audio); el('dataMax').textContent = String(maxMb.data);
function route(focus = false) {
  const hash = location.hash.slice(1);
  const current = ['inicio', 'audio', 'datos', 'encuestas', 'mejora'].includes(hash) ? hash : 'inicio';
  document.querySelectorAll<HTMLElement>('.page').forEach(page => { page.hidden = page.id !== current; });
  document.querySelectorAll<HTMLAnchorElement>('[data-nav]').forEach(link => {
    const active = link.dataset.nav === current;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  document.title = `${current === 'inicio' ? 'Vista general' : current === 'audio' ? 'Audio Audit' : current === 'encuestas' ? 'Survey Audit' : current === 'mejora' ? 'Quality Improvement' : 'Data Audit'} · Quality Audit`;
  if (focus) { document.getElementById(`${current}Title`)?.focus({ preventScroll: true }); window.scrollTo({ top: 0 }); }
  if (current === 'datos' && !basesLoaded) void loadBases();
}
window.addEventListener('hashchange', () => route(true));
document.querySelector<HTMLAnchorElement>('.skip-link')?.addEventListener('click', event => {
  event.preventDefault(); el('contenido').focus();
});
let basesLoading = false;
async function loadBases() {
  if (basesLoading) return;
  basesLoading = true;
  const select = el<HTMLSelectElement>('base');
  select.disabled = true; el<HTMLButtonElement>('dataSubmit').disabled = true; el('retryBases').hidden = true;
  status('basesStatus', 'Consultando bases disponibles…');
  try {
    const bases = await listBases();
    select.replaceChildren(new Option('Selecciona una base', ''));
    bases.forEach(base => select.add(new Option(base.nombre, base.codigo)));
    basesLoaded = bases.length > 0; select.disabled = !basesLoaded; el<HTMLButtonElement>('dataSubmit').disabled = !basesLoaded;
    status('basesStatus', basesLoaded ? '' : 'No hay bases disponibles. El equipo debe configurar los catálogos del servicio.');
    el('retryBases').hidden = basesLoaded;
  } catch (error) {
    select.replaceChildren(new Option('No se pudieron cargar las bases', ''));
    status('basesStatus', message(error), true); el('retryBases').hidden = false;
  } finally { basesLoading = false; }
}
el('retryBases').addEventListener('click', () => void loadBases());
const now = new Date(); el<HTMLInputElement>('year').value = String(now.getFullYear());
['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'].forEach((month, index) => el<HTMLSelectElement>('month').add(new Option(month, String(index + 1), false, index === now.getMonth())));

for (const kind of ['audio', 'data'] as const) {
  el<HTMLInputElement>(`${kind}File`).addEventListener('change', () => {
    const file = el<HTMLInputElement>(`${kind}File`).files?.[0];
    const size = file ? file.size < 1024 * 1024 ? `${(file.size / 1024).toLocaleString('es-GT', { maximumFractionDigits: 2 })} KB` : `${(file.size / 1024 / 1024).toLocaleString('es-GT', { maximumFractionDigits: 2 })} MB` : '';
    el(`${kind}FileInfo`).textContent = file ? `${file.name} · ${size}` : 'Ningún archivo seleccionado.';
    status(`${kind}Status`, '');
  });
}
function selectedFile(kind: 'audio' | 'data'): File {
  const file = el<HTMLInputElement>(`${kind}File`).files?.[0];
  if (!file || !file.size) throw new Error('Selecciona un archivo que no esté vacío.');
  const max = maxMb[kind];
  if (file.size > max * 1024 * 1024) throw new Error(`El archivo supera el límite de ${max} MB.`);
  const valid = kind === 'audio' ? /\.(mp3|wav|m4a|ogg|flac|aac|opus|webm|wma|mp4)$/i : /\.(xlsx|xls|csv)$/i;
  if (!valid.test(file.name)) throw new Error('El formato del archivo no es compatible. Revisa los formatos indicados.');
  return file;
}
const controllers: Partial<Record<'audio' | 'data', AbortController>> = {};
function busy(kind: 'audio' | 'data', value: boolean) {
  el(`${kind}Form`).setAttribute('aria-busy', String(value));
  el<HTMLButtonElement>(`${kind}Submit`).disabled = value || (kind === 'data' && !basesLoaded);
  el(`${kind}Cancel`).hidden = !value;
  el<HTMLFormElement>(`${kind}Form`).querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select').forEach(input => { input.disabled = value || (input.id === 'base' && !basesLoaded); });
}
for (const kind of ['audio', 'data'] as const) el(`${kind}Cancel`).addEventListener('click', () => controllers[kind]?.abort());
window.addEventListener('beforeunload', event => { if (controllers.audio || controllers.data) { event.preventDefault(); event.returnValue = ''; } });

let audioObjectUrl: string | undefined;
el('audioForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (controllers.audio) return;
  try {
    const file = selectedFile('audio');
    const speakers = el<HTMLSelectElement>('speakers').value;
    const [min, max = min] = speakers === 'auto' ? [] : speakers.split('-').map(Number);
    const input = { file, model: el<HTMLSelectElement>('model').value, denoise: el<HTMLInputElement>('denoise').checked,
      diarize: el<HTMLInputElement>('diarize').checked, minSpeakers: min ?? null, maxSpeakers: max ?? null };
    controllers.audio = new AbortController(); busy('audio', true);
    const bar = el<HTMLProgressElement>('audioProgress'); bar.value = 0; bar.hidden = false;
    status('audioStatus', demo ? 'Preparando ejemplo. El audio no se está procesando.' : 'Enviando audio al servicio…');
    const job: AudioJob = await transcribe(input, controllers.audio.signal, (job: AudioJob) => {
      bar.value = Math.max(0, Math.min(100, job.progress)); status('audioStatus', job.stage);
    });
    if (audioObjectUrl) URL.revokeObjectURL(audioObjectUrl);
    audioObjectUrl = URL.createObjectURL(file);
    if (audioModulo) {
      // La transcripción, los roles de hablantes y la evaluación JEV se muestran en el módulo de Audio Audit.
      await audioModulo.abrir(job.job_id, audioObjectUrl);
      status('audioStatus', 'Transcripción completada. Asigna los roles de los hablantes y evalúa la entrevista con JEV.');
    } else {
      status('audioStatus', `Ejemplo listo: ${job.result?.turns.length ?? 0} intervenciones de demostración.`);
    }
  } catch (error) { status('audioStatus', processingError(error), true); }
  finally { delete controllers.audio; busy('audio', false); el('audioProgress').hidden = true; }
});

el('dataForm').addEventListener('submit', async event => {
  event.preventDefault(); if (controllers.data) return;
  try {
    const file = selectedFile('data');
    const input = { file, base: el<HTMLSelectElement>('base').value, anio: Number(el<HTMLInputElement>('year').value), mes: Number(el<HTMLSelectElement>('month').value) };
    if (!input.base) throw new Error('Selecciona la base institucional.');
    controllers.data = new AbortController(); busy('data', true);
    status('dataStatus', demo ? 'Preparando resultados de ejemplo. No se analiza el archivo.' : 'Preparando la auditoría…');
    const result: AuditResult = await audit(input, controllers.data.signal, text => status('dataStatus', text));
    el<HTMLInputElement>('dataFile').value = ''; el('dataFileInfo').textContent = 'Ningún archivo seleccionado.';
    if (datosModulo && result.carga_id) {
      // El resultado queda guardado: se abre su detalle (correcciones, hallazgos, descargas) y aparece en el historial.
      await datosModulo.refrescar();
      await datosModulo.abrir(result.carga_id);
      status('dataStatus', `Auditoría completada: puntaje ${result.reporte.puntaje?.toLocaleString('es-GT') ?? '—'}. Revisa abajo las correcciones sugeridas y los hallazgos.`);
    } else {
      status('dataStatus', `Ejemplo listo: puntaje ${result.reporte.puntaje ?? '—'} con ${result.reporte.hallazgos.length} hallazgos de demostración.`);
    }
  } catch (error) { status('dataStatus', processingError(error), true); }
  finally { delete controllers.data; busy('data', false); }
});
// ---------------------------------------------------------------------------
// Inicio de sesión (Supabase Auth). En modo demostración o local sin Supabase no se pide.
// ---------------------------------------------------------------------------
function showApp(email: string | null) {
  el('login').hidden = true; el('app').hidden = false;
  el('userEmail').textContent = email ?? ''; el('logout').hidden = !loginEnabled;
  route();
}
function showLogin(notice = '') {
  if (controllers.audio || controllers.data) { controllers.audio?.abort(); controllers.data?.abort(); }
  el('app').hidden = true; el('login').hidden = false; basesLoaded = false;
  status('loginStatus', notice, Boolean(notice));
  el<HTMLInputElement>('loginEmail').focus();
}
el('loginForm').addEventListener('submit', async event => {
  event.preventDefault();
  const button = el<HTMLButtonElement>('loginSubmit'); button.disabled = true; status('loginStatus', 'Verificando…');
  try {
    const session = await signIn(el<HTMLInputElement>('loginEmail').value, el<HTMLInputElement>('loginPassword').value);
    el<HTMLInputElement>('loginPassword').value = ''; status('loginStatus', '');
    showApp(session.user.email ?? null);
  } catch (error) { status('loginStatus', message(error), true); }
  finally { button.disabled = false; }
});
el('logout').addEventListener('click', async () => { await signOut(); showLogin(); });
setUnauthorizedHandler(() => { if (loginEnabled) showLogin('Tu sesión expiró. Vuelve a iniciar sesión.'); });
onSessionChange(session => { if (!session && loginEnabled && el('login').hidden) showLogin(); });

if (loginEnabled) {
  void currentSession().then(session => session ? showApp(session.user.email ?? null) : showLogin());
} else {
  showApp(null);
}
