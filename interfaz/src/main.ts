import './styles.css';
import './ine-theme.css';
import { mountExtensions } from './extensions';
import type { AudioJob, AuditResult } from './types';
import { demo, downloadUrl } from './services/config';
import { listBases, audit } from './services/dataApi';
import { transcribe } from './services/audioApi';
import { message } from './services/http';

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
function duration(seconds: number): string { return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`; }

mountExtensions();
el('modeBadge').textContent = demo ? 'Demostración' : 'Modo API';
el('modeBadge').classList.toggle('demo', demo);
el('demoNotice').hidden = !demo;
if (demo) { el('audioSubmit').textContent = 'Ver ejemplo de transcripción'; el('dataSubmit').textContent = 'Ver ejemplo de auditoría'; }
let basesLoaded = false;
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
  if (focus) { el(`${current}Title`).focus({ preventScroll: true }); window.scrollTo({ top: 0 }); }
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
    el(`${kind}Result`).hidden = true;
    status(`${kind}Status`, '');
  });
}
function selectedFile(kind: 'audio' | 'data'): File {
  const file = el<HTMLInputElement>(`${kind}File`).files?.[0];
  if (!file || !file.size) throw new Error('Selecciona un archivo que no esté vacío.');
  const max = kind === 'audio' ? 500 : 100;
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
let transcriptText = '';
el('audioForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (controllers.audio) return;
  try {
    const file = selectedFile('audio');
    const form = new FormData(); form.append('file', file);
    form.append('model', el<HTMLSelectElement>('model').value);
    form.append('denoise', String(el<HTMLInputElement>('denoise').checked));
    form.append('diarize', String(el<HTMLInputElement>('diarize').checked));
    const speakers = el<HTMLSelectElement>('speakers').value;
    if (speakers !== 'auto') { const [min, max = min] = speakers.split('-'); form.append('min_speakers', min); form.append('max_speakers', max); }
    controllers.audio = new AbortController(); busy('audio', true); el('audioResult').hidden = true;
    const bar = el<HTMLProgressElement>('audioProgress'); bar.value = 0; bar.hidden = false;
    status('audioStatus', demo ? 'Preparando ejemplo. El audio no se está procesando.' : 'Enviando audio al servicio…');
    const job = await transcribe(form, controllers.audio.signal, (job: AudioJob) => {
      bar.value = Math.max(0, Math.min(100, job.progress)); status('audioStatus', job.stage);
    });
    if (audioObjectUrl) URL.revokeObjectURL(audioObjectUrl);
    audioObjectUrl = URL.createObjectURL(file); el<HTMLAudioElement>('player').src = audioObjectUrl;
    const turns = job.result?.turns ?? [];
    const transcript = el('transcript'); transcript.replaceChildren();
    if (!turns.length) transcript.append(node('p', 'No se detectó voz en esta grabación.', 'empty'));
    for (const turn of turns) {
      const article = node('article', '', 'turn');
      const heading = node('div', '', 'turn-heading');
      const time = node('button', `${duration(turn.start)} – ${duration(turn.end)}`, 'time-button'); time.type = 'button'; time.setAttribute('aria-label', `Reproducir desde ${duration(turn.start)}`);
      time.addEventListener('click', () => {
        const player = el<HTMLAudioElement>('player'); player.currentTime = Math.max(0, turn.start);
        void player.play().catch(() => status('audioStatus', 'Usa los controles del reproductor para escuchar este archivo.', true));
      });
      heading.append(node('strong', turn.speaker), time); article.append(heading, node('p', turn.text)); transcript.append(article);
    }
    transcriptText = `${demo ? 'DEMOSTRACIÓN: texto de ejemplo, no corresponde al audio seleccionado.\n\n' : ''}${turns.map(turn => `[${duration(turn.start)} - ${duration(turn.end)}] ${turn.speaker}: ${turn.text}`).join('\n\n')}`;
    el('audioSummary').textContent = `${file.name} · ${turns.length} intervenciones${job.result?.warning ? ` · ${job.result.warning}` : ''}`;
    el('audioResult').hidden = false;
    status('audioStatus', demo ? 'Ejemplo listo. La grabación seleccionada no fue transcrita.' : 'Transcripción completada. Revisa el texto con el audio original.');
  } catch (error) { status('audioStatus', processingError(error), true); }
  finally { delete controllers.audio; busy('audio', false); el('audioProgress').hidden = true; }
});
el('downloadTranscript').addEventListener('click', () => save(demo ? 'ejemplo-transcripcion.txt' : 'transcripcion.txt', transcriptText));

let currentReport: AuditResult | undefined;
function renderFindings() {
  const filter = el<HTMLSelectElement>('severity').value;
  const findings = (currentReport?.reporte.hallazgos ?? []).filter(h => filter === 'all' || h.severidad === filter);
  const container = el('findings'); container.replaceChildren();
  if (!findings.length) { container.append(node('p', 'No hay hallazgos para esta selección.', 'empty')); return; }
  const table = node('table'); const caption = node('caption', 'Observaciones del motor de calidad'); caption.className = 'sr-only';
  const head = node('thead'); const headings = node('tr');
  for (const label of ['Severidad', 'Descripción', 'Registros']) { const cell = node('th', label); cell.scope = 'col'; headings.append(cell); }
  head.append(headings); const body = node('tbody');
  findings.forEach(finding => {
    const row = node('tr'); const severity = node('td'); severity.append(node('span', finding.severidad, `severity ${finding.severidad}`));
    row.append(severity, node('td', finding.mensaje), node('td', finding.n?.toLocaleString('es-GT') ?? '—')); body.append(row);
  });
  table.append(caption, head, body); container.append(table);
}
el('severity').addEventListener('change', renderFindings);
el('dataForm').addEventListener('submit', async event => {
  event.preventDefault(); if (controllers.data) return;
  try {
    const file = selectedFile('data');
    const form = new FormData(); form.append('file', file); form.append('base', el<HTMLSelectElement>('base').value); form.append('anio', el<HTMLInputElement>('year').value); form.append('mes', el<HTMLSelectElement>('month').value);
    controllers.data = new AbortController(); busy('data', true); el('dataResult').hidden = true;
    status('dataStatus', demo ? 'Preparando resultados de ejemplo. No se analiza el archivo.' : 'Auditando la base. El tiempo depende del tamaño del archivo…');
    currentReport = await audit(form, controllers.data.signal);
    const r = currentReport.reporte;
    el('reportContext').textContent = `${demo ? 'DATOS DE EJEMPLO · ' : ''}${file.name} · ${form.get('base')} · ${form.get('mes')}/${form.get('anio')}`;
    el('metrics').replaceChildren();
    for (const [label, value] of [['Puntaje global', r.puntaje], ['Registros recibidos', r.total_registros], ['Válidos', r.registros_validos], ['Excluidos', r.registros_excluidos]] as const) {
      const card = node('div', '', 'metric'); card.append(node('strong', value?.toLocaleString('es-GT') ?? '—'), node('span', label)); el('metrics').append(card);
    }
    el('dimensions').replaceChildren();
    for (const [name, value] of Object.entries(r.puntajes)) {
      const row = node('div', '', 'dimension'); const header = node('div'); header.append(node('span', name.replaceAll('_', ' ')), node('strong', value.toLocaleString('es-GT')));
      const bar = node('progress'); bar.max = 100; bar.value = Math.min(100, Math.max(0, value)); bar.setAttribute('aria-label', name); row.append(header, bar); el('dimensions').append(row);
    }
    el<HTMLSelectElement>('severity').value = 'all'; renderFindings(); el('downloads').replaceChildren();
    for (const [name, path] of Object.entries(currentReport.descargas)) {
      try { const link = node('a', `Descargar ${name}`, 'button secondary'); link.href = downloadUrl(path); link.target = '_blank'; link.rel = 'noopener noreferrer'; el('downloads').append(link); }
      catch { el('downloads').append(node('p', `El enlace de ${name} no es válido. Solicita el archivo al equipo del servicio.`, 'error')); }
    }
    el('dataResult').hidden = false;
    status('dataStatus', demo ? 'Ejemplo listo. Las cifras no corresponden al archivo seleccionado.' : 'Auditoría completada. Revisa los hallazgos y archivos disponibles.');
  } catch (error) { status('dataStatus', processingError(error), true); }
  finally { delete controllers.data; busy('data', false); }
});
el('downloadReport').addEventListener('click', () => {
  if (currentReport) save(demo ? 'ejemplo-auditoria.json' : 'resumen-auditoria.json', JSON.stringify({ modo: demo ? 'demostracion' : 'api', ...currentReport.reporte }, null, 2), 'application/json');
});
route();
