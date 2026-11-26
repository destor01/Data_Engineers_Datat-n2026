/**
 * Audio Audit: transcripción, evaluación JEV (ENCOVI A1–A2) y su reporte de puntajes.
 * Trae a la interfaz común lo que tenía la pantalla de React de audio-audit:
 * roles de hablantes, evaluación, reporte por sección, riesgos, edición de cada evaluación,
 * catálogo de reglas, calibración, historial y carga de transcripciones.
 */
import { add, api, ApiError, button, chip, confirmar, errorText, fetchBlob, field, fill, h, input, notice, run, saveBlob, select, textarea } from './ui';
import { send } from './services/http';
import { apiUrl } from './services/config';

type Rol = 'ENCUESTADOR' | 'INFORMANTE' | 'OTRA_PERSONA';
type Tipo = 'obligation' | 'prohibition' | 'conditional' | 'evidence';
type Turno = { speaker: string; start: number | null; end: number | null; text: string; has_overlap?: boolean };
type Ventana = { window: number; followed: number; broken: number; unknown: number; p_trigger?: number };
type Rango = [number | null, number | null] | null | undefined;
type Correccion = { status: string; comment: string } | null | undefined;
type Instruccion = {
  id: string; section: string; text: string; pages: string; kind: Tipo; weight: 1 | 2 | 3; verifiability: string; note: string;
  p_followed: number; p_broken: number; p_unknown: number; windows?: Ventana[];
  worst_window?: { window: number; p_broken: number; time?: Rango }; windows_flagged?: number; windows_review?: number;
  flagged_per_hour?: number; triggered_windows?: number; original_outcome?: { p_followed: number; p_broken: number; p_unknown: number };
  manual_override?: Correccion; is_rule_customized?: boolean; auditor_guidance?: string;
};
type Riesgo = { id: string; p_broken: number; text: string; worst_window: number | null; time?: Rango; manual_override?: Correccion; is_rule_customized?: boolean };
type Seccion = {
  title: string; n_instructions: number; coverage: number | null; expected_broken: number | null; compliance_rate: number | null;
  compliance_rate_weighted: number | null; conduct_flagged_windows?: number; conduct_flagged_per_hour?: number;
};
type Evaluacion = {
  model: string | null; mock: boolean; warning?: string | null; speaker_map: Record<string, Rol>;
  gates: { opening?: number | null; closing?: number | null };
  calibration?: { is_calibrated: boolean; fitted_groups: string[]; total_labels: number | null; min_labels: number };
  windows: { window: number }[]; sections: Record<string, Seccion>; instructions: Instruccion[];
  usage: { requests: number; cache_hits: number; input_tokens: number; cost_usd: number };
  overall: {
    compliance_rate: number | null; compliance_rate_weighted: number | null; coverage: number | null;
    conduct_flagged_windows?: number; conduct_flagged_per_hour?: number; high_risk_count: number; review_count: number;
    manual_edit_count?: number; verdict: { label: string; level: 'ok' | 'warn' | 'danger' | 'muted' }; top_risks: Riesgo[];
  };
};
type Trabajo = {
  job_id: string; filename: string; source: string; stt_provider: string | null; has_audio: boolean;
  status: 'queued' | 'processing' | 'completed' | 'error'; stage: string; progress: number; duration_seconds: number | null;
  result: { turns: Turno[]; speakers: string[]; suggested_roles?: Record<string, Rol>; note?: string | null; warning?: string | null } | null;
  error: string | null; eval_status: string; eval_elapsed_seconds: number; evaluation: Evaluacion | null;
};
type Resumen = { job_id: string; filename: string; status: string; created_at_iso?: string; compliance_rate_weighted?: number | null; verdict?: { label: string; level: string } | null; manual_edit_count?: number };
type Pregunta = { key: string; type: 'noul' | 'choice'; is_trigger?: boolean; instructions: string; criteria: Record<string, string>; roles: Record<string, string> };
type Regla = {
  id: string; section: string; section_title: string; text: string; default_text: string; pages: string; kind: Tipo; weight: 1 | 2 | 3;
  enabled: boolean; auditor_guidance: string; is_customized: boolean; questions: Pregunta[];
};
type Grupo = { n: number; fitted: boolean; positives?: number; negatives?: number; a?: number; b?: number; brier_raw?: number; brier_cal_in_sample?: number; ece_raw?: number; ece_cal_in_sample?: number; temperature?: number; accuracy?: number };
type Calibracion = { model_version: string; is_calibrated: boolean; total_labels: number; min_labels: number; groups: Record<string, Grupo> };
type Estado = { jev_available: boolean; jev_model: string; openrouter_configured: boolean; example_available: boolean; customized_rules_count: number; calibration?: Calibracion };

const ROLES: [Rol, string][] = [['ENCUESTADOR', 'Encuestador(a)'], ['INFORMANTE', 'Informante'], ['OTRA_PERSONA', 'Otra persona']];
const TIPOS: Record<string, string> = { obligation: 'Obligación', prohibition: 'Prohibición', conditional: 'Condicional', evidence: 'Evidencia' };
const PESOS: Record<number, string> = { 1: 'Baja (1)', 2: 'Media (2)', 3: 'Alta (3)' };
const GRUPOS: Record<string, string> = {
  'noul/obligation': 'Obligaciones (apertura y cierre)', 'noul/prohibition': 'Conducta y prohibiciones',
  'noul/trigger': 'Activadores condicionales («si ocurre X»)', 'noul/gate': 'Compuertas de apertura y cierre',
  'choice/conditional': 'Condicionales: respuesta del encuestador', 'choice/evidence': 'Evidencia silenciosa',
};
const CRITERIOS: Record<string, string> = {
  true: 'Sí ocurre / cumple el criterio', false: 'No ocurre / situación opuesta',
  followed: 'Opción: cumplida', broken: 'Opción: incumplida', unknown: 'Opción: no aplica / sin evidencia',
};

const pct = (v: number | null | undefined, d = 0) => v == null || Number.isNaN(v) ? 'n/d' : `${(v * 100).toFixed(d)} %`;
const tiempo = (s: number | null | undefined) => {
  if (s == null || Number.isNaN(s)) return '';
  const t = Math.max(0, Math.floor(s)); const hh = Math.floor(t / 3600); const mm = Math.floor((t % 3600) / 60); const ss = t % 60;
  const p = (n: number) => String(n).padStart(2, '0');
  return hh ? `${p(hh)}:${p(mm)}:${p(ss)}` : `${p(mm)}:${p(ss)}`;
};
const rango = (r: Rango) => {
  if (!Array.isArray(r) || (r[0] == null && r[1] == null)) return null;
  const a = r[0] != null ? tiempo(r[0]) : '—'; const b = r[1] != null ? tiempo(r[1]) : '—';
  return a === b ? a : `${a} – ${b}`;
};
const tono = (v: number | null | undefined) => v == null ? '' : v >= 0.85 ? 'nivel-ok' : v >= 0.7 ? 'nivel-warn' : 'nivel-bad';
const tonoChip = (level: string): 'ok' | 'warn' | 'bad' | 'neutral' => level === 'ok' ? 'ok' : level === 'warn' ? 'warn' : level === 'danger' ? 'bad' : 'neutral';
function clasificar(i: Instruccion): string {
  if (i.p_broken >= 0.7 || (i.windows_flagged ?? 0) > 0) return 'broken';
  if (i.p_broken >= 0.3 || (i.windows_review ?? 0) > 0) return 'review';
  if (i.p_unknown >= 0.7 && i.p_followed < 0.3) return 'unknown';
  return 'followed';
}
function hablantes(t: Trabajo): string[] {
  const r = t.result; if (!r) return [];
  return r.speakers?.length ? r.speakers : [...new Set(r.turns.map(x => x.speaker))];
}

/** Ventana modal sencilla (dialog nativo). */
function modal(titulo: string, ...contenido: (Node | null)[]): { el: HTMLDialogElement; cerrar: () => void } {
  const el = h('dialog', { class: 'modal-audio', 'aria-label': titulo });
  const cerrar = () => { el.close(); el.remove(); };
  el.addEventListener('cancel', e => { e.preventDefault(); cerrar(); });
  el.addEventListener('click', e => { if (e.target === el) cerrar(); });
  const x = h('button', { type: 'button', class: 'modal-cerrar', 'aria-label': 'Cerrar', text: '✕' }); x.addEventListener('click', cerrar);
  add(el, h('div', { class: 'modal-cabeza' }, h('h2', { text: titulo }), x), h('div', { class: 'modal-cuerpo' }, ...contenido));
  document.body.append(el); el.showModal();
  return { el, cerrar };
}

export function mountAudio(): { abrir: (jobId: string, audioLocal?: string) => Promise<void> } {
  const pagina = document.getElementById('audio');
  if (!pagina) throw new Error('Falta la página de Audio Audit');
  const msg = notice();
  const panel = h('div', { class: 'audio-panel' });
  const zona = h('div', { class: 'audio-zona' });
  const anterior = document.getElementById('audioResult');
  anterior?.remove();
  pagina.append(panel, msg, zona);

  let estado: Estado | null = null;
  let calibracion: Calibracion | null = null;
  let reglas: Regla[] = [];
  let recientes: Resumen[] = [];
  let actual: Trabajo | null = null;
  let audioUrl: string | null = null;
  let roles: Record<string, Rol> = {};
  let primeraVisita = true;
  let reproductor: HTMLAudioElement | null = null;
  let lista: HTMLElement | null = null;

  async function refrescar() {
    const [st, jobs, cat, cal] = await Promise.all([
      api<Estado>('status').catch(() => null),
      api<{ jobs: Resumen[] }>('jobs?limit=20').then(r => r.jobs).catch(() => [] as Resumen[]),
      api<{ rules: Regla[] }>('rules').then(r => r.rules).catch(() => [] as Regla[]),
      api<Calibracion>('calibration').catch(() => null),
    ]);
    estado = st; recientes = jobs; reglas = cat; calibracion = cal ?? st?.calibration ?? null;
    pintarPanel();
  }

  // ---------------------------------------------------------------- Panel superior
  function pintarPanel() {
    const jevListo = Boolean(estado?.openrouter_configured);
    const estadoJev = h('div', { class: 'fila-chips' },
      chip(jevListo ? `Evaluación JEV lista · ${estado?.jev_model ?? ''}` : 'Evaluación JEV: falta la llave OPENROUTER_API_KEY', jevListo ? 'ok' : 'warn'),
      button(`Reglas de evaluación (${reglas.length || 51})${estado?.customized_rules_count ? ` · ${estado.customized_rules_count} editadas` : ''}`, () => abrirCatalogo(), 'secondary'),
      button(calibracion?.is_calibrated ? `Calibración activa (${Object.values(calibracion.groups ?? {}).filter(g => g.fitted).length} grupos)` : `Calibración: ${calibracion?.total_labels ?? 0} correcciones`, () => abrirCalibracion(), 'secondary'));
    const aviso = jevListo ? null : h('p', { class: 'muted', text: 'Para calcular el puntaje con JEV, agrega OPENROUTER_API_KEY (secreta) en las variables de Vercel..' });

    const archivo = input('file', '', { accept: '.json,.txt,application/json,text/plain' });
    const cargar = button('Cargar transcripción', () => run(cargar, msg, async () => {
      const f = archivo.files?.[0];
      if (!f) throw new Error('Selecciona una transcripción .json o .txt.');
      if (f.size > 5 * 1024 * 1024) throw new Error('La transcripción supera el límite de 5 MB.');
      const form = new FormData(); form.append('file', f);
      const t = await api<Trabajo>('transcript/upload', 'POST', form);
      archivo.value = '';
      await mostrar(t, null); void refrescar();
      return 'Transcripción cargada. Asigna los roles y evalúa la entrevista.';
    }), 'primary');

    const historial = recientes.length ? h('div', { class: 'historial-audio' }, ...recientes.slice(0, 10).map(j => {
      const b = h('button', { type: 'button', class: `historial-item${actual?.job_id === j.job_id ? ' activo' : ''}` },
        h('span', { class: 'nombre', text: j.filename }),
        j.compliance_rate_weighted != null ? h('span', { class: `puntaje ${tono(j.compliance_rate_weighted)}`, text: pct(j.compliance_rate_weighted) }) : h('span', { class: 'muted', text: j.status === 'completed' ? 'Sin evaluar' : j.status === 'error' ? 'Con error' : 'En proceso' }),
        j.manual_edit_count ? h('span', { class: 'muted', text: `✎ ${j.manual_edit_count}` }) : null);
      b.addEventListener('click', () => void run(null, msg, async () => { await abrir(j.job_id); }));
      return b;
    })) : h('p', { class: 'muted', text: 'Todavía no hay entrevistas procesadas.' });

    fill(panel,
      h('section', { class: 'card' }, h('h2', { text: 'Evaluación de la entrevista' }), estadoJev, aviso),
      h('div', { class: 'editor-grid audio-extra' },
        h('section', { class: 'card' }, h('h2', { text: '¿Ya tienes la transcripción?' }),
          h('p', { class: 'muted', text: 'Sube un JSON de turnos o un TXT con marcas de hablante (por ejemplo, los que descargas aquí) para evaluarlo sin volver a transcribir.' }),
          field('Transcripción (.json o .txt)', archivo), h('div', { class: 'form-actions' }, cargar)),
        h('section', { class: 'card' }, h('h2', { text: 'Entrevistas recientes' }), historial)));
  }

  // ---------------------------------------------------------------- Trabajo
  async function abrir(jobId: string, audioLocal?: string) {
    const t = await api<Trabajo>(`jobs/${encodeURIComponent(jobId)}`);
    await mostrar(t, audioLocal ?? null);
  }

  async function mostrar(t: Trabajo, audioLocal: string | null) {
    if (actual?.job_id !== t.job_id) {
      audioUrl = audioLocal;
      const base: Record<string, Rol> = { ...(t.evaluation?.speaker_map ?? t.result?.suggested_roles ?? {}) };
      hablantes(t).forEach((s, i) => { base[s] ??= i === 0 ? 'ENCUESTADOR' : i === 1 ? 'INFORMANTE' : 'OTRA_PERSONA'; });
      roles = base;
    } else if (audioLocal) audioUrl = audioLocal;
    actual = t;
    pintar();
    pintarPanel();
  }

  function pintar() {
    const t = actual;
    if (!t) { zona.replaceChildren(); return; }
    if (t.status !== 'completed' || !t.result) {
      fill(zona, h('section', { class: 'card' }, h('h2', { text: t.filename }),
        h('p', { text: t.status === 'error' ? (t.error || 'La transcripción terminó con error.') : `${t.stage || 'Procesando…'} (${Math.round(t.progress)} %)` })));
      return;
    }
    fill(zona, tarjetaTranscripcion(t), t.evaluation ? tarjetaReporte(t, t.evaluation) : null);
  }

  function irA(segundos: number | null | undefined) {
    if (segundos == null || !actual?.result) return;
    if (reproductor && reproductor.src) {
      reproductor.currentTime = Math.max(0, segundos);
      void reproductor.play().catch(() => undefined);
    }
    const turnos = actual.result.turns;
    let mejor = 0, dif = Infinity;
    turnos.forEach((x, i) => { if (x.start != null && Math.abs(x.start - segundos) < dif) { dif = Math.abs(x.start - segundos); mejor = i; } });
    const el = lista?.querySelector<HTMLElement>(`[data-turno="${mejor}"]`);
    if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); el.classList.add('resaltado'); window.setTimeout(() => el.classList.remove('resaltado'), 2200); }
  }

  function textoPlano(t: Trabajo): string {
    return (t.result?.turns ?? []).map(x => {
      const a = tiempo(x.start), b = tiempo(x.end);
      return `${a ? `[${a}${b && b !== a ? ` - ${b}` : ''}] ` : ''}${x.speaker}: ${x.text}`;
    }).join('\n\n');
  }

  function tarjetaTranscripcion(t: Trabajo): HTMLElement {
    const r = t.result!;
    const spk = hablantes(t);
    const local = notice();
    const base = t.filename.replace(/\.[^.]+$/, '');
    const copiar = button('Copiar texto', async () => {
      try { await navigator.clipboard.writeText(textoPlano(t)); copiar.textContent = '¡Copiado!'; window.setTimeout(() => { copiar.textContent = 'Copiar texto'; }, 1800); }
      catch { local.show('No se pudo copiar al portapapeles.', true); }
    });
    const txt = button('Descargar TXT', () => saveBlob(new Blob([textoPlano(t)], { type: 'text/plain;charset=utf-8' }), `${base}-transcripcion.txt`));
    const json = button('Descargar JSON', () => {
      // Formato que Survey Audit acepta para vincular la grabación a una entrevista.
      const datos = { fuente: 'Audio Audit', job_id: t.job_id, archivo: t.filename, generado: new Date().toISOString(), result: { speakers: spk, turns: r.turns } };
      saveBlob(new Blob([JSON.stringify(datos, null, 2)], { type: 'application/json' }), `${base}-transcripcion.json`);
    });
    json.title = 'Archivo para vincular la grabación en Survey Audit';

    // Audio: el archivo recién subido se escucha desde el navegador; el de una entrevista anterior se pide al servidor.
    reproductor = h('audio', { controls: true, preload: 'metadata' });
    if (audioUrl) reproductor.src = audioUrl;
    const cargarAudio: HTMLButtonElement | null = t.has_audio && !audioUrl ? button('Escuchar grabación', () => run(cargarAudio, local, async () => {
      const resp = await send(apiUrl(`/api/jobs/${encodeURIComponent(t.job_id)}/audio`), {}, 180_000);
      if (!resp.ok) throw new Error('No se pudo obtener la grabación.');
      audioUrl = URL.createObjectURL(await resp.blob());
      reproductor!.src = audioUrl; reproductor!.hidden = false; cargarAudio!.hidden = true;
      void reproductor!.play().catch(() => undefined);
    })) : null;
    if (cargarAudio) reproductor.hidden = true;

    // Roles y evaluación JEV
    const selects = spk.map(s => {
      const sel = select(ROLES, roles[s] ?? 'OTRA_PERSONA');
      sel.addEventListener('change', () => { roles[s] = sel.value as Rol; leyenda(); pintarTurnos(); });
      const muestra = r.turns.filter(x => x.speaker === s).slice(0, 2).map(x => `«${x.text.slice(0, 90)}${x.text.length > 90 ? '…' : ''}»`).join(' ');
      return h('div', { class: 'rol-hablante' }, h('strong', { text: s }), sel, h('p', { class: 'muted', text: muestra }));
    });
    const primera = input('checkbox'); primera.checked = primeraVisita;
    primera.addEventListener('change', () => { primeraVisita = primera.checked; });
    const evaluar = button(t.evaluation ? 'Volver a evaluar con JEV' : 'Evaluar con JEV', () => run(evaluar, local, async () => {
      if (!Object.values(roles).includes('ENCUESTADOR')) throw new Error('Indica qué hablante es el encuestador antes de evaluar.');
      if (!estado?.openrouter_configured) throw new Error('Falta la llave OPENROUTER_API_KEY en el servidor. Agrégala en las variables de Vercel.');
      local.show('Evaluando la entrevista con JEV… puede tardar unos minutos.');
      const nuevo = await api<Trabajo>(`jobs/${encodeURIComponent(t.job_id)}/evaluate`, 'POST', { speaker_map: roles, first_contact: primeraVisita, mock: false }, 300_000);
      actual = nuevo; pintar(); void refrescar();
      window.setTimeout(() => zona.querySelector('.reporte-jev')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120);
    }), 'primary');

    const leyendaEl = h('div', { class: 'fila-chips' });
    const leyenda = () => fill(leyendaEl, ...spk.map(s => chip(`${s} → ${ROLES.find(([k]) => k === roles[s])?.[1] ?? 'Otra persona'}`, roles[s] === 'ENCUESTADOR' ? 'info' : 'neutral')));
    leyenda();
    lista = h('div', { class: 'transcript' });
    const pintarTurnos = () => fill(lista!, ...(r.turns.length ? r.turns.map((x, i) => {
      const hora = x.start != null ? h('button', { type: 'button', class: 'time-button', text: x.end != null && tiempo(x.end) !== tiempo(x.start) ? `${tiempo(x.start)} – ${tiempo(x.end)}` : tiempo(x.start), 'aria-label': `Ir a ${tiempo(x.start)}` }) : null;
      hora?.addEventListener('click', () => irA(x.start));
      const rol = roles[x.speaker];
      return h('article', { class: `turn${rol === 'ENCUESTADOR' ? ' encuestador' : ''}`, 'data-turno': i },
        h('div', { class: 'turn-heading' }, h('strong', { text: x.speaker }), rol ? chip(ROLES.find(([k]) => k === rol)?.[1] ?? rol, rol === 'ENCUESTADOR' ? 'info' : 'neutral') : null, hora,
          x.has_overlap ? chip('Voces superpuestas', 'warn') : null),
        h('p', { text: x.text }));
    }) : [h('p', { class: 'empty', text: 'No se detectó voz en esta grabación.' })]));
    pintarTurnos();

    const resumen = [t.filename, `${r.turns.length} intervenciones`, spk.length ? `${spk.length} ${spk.length === 1 ? 'hablante' : 'hablantes'}` : 'sin separación de hablantes',
      t.duration_seconds ? `duración ${tiempo(t.duration_seconds)}` : null].filter(Boolean).join(' · ');

    return h('section', { class: 'card results' },
      h('div', { class: 'card-heading' }, h('div', {}, h('span', { class: 'eyebrow', text: 'TRANSCRIPCIÓN' }), h('h2', { text: 'Texto de la entrevista' })),
        h('div', { class: 'downloads', style: 'margin:0' }, copiar, txt, json)),
      h('p', { class: 'muted', text: resumen }),
      r.warning ? h('p', { class: 'aviso error', text: r.warning }) : null,
      r.note ? h('p', { class: 'aviso', text: r.note }) : null,
      reproductor, cargarAudio,
      h('div', { class: 'lanzador-jev' },
        h('h3', { text: 'Evaluar la entrevista con JEV (ENCOVI A1–A2)' }),
        h('p', { class: 'muted', text: 'Confirma quién es el encuestador y quién el informante; luego ejecuta la evaluación. Se aplican las reglas que hayas reescrito.' }),
        h('div', { class: 'roles-hablantes' }, ...selects),
        h('label', { class: 'check' }, primera, 'Primera visita / contacto inicial (evalúa las reglas de apertura A1)'),
        h('div', { class: 'form-actions' }, evaluar), local),
      leyendaEl, lista);
  }

  // ---------------------------------------------------------------- Reporte
  function tarjetaReporte(t: Trabajo, ev: Evaluacion): HTMLElement {
    const o = ev.overall;
    const local = notice();
    const descargar = button('Descargar reporte (.json)', () => run(descargar, local, async () => {
      const { blob, name } = await fetchBlob(`jobs/${encodeURIComponent(t.job_id)}/evaluation/download`);
      saveBlob(blob, name === 'archivo' ? `${t.filename.replace(/\.[^.]+$/, '')}-evaluacion-jev.json` : name);
    }), 'primary');
    const caja = (titulo: string, valor: string, clase: string, sub: string) =>
      h('div', { class: 'kpi' }, h('span', { class: 'kpi-titulo', text: titulo }), h('strong', { class: `kpi-valor ${clase}`, text: valor }), h('span', { class: 'muted', text: sub }));
    const conducta = o.conduct_flagged_per_hour ?? 0;
    const kpis = h('div', { class: 'kpis' },
      caja('Cumplimiento global', pct(o.compliance_rate_weighted ?? o.compliance_rate), tono(o.compliance_rate_weighted ?? o.compliance_rate), `Simple: ${pct(o.compliance_rate)} · Cobertura: ${pct(o.coverage)}`),
      caja('Conducta: marcadas por hora', `${conducta.toFixed(2)} / h`, conducta >= 2.5 ? 'nivel-bad' : conducta >= 0.5 ? 'nivel-warn' : 'nivel-ok', `${o.conduct_flagged_windows ?? 0} ${(o.conduct_flagged_windows ?? 0) === 1 ? 'ventana marcada' : 'ventanas marcadas'} (≥ 70 %)`),
      caja('Riesgos altos (≥ 70 %)', String(o.high_risk_count), o.high_risk_count > 0 ? 'nivel-bad' : 'nivel-ok', `En revisión (30–69 %): ${o.review_count}`),
      caja('Apertura / cierre', `${ev.gates.opening != null ? pct(ev.gates.opening) : 'Omitida'} / ${ev.gates.closing != null ? pct(ev.gates.closing) : 'n/d'}`, '',
        ev.calibration?.is_calibrated ? `Calibrado (${ev.calibration.fitted_groups.length} grupos)` : `Sin calibrar (${calibracion?.total_labels ?? 0} correcciones)`));

    const secciones = h('div', { class: 'secciones-jev' }, ...Object.entries(ev.sections).map(([id, s]) => {
      const v = s.compliance_rate_weighted ?? s.compliance_rate;
      const barra = h('div', { class: 'barra' }, h('div', { class: `relleno ${tono(v)}`, style: `width:${v != null ? Math.round(v * 100) : 0}%` }));
      const fila = (a: string, b: string) => h('div', { class: 'metrica' }, h('span', { text: a }), h('strong', { text: b }));
      return h('div', { class: 'seccion-jev' },
        h('div', { class: 'seccion-jev-cabeza' }, h('div', {}, h('h3', { text: `${id} · ${s.title}` }), h('span', { class: 'muted', text: `${s.n_instructions} instrucciones` })),
          h('strong', { class: `kpi-valor ${tono(v)}`, text: pct(v) })),
        barra,
        fila('Cumplimiento simple', pct(s.compliance_rate)),
        fila('Conducta: marcadas por hora', `${(s.conduct_flagged_per_hour ?? 0).toFixed(2)} / h (${s.conduct_flagged_windows ?? 0} vent.)`),
        fila('Incumplimientos esperados', s.expected_broken != null ? s.expected_broken.toFixed(1) : '—'),
        fila('Cobertura evaluable', pct(s.coverage)));
    }));

    const momento = (r: Rango, etiqueta?: string) => {
      const txt = rango(r);
      if (!txt) return null;
      const b = h('button', { type: 'button', class: 'time-button', text: `${etiqueta ?? ''}${txt}` });
      b.addEventListener('click', () => irA(r?.[0]));
      return b;
    };
    const riesgos = o.top_risks.length ? h('div', { class: 'riesgos' }, ...o.top_risks.map(x => {
      const alto = x.p_broken >= 0.7;
      return h('div', { class: `riesgo${alto ? '' : ' revisar'}` },
        h('div', { class: 'fila-chips' }, chip(x.id, 'info'), chip(`${pct(x.p_broken)} de incumplimiento`, alto ? 'bad' : 'warn'),
          x.manual_override ? chip('Corregida manualmente', 'info') : null, x.is_rule_customized ? chip('Criterio reescrito', 'neutral') : null,
          momento(x.time, x.worst_window != null ? `Ventana ${x.worst_window + 1} · ` : ''),
          button('✎ Editar evaluación', () => editarEvaluacion(x.id), 'secondary')),
        h('p', { text: x.text }));
    })) : h('p', { class: 'aviso ok', text: 'No se detectaron incumplimientos probables (probabilidad ≥ 30 %).' });

    // Tabla de todas las evaluaciones con filtros
    let filtro = 'all', seccion = 'ALL', busqueda = '';
    const cuerpo = h('tbody');
    const contador = h('span', { class: 'chip neutral' });
    const pintarTabla = () => {
      const q = busqueda.trim().toLowerCase();
      const filas = ev.instructions.filter(i => {
        if (seccion !== 'ALL' && i.section !== seccion) return false;
        if (filtro === 'edited') { if (!i.manual_override && !i.is_rule_customized) return false; }
        else if (filtro !== 'all' && clasificar(i) !== filtro) return false;
        return !q || `${i.id} ${i.text} ${i.note ?? ''} ${i.manual_override?.comment ?? ''} ${i.auditor_guidance ?? ''}`.toLowerCase().includes(q);
      });
      contador.textContent = `${filas.length} de ${ev.instructions.length}`;
      fill(cuerpo, ...(filas.length ? filas.map(i => {
        const barra = h('div', { class: 'prob', title: `Cumplida ${pct(i.p_followed)} · Incumplida ${pct(i.p_broken)} · No aplica ${pct(i.p_unknown)}` },
          h('div', { class: 'prob-c', style: `width:${(i.p_followed * 100).toFixed(1)}%` }), h('div', { class: 'prob-i', style: `width:${(i.p_broken * 100).toFixed(1)}%` }),
          h('div', { class: 'prob-n', style: `width:${(i.p_unknown * 100).toFixed(1)}%` }));
        const extra = i.kind === 'prohibition' && (i.windows_flagged ?? 0) > 0
          ? `${i.windows_flagged} ${i.windows_flagged === 1 ? 'ventana marcada' : 'ventanas marcadas'}${i.flagged_per_hour != null ? ` (${i.flagged_per_hour.toFixed(2)} / h)` : ''}`
          : i.kind === 'conditional' && i.triggered_windows != null
            ? i.triggered_windows > 0 ? `Situación detectada en ${i.triggered_windows} ${i.triggered_windows === 1 ? 'ventana' : 'ventanas'}` : 'No se presentó en esta entrevista' : '';
        const ww = i.worst_window;
        return h('tr', { class: i.manual_override ? 'editada' : '' },
          h('td', {}, h('div', { class: 'fila-chips' }, chip(i.id, 'info'), i.manual_override ? chip('Corregida aquí', 'info') : null, i.is_rule_customized ? chip('Criterio reescrito', 'neutral') : null),
            h('p', { text: i.text }),
            h('p', { class: 'muted', text: [i.pages ? `Manual ${i.pages}` : '', i.verifiability ? `Audibilidad: ${i.verifiability}` : '', i.note].filter(Boolean).join(' · ') }),
            i.manual_override?.comment ? h('p', { class: 'nota-auditor' }, h('strong', { text: 'Auditor: ' }), i.manual_override.comment) : null,
            i.auditor_guidance ? h('p', { class: 'nota-auditor' }, h('strong', { text: 'Criterio para próximas entrevistas: ' }), i.auditor_guidance) : null),
          h('td', {}, h('p', { text: TIPOS[i.kind] ?? i.kind }), h('p', { class: 'muted', text: `Peso: ${PESOS[i.weight] ?? i.weight}` })),
          h('td', {}, barra, h('p', { class: 'prob-numeros' }, h('span', { class: 'nivel-ok', text: `C: ${pct(i.p_followed)}` }), h('span', { class: 'nivel-bad', text: `I: ${pct(i.p_broken)}` }), h('span', { class: 'muted', text: `N/A: ${pct(i.p_unknown)}` })),
            extra ? h('p', { class: 'muted', text: extra }) : null),
          h('td', {}, ww ? momento(ww.time) ?? `Ventana ${ww.window + 1}` : '—'),
          h('td', {}, button('✎ Editar', () => editarEvaluacion(i.id), 'secondary')));
      }) : [h('tr', {}, h('td', { colspan: 5, class: 'muted', text: 'No hay evaluaciones que coincidan con este filtro.' }))]));
    };
    const filtros = h('div', { class: 'pestanas' });
    const opcionesFiltro: [string, string][] = [['all', 'Todas'], ['broken', 'Incumplidas (≥ 70 %)'], ['review', 'Revisar (30–69 %)'], ['followed', 'Cumplidas'], ['unknown', 'No aplica / sin evidencia'], ['edited', '✎ Editadas o reescritas']];
    const pintarFiltros = () => fill(filtros, ...opcionesFiltro.map(([k, l]) => {
      const b = h('button', { type: 'button', class: 'pestana', text: l, 'aria-selected': k === filtro ? 'true' : 'false' });
      b.addEventListener('click', () => { filtro = k; pintarFiltros(); pintarTabla(); });
      return b;
    }));
    pintarFiltros();
    const selSeccion = select([['ALL', 'Todas las secciones'], ...Object.entries(ev.sections).map(([k, s]) => [k, `${k} · ${s.title}`] as [string, string])]);
    selSeccion.addEventListener('change', () => { seccion = selSeccion.value; pintarTabla(); });
    const buscar = input('search', '', { placeholder: 'Buscar por código, texto o nota del auditor…' });
    buscar.addEventListener('input', () => { busqueda = buscar.value; pintarTabla(); });
    pintarTabla();

    const uso = ev.usage;
    const resumen = `Modelo: ${ev.model || 'typesafe/jev-1.14'}${ev.mock ? ' (simulado)' : ''} · ${ev.windows.length} ${ev.windows.length === 1 ? 'ventana' : 'ventanas'} · ${uso.requests} consultas${uso.cache_hits ? ` (${uso.cache_hits} en caché)` : ''} · ${uso.input_tokens.toLocaleString('es-GT')} tokens · $${uso.cost_usd.toFixed(4)} USD${t.eval_elapsed_seconds ? ` · ${t.eval_elapsed_seconds.toFixed(1)} s` : ''}`;
    return h('section', { class: 'card reporte-jev' },
      h('div', { class: 'card-heading' },
        h('div', {}, h('span', { class: 'eyebrow', text: 'EVALUACIÓN JEV' }),
          h('div', { class: 'fila-chips' }, h('h2', { text: 'Puntaje de la entrevista' }), chip(o.verdict.label, tonoChip(o.verdict.level)),
            o.manual_edit_count ? chip(`${o.manual_edit_count} ${o.manual_edit_count === 1 ? 'evaluación corregida' : 'evaluaciones corregidas'}`, 'info') : null)),
        h('div', { class: 'downloads', style: 'margin:0' }, button('Reglas de evaluación', () => abrirCatalogo()), descargar)),
      h('p', { class: 'muted', text: resumen }),
      ev.mock && !ev.warning ? h('p', { class: 'aviso', text: 'Esta evaluación es simulada (modo de prueba): los puntajes no son reales.' }) : null,
      ev.warning ? h('p', { class: 'aviso error', text: ev.warning }) : null,
      local, kpis, secciones,
      h('h3', { text: 'Principales riesgos detectados' }),
      h('p', { class: 'muted', text: 'Si no estás de acuerdo con un resultado, usa «Editar evaluación» para corregirlo en esta entrevista y, si quieres, para las próximas.' }),
      riesgos,
      h('details', { class: 'todas-evaluaciones', open: true },
        h('summary', {}, h('span', { text: `Todas las evaluaciones (${ev.instructions.length} reglas)` }), contador),
        filtros, h('div', { class: 'campos-linea' }, field('Sección', selSeccion), field('Buscar', buscar)),
        h('div', { class: 'tabla-scroll' }, h('table', { class: 'tabla-jev' },
          h('thead', {}, h('tr', {}, ...['Regla', 'Tipo / peso', 'Resultado (cumplida / incumplida / no aplica)', 'Momento', ''].map(x => h('th', { scope: 'col', text: x })))), cuerpo))));
  }

  // ---------------------------------------------------------------- Edición de una evaluación o de una regla
  function formularioRegla(regla: Regla, alCambiar: () => void) {
    const peso = select([['1', 'Baja (1): detalle de cortesía o ejemplo'], ['2', 'Media (2): procedimiento explícito'], ['3', 'Alta (3): protege al informante o la validez del dato']], String(regla.weight));
    const activa = select([['si', 'Activa (se evalúa en próximas transcripciones)'], ['no', 'Desactivada (no se evalúa)']], regla.enabled ? 'si' : 'no');
    const texto = input('text', regla.text, { maxlength: 2000 });
    const guia = textarea(regla.auditor_guidance ?? '', 2, { maxlength: 2000, placeholder: 'Ej.: Si el encuestador menciona al INE al presentarse, cuenta como haber mencionado a la institución.' });
    const preguntas = regla.questions.map(q => {
      const inst = textarea(q.instructions, 2, { maxlength: 2000 });
      const crit = Object.entries(q.criteria).map(([k, v]) => {
        const rol = Object.entries(q.roles ?? {}).find(([, n]) => n === k)?.[0];
        const etiqueta = CRITERIOS[k] ?? (rol && CRITERIOS[rol] ? `${CRITERIOS[rol]} (${k})` : `Opción: ${k}`);
        return [k, textarea(v, 2, { maxlength: 2000 }), etiqueta] as const;
      });
      [inst, ...crit.map(c => c[1])].forEach(x => x.addEventListener('input', alCambiar));
      return { q, inst, crit };
    });
    [peso, activa].forEach(x => x.addEventListener('change', alCambiar));
    [texto, guia].forEach(x => x.addEventListener('input', alCambiar));
    const el = h('div', {},
      h('div', { class: 'campos-linea' }, field('Severidad / peso en el puntaje', peso), field('Estado en próximas evaluaciones', activa)),
      field('Enunciado de la regla ENCOVI', texto),
      field('Aclaración para próximas transcripciones (recomendado)', guia),
      h('details', {}, h('summary', { text: `Ver y reescribir las preguntas exactas que se envían a JEV (${regla.questions.length})` }),
        ...preguntas.map(({ q, inst, crit }) => h('div', { class: 'pregunta-jev' },
          h('div', { class: 'fila-chips' }, chip(q.key, 'info'), h('span', { class: 'muted', text: q.is_trigger ? 'Etapa 1 · activador condicional (sí / no)' : q.type === 'noul' ? 'Sí / no' : 'Etapa 2 · evaluación de la respuesta (opciones)' })),
          field('Instrucción que evalúa JEV', inst),
          ...crit.map(([, area, etiqueta]) => field(etiqueta, area))))));
    const datos = () => ({
      custom_text: texto.value.trim() || regla.default_text, weight: Number(peso.value), enabled: activa.value === 'si',
      auditor_guidance: guia.value.trim(),
      questions_override: Object.fromEntries(preguntas.map(({ q, inst, crit }) => [q.key, { instructions: inst.value, criteria: Object.fromEntries(crit.map(([k, area]) => [k, area.value])) }])),
    });
    return { el, datos };
  }

  function editarEvaluacion(id: string) {
    const t = actual; const ev = t?.evaluation;
    const regla = reglas.find(r => r.id === id);
    const ins = ev?.instructions.find(i => i.id === id);
    if (!t || !ev || !regla || !ins) { msg.show('No se encontró la definición de esta regla. Recarga la página e inténtalo de nuevo.', true); return; }
    const local = notice();
    let estadoSel = ins.manual_override && ['followed', 'broken', 'unknown', 'custom'].includes(ins.manual_override.status) ? ins.manual_override.status : 'keep';
    const pc = input('number', String(Math.round(ins.p_followed * 100)), { min: 0, max: 100 });
    const pi = input('number', String(Math.round(ins.p_broken * 100)), { min: 0, max: 100 });
    const pn = input('number', String(Math.round(ins.p_unknown * 100)), { min: 0, max: 100 });
    const personalizados = h('div', { class: 'campos-linea' }, field('Cumplida (%)', pc), field('Incumplida (%)', pi), field('No aplica (%)', pn));
    const opciones = h('div', { class: 'pestanas' });
    const pintarOpciones = () => {
      personalizados.hidden = estadoSel !== 'custom';
      fill(opciones, ...([['keep', 'Mantener'], ['followed', '✓ Cumplida'], ['broken', '✕ Incumplida'], ['unknown', '— No aplica / sin evidencia'], ['custom', '% Personalizado'],
        ...(ins.manual_override ? [['reset', '↺ Restaurar resultado de JEV']] : [])] as [string, string][]).map(([k, l]) => {
        const b = h('button', { type: 'button', class: 'pestana', text: l, 'aria-selected': k === estadoSel ? 'true' : 'false' });
        b.addEventListener('click', () => { estadoSel = k; pintarOpciones(); });
        return b;
      }));
    };
    pintarOpciones();
    const comentario = textarea(ins.manual_override?.comment ?? '', 2, { maxlength: 2000, placeholder: 'Ej.: El encuestador sí aclaró la confidencialidad en el minuto 00:45.' });
    const ventana = ins.windows && ins.windows.length > 1
      ? select(ins.windows.map(w => [String(w.window), `Ventana ${w.window + 1} (I: ${pct(w.broken)} · C: ${pct(w.followed)}${w.p_trigger != null ? ` · activador: ${pct(w.p_trigger)}` : ''})`] as [string, string]), String(ins.worst_window?.window ?? ins.windows[0].window))
      : null;
    const futuro = input('checkbox'); futuro.checked = regla.is_customized;
    const form = formularioRegla(regla, () => { futuro.checked = true; });
    const guardar = async (reevaluar: boolean) => {
      const total = Number(pc.value) + Number(pi.value) + Number(pn.value) || 100;
      const conRegla = futuro.checked || reevaluar;
      const resp = await api<{ job: Trabajo }>(`jobs/${encodeURIComponent(t.job_id)}/evaluation/rules/${encodeURIComponent(id)}`, 'PATCH', {
        override_status: estadoSel,
        custom_probs: estadoSel === 'custom' ? { p_followed: Number(pc.value) / total, p_broken: Number(pi.value) / total, p_unknown: Number(pn.value) / total } : null,
        auditor_comment: comentario.value, window_index: ventana ? Number(ventana.value) : (ins.worst_window?.window ?? ins.windows?.[0]?.window ?? 0),
        update_future_rule: conRegla, rule_override: conRegla ? form.datos() : null,
      });
      actual = resp.job;
      if (reevaluar) actual = await api<Trabajo>(`jobs/${encodeURIComponent(t.job_id)}/evaluate`, 'POST', { speaker_map: roles, first_contact: primeraVisita, mock: false }, 300_000);
      m.cerrar(); pintar(); void refrescar();
      msg.show(reevaluar ? 'Cambios guardados y entrevista evaluada de nuevo.' : 'Evaluación corregida.');
    };
    const bGuardar = button('Guardar cambios', () => run(bGuardar, local, () => guardar(false)), 'primary');
    const bReevaluar = button('Guardar criterio y volver a evaluar', () => run(bReevaluar, local, () => guardar(true)));
    const m = modal(`Editar evaluación · ${id}`,
      h('p', { class: 'muted', text: `Sección ${regla.section}${regla.pages ? ` · Manual ${regla.pages}` : ''} · ${regla.text}` }),
      h('h3', { text: '1. Corregir el resultado en esta entrevista' }),
      h('p', { class: 'muted', text: `Resultado actual: cumplida ${pct(ins.p_followed)} · incumplida ${pct(ins.p_broken)} · no aplica ${pct(ins.p_unknown)}${ins.original_outcome && ins.manual_override ? ` (JEV original: incumplida ${pct(ins.original_outcome.p_broken)})` : ''}` }),
      opciones, personalizados,
      field('Nota o justificación del auditor (opcional)', comentario),
      ventana ? field('Ventana de referencia para la calibración', ventana) : null,
      h('p', { class: 'muted', text: 'Al marcar cumplida, incumplida o no aplica en evaluaciones reales se guarda la probabilidad que dio JEV para mejorar la calibración (se activa con unas 30 correcciones por tipo de regla).' }),
      h('h3', { text: '2. Reescribir el criterio para próximas transcripciones' }),
      h('label', { class: 'check' }, futuro, 'Guardar este criterio para las próximas transcripciones'),
      form.el, local,
      h('div', { class: 'form-actions' }, bGuardar, bReevaluar));
  }

  function editarRegla(regla: Regla, alGuardar: () => void) {
    const local = notice();
    const form = formularioRegla(regla, () => undefined);
    const bGuardar = button('Guardar criterio', () => run(bGuardar, local, async () => {
      await api(`rules/${encodeURIComponent(regla.id)}`, 'PUT', form.datos());
      m.cerrar(); await refrescar(); alGuardar(); msg.show('Criterio guardado. Se aplicará en las próximas evaluaciones.');
    }), 'primary');
    const bRestaurar: HTMLButtonElement | null = regla.is_customized ? button('Restaurar criterio original', () => run(bRestaurar, local, async () => {
      if (!confirmar('¿Restaurar el criterio original de ENCOVI para esta regla?')) return;
      await api(`rules/${encodeURIComponent(regla.id)}/override`, 'DELETE');
      m.cerrar(); await refrescar(); alGuardar(); msg.show('Se restauró el criterio original.');
    })) : null;
    const m = modal(`Criterio de evaluación · ${regla.id}`,
      h('p', { class: 'muted', text: `Sección ${regla.section} · ${regla.section_title}${regla.pages ? ` · Manual ${regla.pages}` : ''}` }),
      form.el, local, h('div', { class: 'form-actions' }, bGuardar, bRestaurar));
  }

  function abrirCatalogo() {
    let seccion = 'ALL', soloEditadas = false, q = '';
    const cuerpo = h('tbody');
    const pintarLista = () => fill(cuerpo, ...reglas.filter(r => (seccion === 'ALL' || r.section === seccion) && (!soloEditadas || r.is_customized)
      && (!q || `${r.id} ${r.text} ${r.auditor_guidance}`.toLowerCase().includes(q))).map(r => h('tr', {},
      h('td', {}, chip(r.id, 'info'), ' ', r.text, r.auditor_guidance ? h('p', { class: 'nota-auditor', text: `Aclaración: ${r.auditor_guidance}` }) : null),
      h('td', { text: TIPOS[r.kind] ?? r.kind }), h('td', { text: String(r.weight) }),
      h('td', {}, !r.enabled ? chip('Desactivada', 'neutral') : r.is_customized ? chip('Reescrita', 'info') : chip('Original', 'ok')),
      h('td', {}, button('Editar', () => { m.cerrar(); editarRegla(r, () => abrirCatalogo()); }, 'secondary')))));
    const sel = select([['ALL', 'Todas las secciones'], ...[...new Set(reglas.map(r => r.section))].map(s => [s, `${s} · ${reglas.find(r => r.section === s)?.section_title ?? ''}`] as [string, string])]);
    sel.addEventListener('change', () => { seccion = sel.value; pintarLista(); });
    const buscar = input('search', '', { placeholder: 'Buscar por código o texto…' });
    buscar.addEventListener('input', () => { q = buscar.value.trim().toLowerCase(); pintarLista(); });
    const edit = input('checkbox'); edit.addEventListener('change', () => { soloEditadas = edit.checked; pintarLista(); });
    pintarLista();
    const m = modal(`Reglas de evaluación ENCOVI (${reglas.length})`,
      h('p', { class: 'muted', text: 'Puedes ajustar el texto, el peso o las preguntas que se envían a JEV. Los cambios se aplican en las próximas evaluaciones.' }),
      h('div', { class: 'campos-linea' }, field('Sección', sel), field('Buscar', buscar)), h('label', { class: 'check' }, edit, 'Solo reglas reescritas'),
      h('div', { class: 'tabla-scroll' }, h('table', { class: 'tabla-jev' }, h('thead', {}, h('tr', {}, ...['Regla', 'Tipo', 'Peso', 'Estado', ''].map(x => h('th', { scope: 'col', text: x })))), cuerpo)));
  }

  function abrirCalibracion() {
    const local = notice();
    const cuerpo = h('tbody');
    const resumen = h('p', { class: 'muted' });
    const pintarTabla = () => {
      const c = calibracion; const min = c?.min_labels ?? 30; const grupos = c?.groups ?? {};
      resumen.textContent = `${c?.is_calibrated ? 'Calibración activa' : 'Sin calibrar todavía'} · modelo ${c?.model_version ?? estado?.jev_model ?? ''} · ${c?.total_labels ?? 0} correcciones válidas`;
      fill(cuerpo, ...[...new Set([...Object.keys(GRUPOS), ...Object.keys(grupos)])].map(k => {
        const g = grupos[k]; const n = g?.n ?? 0;
        const detalle = g?.fitted ? g.temperature != null ? `T = ${g.temperature} · precisión ${g.accuracy != null ? pct(g.accuracy) : '—'}`
          : `a = ${g.a}, b = ${g.b} · Brier ${g.brier_raw} → ${g.brier_cal_in_sample} · ECE ${g.ece_raw} → ${g.ece_cal_in_sample}`
          : g && n > 0 ? g.positives != null ? `${g.positives} sí / ${g.negatives} no` : `Precisión sin calibrar: ${g.accuracy != null ? pct(g.accuracy) : '—'}` : 'Sin correcciones aún';
        return h('tr', {}, h('td', {}, h('strong', { text: GRUPOS[k] ?? k }), h('p', { class: 'muted', text: k })),
          h('td', {}, h('span', { text: `${n} / ${min}` }), h('div', { class: 'barra' }, h('div', { class: 'relleno nivel-ok', style: `width:${Math.min(100, Math.round(n / min * 100))}%` }))),
          h('td', {}, g?.fitted ? chip('Calibrado', 'ok') : chip(`Faltan ${Math.max(0, min - n)}`, 'neutral')),
          h('td', { class: 'muted', text: detalle }));
      }));
    };
    pintarTabla();
    const recalibrar = button('Recalibrar ahora', () => run(recalibrar, local, async () => {
      calibracion = await api<Calibracion>('calibration/fit', 'POST', {});
      pintarTabla(); pintarPanel();
      return 'Calibración actualizada.';
    }), 'primary');
    modal('Calibración con las correcciones del supervisor',
      h('p', { text: 'Cada vez que corriges una evaluación real (cumplida, incumplida o no aplica) se guarda la probabilidad que dio JEV. Con al menos 30 correcciones por tipo de regla se ajusta la calibración y se aplica en las siguientes entrevistas.' }),
      resumen, h('div', { class: 'tabla-scroll' }, h('table', { class: 'tabla-jev' }, h('thead', {}, h('tr', {}, ...['Tipo de regla', 'Correcciones', 'Estado', 'Parámetros'].map(x => h('th', { scope: 'col', text: x })))), cuerpo)),
      local, h('div', { class: 'form-actions' }, recalibrar));
  }

  // Carga inicial cuando la página se muestra por primera vez
  let iniciado = false;
  const iniciar = () => { if (!iniciado && !pagina.hidden && !document.getElementById('app')?.hidden) { iniciado = true; void refrescar(); } };
  new MutationObserver(iniciar).observe(pagina, { attributes: true, attributeFilter: ['hidden'] });
  const app = document.getElementById('app');
  if (app) new MutationObserver(iniciar).observe(app, { attributes: true, attributeFilter: ['hidden'] });
  iniciar();

  return {
    abrir: async (jobId: string, audioLocal?: string) => {
      try { await abrir(jobId, audioLocal); await refrescar(); }
      catch (error) { msg.show(error instanceof ApiError ? error.message : errorText(error), true); }
    },
  };
}
