/** Survey Audit: del cuestionario en PDF a la entrevista digital verificada contra la grabación. */
import { ApiError, add, api, button, fill, card, chip, confirmar, errorText, fecha, field, h, input, minutos, notice, pause, run, select, tabs, textarea, uploadFile } from './ui';

type Pase = { tipo: 'pregunta' | 'seccion' | 'fin'; destino?: string };
type Opcion = { code: string; label: string; pase_a?: Pase };
type Pregunta = {
  id: string; codigo?: string; section_id: string; label: string; type: Tipo; required?: boolean; options: Opcion[];
  pase_a?: Pase; instrucciones?: string; pagina?: number; constraints?: { min?: number; max?: number }; alertas?: string[];
  visible_when?: { question_id: string; operator: 'eq' | 'ne' | 'in'; value: unknown };
};
type Tipo = 'text' | 'integer' | 'decimal' | 'date' | 'single_select' | 'multi_select';
type Seccion = { id: string; label: string; scope?: 'household' | 'person'; informante?: string; instrucciones?: string };
type Schema = { schema_version: number; template_code: string; nombre?: string; version: number; sections: Seccion[]; questions: Pregunta[]; origen?: { archivo?: string; paginas?: number } };
type Template = { id: string; status: 'draft' | 'published'; revision: number; schema: Schema };
type TemplateResumen = { id: string; status: 'draft' | 'published'; nombre: string; version: number; preguntas: number; secciones: number; alertas: number; created_at: string; origen?: { archivo?: string; paginas?: number } };
type Documento = { id: string; nombre: string; archivo: string; estado: string; paginas: number | null; bloques: { desde: number; hasta: number }[]; rangos?: [number, number][]; creado_en: string };
type Turno = { id: number; speaker: string; text: string; start: number; end: number };
type Hallazgo = {
  id: string; clave: string; codigo: string; persona: number | null; pregunta: string; registrada: string; escuchada: string;
  estado: 'coincidencia' | 'discrepancia' | 'no_verificable'; explicacion: string;
  evidencia: { id: number; hablante: string; rol: string; inicio: number; fin: number; texto: string }[];
  revision: { estado: 'pendiente' | 'confirmado' | 'descartado'; justificacion: string | null; por: string | null; en: string | null };
};
type Entrevista = {
  id: string; codigo: string; nombre: string; status: 'draft' | 'submitted'; revision: number; responses: Record<string, unknown>;
  schema: Schema; created_at: string; transcripcion: { archivo: string | null; turns: Turno[]; hablantes: string[]; vinculada_en: string; job_id: string } | null;
  encuestador: string | null; hallazgos: Hallazgo[];
};
type EntrevistaResumen = { id: string; codigo: string; nombre: string; status: string; formulario: string; created_at: string; transcripcion: boolean; verificadas: number; discrepancias: number };

const TIPOS: [Tipo, string][] = [['single_select', 'Una opción de la lista'], ['multi_select', 'Varias opciones de la lista'],
  ['integer', 'Número entero'], ['decimal', 'Cantidad o monto'], ['date', 'Fecha'], ['text', 'Texto libre']];
const ESTADO_VERIF = { coincidencia: ['Coincide', 'ok'], discrepancia: ['No coincide', 'bad'], no_verificable: ['No verificable', 'neutral'] } as const;
const PARALELO = 4;

// ---------------------------------------------------------------------------
// Reglas de visibilidad (las mismas que valida el servidor)
// ---------------------------------------------------------------------------
type Instancia = { clave: string; q: Pregunta; persona: number | null };

function saltos(schema: Schema): Map<string, [string, string[] | null][]> {
  const qs = schema.questions;
  const orden = new Map(qs.map((q, i) => [q.id, i]));
  const primera = new Map<string, number>();
  qs.forEach((q, i) => { if (!primera.has(q.section_id)) primera.set(q.section_id, i); });
  const alcance = new Map(schema.sections.map(s => [s.id, s.scope ?? 'household']));
  const ocultas = new Map<string, [string, string[] | null][]>();
  const marcar = (origen: Pregunta, pase: Pase | undefined, codigos: string[] | null) => {
    if (!pase) return;
    const i = orden.get(origen.id)!;
    const j = pase.tipo === 'pregunta' ? orden.get(pase.destino ?? '') ?? i : pase.tipo === 'seccion' ? primera.get(pase.destino ?? '') ?? i : qs.length;
    for (let k = i + 1; k < Math.max(i + 1, j); k++) {
      const d = qs[k];
      if ((alcance.get(d.section_id) ?? 'household') !== (alcance.get(origen.section_id) ?? 'household')) continue;
      ocultas.set(d.id, [...(ocultas.get(d.id) ?? []), [origen.id, codigos]]);
    }
  };
  for (const q of qs) { for (const o of q.options ?? []) marcar(q, o.pase_a, [o.code]); marcar(q, q.pase_a, null); }
  return ocultas;
}

function instancias(schema: Schema, personas: number): Instancia[] {
  const scope = new Map(schema.sections.map(s => [s.id, s.scope ?? 'household']));
  const salida: Instancia[] = [];
  for (const s of schema.sections) {
    const qs = schema.questions.filter(q => q.section_id === s.id);
    if (scope.get(s.id) === 'person') { for (let p = 1; p <= personas; p++) for (const q of qs) salida.push({ clave: `${q.id}#${p}`, q, persona: p }); }
    else for (const q of qs) salida.push({ clave: q.id, q, persona: null });
  }
  return salida;
}

function visibles(schema: Schema, values: Record<string, unknown>): Set<string> {
  const personas = typeof values._personas === 'number' ? values._personas : 0;
  const ocultas = schema.schema_version === 2 ? saltos(schema) : new Map();
  const todas = instancias(schema, personas);
  const claves = new Set(todas.map(i => i.clave));
  const activas: Record<string, unknown> = {};
  const vis = new Set<string>();
  for (const { clave, q, persona } of todas) {
    const valor = (origen: string) => activas[persona && claves.has(`${origen}#${persona}`) ? `${origen}#${persona}` : origen];
    let ok = true;
    const c = q.visible_when;
    if (c) {
      const parent = valor(c.question_id);
      ok = parent !== undefined && (c.operator === 'eq' ? parent === c.value : c.operator === 'ne' ? parent !== c.value : Array.isArray(c.value) && c.value.includes(parent));
    }
    for (const [origen, codigos] of ocultas.get(q.id) ?? []) {
      const elegido = valor(origen);
      if (elegido === undefined) continue;
      const lista = Array.isArray(elegido) ? elegido : [elegido];
      if (codigos === null || lista.some(v => codigos.includes(String(v)))) ok = false;
    }
    if (ok) { vis.add(clave); if (values[clave] !== undefined && values[clave] !== '') activas[clave] = values[clave]; }
  }
  return vis;
}

function nombrePregunta(q: Pregunta): string { return `${q.codigo ? q.codigo + '. ' : ''}${q.label}`; }

// ---------------------------------------------------------------------------
export function mountSurvey(page: HTMLElement): void {
  const msg = notice();
  const header = h('div');
  const body = h('div');
  type Vista = { tipo: 'formularios' } | { tipo: 'entrevistas' } | { tipo: 'editor'; id: string } | { tipo: 'entrevista'; id: string; paso?: string };
  let vista: Vista = { tipo: 'formularios' };
  page.append(
    h('p', { class: 'eyebrow', text: 'QUALITY AUDIT / ENCUESTAS' }),
    h('h1', { id: 'encuestasTitle', tabindex: -1, text: 'Survey Audit' }),
    h('p', { class: 'lead', text: 'Convierte el cuestionario en PDF en un formulario digital, registra cada entrevista y verifícala con la grabación.' }),
    header, msg, body);

  function ir(v: Vista) { vista = v; msg.show(''); void pintar(); window.scrollTo({ top: page.offsetTop - 20 }); }
  async function pintar() {
    const principal = vista.tipo === 'entrevistas' || vista.tipo === 'entrevista' ? 'entrevistas' : 'formularios';
    header.replaceChildren(tabs([['formularios', '1. Formularios de entrevista'], ['entrevistas', '2. Entrevistas']], k => ir({ tipo: k as 'formularios' | 'entrevistas' }), principal));
    body.replaceChildren(h('p', { class: 'muted', text: 'Cargando…' }));
    try {
      if (vista.tipo === 'formularios') await pintarFormularios();
      else if (vista.tipo === 'editor') await pintarEditor(vista.id);
      else if (vista.tipo === 'entrevistas') await pintarEntrevistas();
      else await pintarEntrevista(vista.id, vista.paso);
    } catch (error) { body.replaceChildren(); msg.show(errorText(error), true); }
  }

  // -------------------------------------------------------------------------
  // 1. Formularios: subir PDF y generar
  // -------------------------------------------------------------------------
  async function leerDocumento(doc: Documento, progreso: (texto: string, pct: number) => void, senal: { detenido: boolean }): Promise<Template> {
    const total = doc.paginas ?? 0;
    const leidas = new Set<number>();
    for (const [d, hasta] of doc.rangos ?? []) for (let p = d; p <= hasta; p++) leidas.add(p);
    const cola = doc.bloques.filter(b => !Array.from({ length: b.hasta - b.desde + 1 }, (_, i) => b.desde + i).every(p => leidas.has(p)));
    const avisar = () => progreso(`Leyendo el cuestionario: ${leidas.size} de ${total} páginas listas…`, total ? leidas.size / total * 100 : 0);
    avisar();
    let fallo: Error | null = null;
    const trabajador = async () => {
      while (cola.length && !fallo && !senal.detenido) {
        const b = cola.shift()!;
        for (let intento = 0; ; intento++) {
          try {
            await api(`surveys/documents/${doc.id}/leer`, 'POST', b, 290_000);
            for (let p = b.desde; p <= b.hasta; p++) leidas.add(p);
            avisar();
            break;
          } catch (error) {
            if (error instanceof ApiError && error.data.dividir && b.hasta > b.desde) {
              for (let p = b.desde; p <= b.hasta; p++) cola.push({ desde: p, hasta: p });
              break;
            }
            const reintentar = error instanceof ApiError && (error.data.reintentar || error.status === 504 || error.status === 0);
            if (reintentar && intento < 6) { progreso(`Claude está ocupado; se reintentará en unos segundos (páginas ${b.desde}–${b.hasta})…`, leidas.size / total * 100); await pause(15_000 + intento * 10_000); continue; }
            fallo = error instanceof Error ? error : new Error(errorText(error));
            return;
          }
        }
      }
    };
    await Promise.all(Array.from({ length: PARALELO }, trabajador));
    if (senal.detenido) throw new Error('Se detuvo la lectura. Puedes continuarla más tarde desde la lista de cuestionarios en proceso.');
    if (fallo) throw new Error(`${errorText(fallo)} Puedes continuar la lectura desde la lista de cuestionarios en proceso.`);
    progreso('Armando el formulario con todas las preguntas…', 100);
    return api<Template>(`surveys/documents/${doc.id}/formulario`, 'POST', undefined, 120_000);
  }

  async function pintarFormularios() {
    const nombre = input('text', '', { placeholder: 'Ej.: ENCOVI 2023', maxlength: 150 });
    const pdf = input('file', '', { accept: '.pdf,application/pdf' });
    const barra = h('progress', { max: 100, value: 0, hidden: true });
    const local = notice();
    const senal = { detenido: false };
    const detener = button('Detener', () => { senal.detenido = true; }, 'link');
    detener.hidden = true;
    const generar = button('Generar formulario de entrevista', () => run(generar, local, async () => {
      const f = pdf.files?.[0];
      if (nombre.value.trim().length < 2) throw new Error('Escribe el nombre de la entrevista.');
      if (!f) throw new Error('Selecciona la entrevista en PDF.');
      if (!/\.pdf$/i.test(f.name)) throw new Error('El archivo debe ser un PDF.');
      if (f.size > 50 * 1024 * 1024) throw new Error('El PDF supera 50 MB.');
      senal.detenido = false; detener.hidden = false; barra.hidden = false;
      try {
        local.show('Subiendo el PDF…');
        const r = await api<{ documento: Documento; subida: { url: string; directa: boolean } }>('surveys/documents', 'POST', { nombre: nombre.value.trim(), archivo: f.name, tamano: f.size });
        await uploadFile(r.subida.url, f, r.subida.directa, pct => { barra.value = pct; local.show(`Subiendo el PDF… ${pct}%`); });
        local.show('Revisando el documento…');
        const doc = await api<Documento>(`surveys/documents/${r.documento.id}/preparar`, 'POST');
        const t = await leerDocumento(doc, (texto, pct) => { local.show(texto); barra.value = pct; }, senal);
        ir({ tipo: 'editor', id: t.id });
        msg.show(`Formulario generado con ${t.schema.questions.length} preguntas en ${t.schema.sections.length} secciones. Revísalo y corrige lo necesario antes de finalizarlo.`);
      } finally { detener.hidden = true; barra.hidden = true; }
    }), 'primary');

    const [formularios, documentos] = await Promise.all([api<TemplateResumen[]>('surveys/templates'), api<Documento[]>('surveys/documents')]);
    const enProceso = documentos.filter(d => d.estado !== 'listo');
    fill(body,
      card('Nueva entrevista',
        h('p', { text: 'Sube el cuestionario en PDF. Se leen todas sus páginas (también las escaneadas) y se arma un formulario con sus secciones, preguntas, opciones de respuesta, códigos, instrucciones y saltos. Un cuestionario largo puede tardar varios minutos; no cierres esta página mientras se lee.' }),
        h('div', { class: 'fields' }, field('Nombre de la entrevista', nombre), field('Entrevista en PDF', pdf, 'Hasta 50 MB.')),
        h('div', { class: 'form-actions' }, generar, detener), barra, local),
      enProceso.length ? card('Cuestionarios en proceso de lectura', h('div', { class: 'lista' }, ...enProceso.map(d => {
        const leidas = new Set<number>(); for (const [a, b] of d.rangos ?? []) for (let p = a; p <= b; p++) leidas.add(p);
        const st = notice();
        const seguir = button('Continuar lectura', () => run(seguir, st, async () => {
          const doc = d.paginas ? d : await api<Documento>(`surveys/documents/${d.id}/preparar`, 'POST');
          const t = await leerDocumento({ ...doc, rangos: d.rangos }, texto => st.show(texto), { detenido: false });
          ir({ tipo: 'editor', id: t.id });
        }));
        return h('div', { class: 'fila' }, h('div', {}, h('strong', { text: d.nombre }),
          h('p', { class: 'muted', text: `${d.archivo} · ${d.paginas ? `${leidas.size} de ${d.paginas} páginas leídas` : 'sin leer'} · ${fecha(d.creado_en)}` })), h('div', { class: 'fila-acciones' }, seguir), st);
      }))) : null,
      card('Formularios', formularios.length ? h('div', { class: 'lista' }, ...formularios.map(t => h('div', { class: 'fila' },
        h('div', {}, h('strong', { text: `${t.nombre} · versión ${t.version}` }),
          h('p', { class: 'muted', text: `${t.preguntas} preguntas en ${t.secciones} secciones${t.origen?.archivo ? ` · desde ${t.origen.archivo}` : ''} · ${fecha(t.created_at)}` })),
        h('div', { class: 'fila-acciones' },
          t.status === 'published' ? chip('Listo para entrevistas', 'ok') : chip(t.alertas ? `Borrador · ${t.alertas} por revisar` : 'Borrador', 'warn'),
          button(t.status === 'published' ? 'Ver preguntas' : 'Revisar y editar', () => ir({ tipo: 'editor', id: t.id })),
          t.status === 'published' ? button('Nueva entrevista', () => ir({ tipo: 'entrevistas' }), 'primary') : null)))) :
        h('p', { class: 'empty', text: 'Todavía no hay formularios. Sube un cuestionario en PDF para crear el primero.' })));
  }

  // -------------------------------------------------------------------------
  // Editor del formulario
  // -------------------------------------------------------------------------
  async function pintarEditor(id: string) {
    const t = await api<Template>(`surveys/templates/${id}`);
    const s = t.schema;
    const soloLectura = t.status !== 'draft';
    const local = notice();
    let soloAlertas = false;
    const dis = { disabled: soloLectura };

    const destinoOpciones = (desde: Pregunta): [string, string][] => {
      const i = s.questions.findIndex(q => q.id === desde.id);
      const indSeccion = s.sections.findIndex(x => x.id === desde.section_id);
      return [['', 'Continúa con la siguiente pregunta'],
        ...s.questions.slice(i + 1).map(q => [`pregunta:${q.id}`, `Pasa a la pregunta ${nombrePregunta(q).slice(0, 70)}`] as [string, string]),
        ...s.sections.slice(indSeccion + 1).map(x => [`seccion:${x.id}`, `Pasa a la sección ${x.label.slice(0, 70)}`] as [string, string]),
        ['fin', 'Termina la entrevista']];
    };
    const paseValor = (p?: Pase) => !p ? '' : p.tipo === 'fin' ? 'fin' : `${p.tipo}:${p.destino}`;
    const paseDe = (v: string): Pase | undefined => !v ? undefined : v === 'fin' ? { tipo: 'fin' } : { tipo: v.split(':')[0] as Pase['tipo'], destino: v.split(':')[1] };
    /** Selector de salto que carga sus opciones solo al abrirlo (los cuestionarios largos tienen cientos de preguntas). */
    const selectorSalto = (q: Pregunta, actual: Pase | undefined, alCambiar: (p: Pase | undefined) => void) => {
      const sel = h('select', { disabled: soloLectura, 'aria-label': 'Salto' });
      const etiqueta = actual ? destinoOpciones(q).find(([v]) => v === paseValor(actual))?.[1] ?? 'Salto' : 'Continúa con la siguiente pregunta';
      sel.add(new Option(etiqueta, paseValor(actual), true, true));
      let cargado = false;
      const cargar = () => { if (cargado) return; cargado = true; const v = sel.value; sel.replaceChildren(); for (const [val, l] of destinoOpciones(q)) sel.add(new Option(l, val, false, val === v)); };
      sel.addEventListener('focus', cargar); sel.addEventListener('mousedown', cargar);
      sel.addEventListener('change', () => alCambiar(paseDe(sel.value)));
      return sel;
    };

    const editorPregunta = (q: Pregunta, alBorrar: () => void): HTMLElement => {
      const caja = h('article', { class: `pregunta-editor${q.alertas?.length ? ' con-alerta' : ''}` });
      const pintarCaja = () => {
        const codigo = input('text', q.codigo ?? '', { maxlength: 40, ...dis });
        codigo.addEventListener('input', () => { q.codigo = codigo.value.trim(); });
        const texto = textarea(q.label, 2, { maxlength: 1000, ...dis });
        texto.addEventListener('input', () => { q.label = texto.value; });
        const tipo = select(TIPOS, q.type); tipo.disabled = soloLectura;
        tipo.addEventListener('change', () => { q.type = tipo.value as Tipo; if (!q.type.endsWith('select')) q.options = []; else if (!q.options.length) q.options = [{ code: '1', label: 'Opción 1' }]; pintarCaja(); });
        const req = input('checkbox', '', dis); req.checked = q.required !== false;
        req.addEventListener('change', () => { q.required = req.checked; });
        const instr = textarea(q.instrucciones ?? '', 1, { maxlength: 1000, placeholder: 'Indicaciones para el encuestador (opcional)', ...dis });
        instr.addEventListener('input', () => { q.instrucciones = instr.value; });
        const alertas = (q.alertas ?? []).length ? h('div', { class: 'alerta' }, ...(q.alertas ?? []).map(a => h('p', { text: a })),
          soloLectura ? null : button('Marcar como revisada', () => { delete q.alertas; caja.classList.remove('con-alerta'); pintarCaja(); }, 'link')) : null;
        const opciones = h('div', { class: 'opciones-editor' });
        if (q.type.endsWith('select')) {
          opciones.append(h('div', { class: 'opcion-fila encabezado' }, h('span', { text: 'Código' }), h('span', { text: 'Opción de respuesta' }), h('span', { text: 'Si eligen esta opción' }), h('span')));
          q.options.forEach((o, i) => {
            const c = input('text', o.code, { maxlength: 20, 'aria-label': 'Código', ...dis }); c.addEventListener('input', () => { o.code = c.value.trim(); });
            const l = input('text', o.label, { maxlength: 300, 'aria-label': 'Opción', ...dis }); l.addEventListener('input', () => { o.label = l.value; });
            const salto = selectorSalto(q, o.pase_a, p => { if (p) o.pase_a = p; else delete o.pase_a; });
            opciones.append(h('div', { class: 'opcion-fila' }, c, l, salto, soloLectura ? h('span') : button('Quitar', () => { q.options.splice(i, 1); pintarCaja(); }, 'link')));
          });
          if (!soloLectura) opciones.append(button('+ Agregar opción', () => { q.options.push({ code: String(q.options.length + 1), label: '' }); pintarCaja(); }, 'link'));
        }
        const numerico = q.type === 'integer' || q.type === 'decimal';
        const min = input('number', q.constraints?.min?.toString() ?? '', { 'aria-label': 'Mínimo', ...dis });
        const max = input('number', q.constraints?.max?.toString() ?? '', { 'aria-label': 'Máximo', ...dis });
        const rango = () => { const c: { min?: number; max?: number } = {}; if (min.value !== '') c.min = Number(min.value); if (max.value !== '') c.max = Number(max.value); if (Object.keys(c).length) q.constraints = c; else delete q.constraints; };
        min.addEventListener('input', rango); max.addEventListener('input', rango);
        fill(caja,
          h('div', { class: 'pregunta-cabecera' }, h('span', { class: 'fuente', text: q.pagina ? `Fuente: página ${q.pagina} del PDF` : 'Agregada a mano' }),
            soloLectura ? null : button('Eliminar pregunta', () => { if (confirmar('¿Eliminar esta pregunta?')) alBorrar(); }, 'link')),
          alertas,
          h('div', { class: 'pregunta-grid' }, field('Código', codigo), field('Pregunta', texto)),
          h('div', { class: 'pregunta-grid' }, field('Tipo de respuesta', tipo), h('label', { class: 'check' }, req, 'Respuesta obligatoria')),
          numerico ? h('div', { class: 'fields' }, field('Valor mínimo (opcional)', min), field('Valor máximo (opcional)', max)) : null,
          opciones,
          field('Después de responder', selectorSalto(q, q.pase_a, p => { if (p) q.pase_a = p; else delete q.pase_a; }), 'Úsalo si el cuestionario indica un salto para cualquier respuesta.'),
          field('Instrucciones', instr));
      };
      pintarCaja();
      return caja;
    };

    const secciones = h('div');
    const pintarSecciones = () => {
      secciones.replaceChildren();
      for (const sec of s.sections) {
        const preguntas = s.questions.filter(q => q.section_id === sec.id);
        const conAlerta = preguntas.filter(q => q.alertas?.length).length;
        if (soloAlertas && !conAlerta) continue;
        const det = h('details', { class: 'seccion-editor' }, h('summary', {},
          h('span', { text: sec.label }), h('span', { class: 'muted', text: ` · ${preguntas.length} preguntas${sec.scope === 'person' ? ' · por persona' : ''}` }),
          conAlerta ? chip(`${conAlerta} por revisar`, 'warn') : null));
        let pintada = false;
        det.addEventListener('toggle', () => {
          if (!det.open || pintada) return;
          pintada = true;
          const titulo = input('text', sec.label, { maxlength: 300, ...dis }); titulo.addEventListener('input', () => { sec.label = titulo.value; });
          const alcance = select([['household', 'Al hogar (una vez)'], ['person', 'A cada persona del hogar']], sec.scope ?? 'household'); alcance.disabled = soloLectura;
          alcance.addEventListener('change', () => { sec.scope = alcance.value as Seccion['scope']; });
          const informante = input('text', sec.informante ?? '', { maxlength: 200, placeholder: 'Ej.: Jefe(a) del hogar', ...dis }); informante.addEventListener('input', () => { sec.informante = informante.value; });
          const lista = h('div');
          const pintarLista = () => {
            lista.replaceChildren();
            for (const q of s.questions.filter(x => x.section_id === sec.id && (!soloAlertas || x.alertas?.length))) {
              lista.append(editorPregunta(q, () => {
                const i = s.questions.indexOf(q);
                const siguiente = s.questions[i + 1];
                s.questions.splice(i, 1);
                for (const otra of s.questions) for (const p of [otra.pase_a, ...otra.options.map(o => o.pase_a)]) if (p?.tipo === 'pregunta' && p.destino === q.id) p.destino = siguiente?.id;
                for (const otra of s.questions) { if (otra.pase_a?.tipo === 'pregunta' && !otra.pase_a.destino) delete otra.pase_a; for (const o of otra.options) if (o.pase_a?.tipo === 'pregunta' && !o.pase_a.destino) delete o.pase_a; }
                pintarLista();
              }));
            }
          };
          pintarLista();
          add(det, h('div', { class: 'fields' }, field('Nombre de la sección', titulo), field('Se pregunta', alcance)), field('Informante (fuente de la respuesta)', informante),
            sec.instrucciones ? h('p', { class: 'muted', text: `Instrucciones: ${sec.instrucciones}` }) : null, lista,
            soloLectura ? null : button('+ Agregar pregunta a esta sección', () => {
              const n = Math.max(0, ...s.questions.map(q => Number(q.id.replace(/\D/g, '')) || 0)) + 1;
              const ultima = s.questions.map(q => q.section_id).lastIndexOf(sec.id);
              s.questions.splice(ultima + 1, 0, { id: `q${String(n).padStart(4, '0')}`, section_id: sec.id, label: '', type: 'text', required: true, options: [] });
              pintarLista();
            }, 'link'));
        });
        secciones.append(det);
      }
    };
    pintarSecciones();

    const alertasTotales = () => s.questions.filter(q => q.alertas?.length).length;
    const resumen = h('p', { class: 'muted' });
    const actualizarResumen = () => {
      resumen.textContent = `${s.questions.length} preguntas en ${s.sections.length} secciones${s.origen?.paginas ? ` · generado desde ${s.origen.archivo} (${s.origen.paginas} páginas)` : ''}.` +
        (alertasTotales() ? ` Hay ${alertasTotales()} preguntas marcadas para revisión.` : '');
    };
    actualizarResumen();
    const filtro = input('checkbox'); filtro.addEventListener('change', () => { soloAlertas = filtro.checked; pintarSecciones(); });
    let revision = t.revision;
    const guardar = async () => {
      const vacias = s.questions.filter(q => !q.label.trim());
      if (vacias.length) throw new Error(`Hay ${vacias.length} preguntas sin texto. Escríbelo o elimínalas.`);
      const r = await api<Template>(`surveys/templates/${t.id}`, 'PATCH', { schema_data: s, revision }, 120_000);
      revision = r.revision; actualizarResumen();
    };
    const bGuardar = button('Guardar cambios', () => run(bGuardar, local, async () => { await guardar(); return 'Cambios guardados.'; }), 'primary');
    const bFinal = button('Finalizar formulario', () => run(bFinal, local, async () => {
      await guardar();
      if (alertasTotales()) throw new Error(`Antes de finalizar, revisa las ${alertasTotales()} preguntas marcadas (usa «Mostrar solo preguntas por revisar»).`);
      if (!confirmar('Al finalizar, el formulario ya no se podrá editar y quedará listo para registrar entrevistas. ¿Continuar?')) return;
      await api(`surveys/templates/${t.id}/publish`, 'POST');
      ir({ tipo: 'entrevistas' });
      msg.show('Formulario finalizado. Ya puedes registrar entrevistas con él.');
    }));
    const bBorrar = button('Eliminar borrador', async () => {
      if (!confirmar('¿Eliminar este formulario? Esta acción no se puede deshacer.')) return;
      await run(null, local, async () => { await api(`surveys/templates/${t.id}`, 'DELETE'); ir({ tipo: 'formularios' }); });
    }, 'link');
    body.replaceChildren(card(`${soloLectura ? 'Preguntas del formulario' : 'Revisar y editar el formulario'}: ${s.nombre ?? s.template_code}`,
      resumen,
      soloLectura ? h('p', { text: 'Este formulario está finalizado; sus preguntas ya no se pueden modificar.' })
        : h('p', { text: 'Revisa que las preguntas, códigos, opciones y saltos coincidan con el PDF. Abre cada sección para editarla. Los cambios se guardan al presionar «Guardar cambios».' }),
      h('label', { class: 'check' }, filtro, 'Mostrar solo preguntas por revisar'),
      secciones,
      h('div', { class: 'form-actions barra-fija' }, soloLectura ? null : bGuardar, soloLectura ? null : bFinal, button('Volver a formularios', () => ir({ tipo: 'formularios' })), soloLectura ? null : bBorrar),
      local));
  }

  // -------------------------------------------------------------------------
  // 2. Entrevistas
  // -------------------------------------------------------------------------
  async function pintarEntrevistas() {
    const [formularios, entrevistas] = await Promise.all([api<TemplateResumen[]>('surveys/templates'), api<EntrevistaResumen[]>('surveys/interviews')]);
    const listos = formularios.filter(f => f.status === 'published');
    const form = select(listos.map(f => [f.id, `${f.nombre} · versión ${f.version}`] as [string, string]));
    const nombre = input('text', '', { placeholder: 'Ej.: Hogar 15 · boleta 0234', maxlength: 150 });
    const local = notice();
    const crear = button('Crear entrevista', () => run(crear, local, async () => {
      if (!form.value) throw new Error('Primero finaliza un formulario de entrevista.');
      if (nombre.value.trim().length < 2) throw new Error('Escribe un nombre para identificar la entrevista.');
      const e = await api<Entrevista>('surveys/interviews', 'POST', { template_id: form.value, nombre: nombre.value.trim() });
      ir({ tipo: 'entrevista', id: e.id });
      msg.show(`Entrevista ${e.codigo} creada. Registra las respuestas en el formulario.`);
    }), 'primary');
    const estado = (e: EntrevistaResumen) => e.status === 'submitted' ? chip('Finalizada', 'ok') : chip('En proceso', 'warn');
    body.replaceChildren(
      card('Registrar una entrevista', listos.length ? h('div', {},
        h('p', { text: 'Elige el formulario y escribe un nombre que identifique la entrevista. Se le asignará un código único (por ejemplo, ENT-0001).' }),
        h('div', { class: 'fields' }, field('Formulario', form), field('Nombre de la entrevista', nombre)), h('div', { class: 'form-actions' }, crear), local)
        : h('p', { class: 'empty', text: 'Para registrar entrevistas primero necesitas un formulario finalizado (pestaña «Formularios de entrevista»).' })),
      card('Entrevistas registradas', entrevistas.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'tabla-simple' },
        h('thead', {}, h('tr', {}, ...['Código', 'Nombre', 'Formulario', 'Estado', 'Grabación', 'Verificación', ''].map(x => h('th', { text: x })))),
        h('tbody', {}, ...entrevistas.map(e => h('tr', {},
          h('td', {}, h('strong', { text: e.codigo })), h('td', { text: e.nombre }), h('td', { text: e.formulario }), h('td', {}, estado(e)),
          h('td', { text: e.transcripcion ? 'Vinculada' : 'Sin vincular' }),
          h('td', { text: e.verificadas ? `${e.verificadas} preguntas verificadas · ${e.discrepancias} no coinciden` : '—' }),
          h('td', {}, button('Abrir', () => ir({ tipo: 'entrevista', id: e.id })))))))) :
        h('p', { class: 'empty', text: 'Todavía no hay entrevistas registradas.' })));
  }

  async function pintarEntrevista(id: string, paso = 'respuestas') {
    const e = await api<Entrevista>(`surveys/interviews/${id}`);
    const pasos: [string, string][] = [['respuestas', '1. Respuestas'], ['grabacion', '2. Grabación'], ['verificacion', '3. Verificación con la grabación']];
    const contenido = h('div');
    body.replaceChildren(card(undefined,
      h('div', { class: 'card-heading' }, h('div', {}, h('p', { class: 'eyebrow', text: e.schema.nombre ?? e.schema.template_code }), h('h2', { text: `${e.codigo} · ${e.nombre}` })),
        e.status === 'submitted' ? chip('Finalizada', 'ok') : chip('En proceso', 'warn')),
      tabs(pasos, k => ir({ tipo: 'entrevista', id, paso: k }), paso), contenido),
      h('div', { class: 'form-actions' }, button('Volver a entrevistas', () => ir({ tipo: 'entrevistas' }))));
    if (paso === 'grabacion') pintarGrabacion(e, contenido);
    else if (paso === 'verificacion') pintarVerificacion(e, contenido);
    else pintarRespuestas(e, contenido);
  }

  // ---- Respuestas ---------------------------------------------------------
  function pintarRespuestas(e: Entrevista, cont: HTMLElement) {
    const s = e.schema;
    const values: Record<string, unknown> = structuredClone(e.responses);
    const cerrada = e.status !== 'draft';
    const local = notice();
    const errores = h('div', { class: 'errores', hidden: true });
    const conPersonas = s.sections.some(x => x.scope === 'person');
    let persona = 1;
    const envolturas = new Map<string, HTMLElement>();
    const refrescar = () => {
      const vis = visibles(s, values);
      for (const [clave, el] of envolturas) el.hidden = !vis.has(clave);
    };
    const control = (q: Pregunta, clave: string): HTMLElement => {
      const valor = values[clave];
      const cambiar = (v: unknown) => { if (v === undefined || v === '' || (Array.isArray(v) && !v.length)) delete values[clave]; else values[clave] = v; refrescar(); };
      if (q.type === 'single_select') {
        const sel = select([['', 'Selecciona una opción'], ...q.options.map(o => [o.code, `${o.code} · ${o.label}`] as [string, string])], String(valor ?? ''));
        sel.disabled = cerrada; sel.addEventListener('change', () => cambiar(sel.value || undefined)); return sel;
      }
      if (q.type === 'multi_select') {
        const elegidos = new Set(Array.isArray(valor) ? valor.map(String) : []);
        return h('div', { class: 'multi' }, ...q.options.map(o => {
          const c = input('checkbox', '', { disabled: cerrada }); c.checked = elegidos.has(o.code);
          c.addEventListener('change', () => { if (c.checked) elegidos.add(o.code); else elegidos.delete(o.code); cambiar([...elegidos]); });
          return h('label', { class: 'check' }, c, `${o.code} · ${o.label}`);
        }));
      }
      const tipo = q.type === 'integer' || q.type === 'decimal' ? 'number' : q.type === 'date' ? 'date' : 'text';
      const el = input(tipo, valor === undefined ? '' : String(valor), { disabled: cerrada, step: q.type === 'integer' ? '1' : q.type === 'decimal' ? 'any' : undefined,
        min: q.constraints?.min, max: q.constraints?.max, maxlength: tipo === 'text' ? 2000 : undefined });
      el.addEventListener('input', () => cambiar(el.value === '' ? undefined : tipo === 'number' ? Number(el.value) : el.value));
      return el;
    };
    const pregunta = (q: Pregunta, clave: string) => {
      const ctl = control(q, clave);
      ctl.id = `r-${clave.replace('#', '-')}`;
      const w = h('div', { class: 'respuesta', 'data-clave': clave },
        h('label', { for: ctl.id }, `${nombrePregunta(q)}${q.required !== false ? ' *' : ''}`),
        q.instrucciones ? h('p', { class: 'instruccion', text: q.instrucciones }) : null, ctl);
      envolturas.set(clave, w);
      return w;
    };
    const zona = h('div');
    let abiertas: Set<string> | null = null;
    const pintarZona = () => {
      // Conserva abiertas las secciones que la persona tenía abiertas.
      if (zona.childElementCount) abiertas = new Set([...zona.querySelectorAll<HTMLDetailsElement>('details[data-seccion]')].filter(d => d.open).map(d => d.dataset.seccion!));
      envolturas.clear();
      zona.replaceChildren();
      const n = typeof values._personas === 'number' ? values._personas : 0;
      for (const sec of s.sections) {
        const qs = s.questions.filter(q => q.section_id === sec.id);
        const det = h('details', { class: 'seccion-editor', 'data-seccion': sec.id, open: abiertas ? abiertas.has(sec.id) : sec === s.sections[0] },
          h('summary', {}, h('span', { text: sec.label }), sec.scope === 'person' ? h('span', { class: 'muted', text: ` · Persona ${persona}` }) : null));
        if (sec.informante) det.append(h('p', { class: 'muted', text: `Informante: ${sec.informante}` }));
        if (sec.scope === 'person') {
          if (!n) { det.append(h('p', { class: 'muted', text: 'Indica arriba cuántas personas viven en el hogar para responder esta sección.' })); zona.append(det); continue; }
          for (const q of qs) det.append(pregunta(q, `${q.id}#${persona}`));
        } else for (const q of qs) det.append(pregunta(q, q.id));
        zona.append(det);
      }
      refrescar();
    };
    const cabeceraPersonas = h('div', { class: 'fields' });
    if (conPersonas) {
      const num = input('number', String(values._personas ?? ''), { min: 0, max: 40, step: 1, disabled: cerrada });
      const sel = h('select');
      const opcionesPersona = () => { const n = typeof values._personas === 'number' ? values._personas : 0; sel.replaceChildren(...Array.from({ length: n }, (_, i) => new Option(`Persona ${i + 1}`, String(i + 1), false, i + 1 === persona))); sel.disabled = !n; };
      num.addEventListener('change', () => { const antes = values._personas; const v = Number(num.value); if (num.value !== '' && Number.isInteger(v) && v >= 0 && v <= 40) values._personas = v; else delete values._personas; if (values._personas === antes) return; persona = Math.min(persona, Math.max(1, v || 1)); opcionesPersona(); pintarZona(); });
      sel.addEventListener('change', () => { persona = Number(sel.value); pintarZona(); });
      opcionesPersona();
      cabeceraPersonas.append(field('¿Cuántas personas viven en el hogar?', num, 'Las secciones por persona se responden una vez por cada miembro.'), field('Respondiendo por', sel));
    }
    pintarZona();
    let revision = e.revision;
    const guardar = async () => { const r = await api<Entrevista>(`surveys/interviews/${e.id}`, 'PATCH', { responses: values, revision }); revision = r.revision; };
    const irA = (clave: string) => {
      const [, p] = clave.split('#');
      if (p && Number(p) !== persona) { persona = Number(p); pintarZona(); }
      const w = envolturas.get(clave) ?? zona.querySelector(`[data-clave="${clave}"]`);
      if (w) { (w.closest('details') as HTMLDetailsElement | null)?.setAttribute('open', ''); w.scrollIntoView({ behavior: 'smooth', block: 'center' }); w.classList.add('resaltar'); (w.querySelector('input,select') as HTMLElement | null)?.focus({ preventScroll: true }); }
    };
    const bGuardar = button('Guardar avance', () => run(bGuardar, local, async () => { await guardar(); return 'Avance guardado.'; }), 'primary');
    const bFinal = button('Finalizar entrevista', () => run(bFinal, local, async () => {
      await guardar();
      errores.hidden = true;
      try {
        await api(`surveys/interviews/${e.id}/submit`, 'POST');
      } catch (error) {
        if (error instanceof ApiError && Array.isArray(error.data.errores)) {
          const lista = error.data.errores as { clave: string; pregunta: string | null; mensaje: string }[];
          fill(errores, h('strong', { text: `${error.message} Revisa estas preguntas:` }),
            h('ul', {}, ...lista.slice(0, 30).map(x => h('li', {}, button(x.pregunta ?? 'Número de personas del hogar', () => irA(x.clave), 'link'), ` — ${x.mensaje}`))),
            lista.length > 30 ? h('p', { text: `…y ${lista.length - 30} más.` }) : null);
          errores.hidden = false;
          errores.scrollIntoView({ behavior: 'smooth', block: 'center' });
          return;
        }
        throw error;
      }
      ir({ tipo: 'entrevista', id: e.id, paso: 'grabacion' });
      msg.show('Entrevista finalizada. Ahora puedes vincular la grabación para verificarla.');
    }));
    add(cont,
      cerrada ? h('p', { text: 'Esta entrevista está finalizada. Sus respuestas son las oficiales y ya no se pueden modificar.' })
        : h('p', { text: 'Registra las respuestas. Las preguntas que no aplican por un salto del cuestionario se ocultan solas. Al finalizar se revisa que todo esté completo y correcto.' }),
      cabeceraPersonas, zona, errores,
      cerrada ? null : h('div', { class: 'form-actions barra-fija' }, bGuardar, bFinal), local);
  }

  // ---- Grabación ----------------------------------------------------------
  function pintarGrabacion(e: Entrevista, cont: HTMLElement) {
    const local = notice();
    const t = e.transcripcion;
    const permiso = input('checkbox');
    const archivo = input('file', '', { accept: '.json,application/json' });
    const vincular = button(t ? 'Reemplazar transcripción' : 'Vincular transcripción', () => run(vincular, local, async () => {
      if (!permiso.checked) throw new Error('Confirma que cuentas con autorización para usar la grabación.');
      const f = archivo.files?.[0];
      if (!f) throw new Error('Selecciona el archivo JSON que descargaste de Audio Audit.');
      if (f.size > 20 * 1024 * 1024) throw new Error('El archivo es demasiado grande.');
      if (t && !confirmar('Ya hay una transcripción vinculada. Si la reemplazas, se borrarán los resultados de verificación pendientes. ¿Continuar?')) return;
      let datos: unknown;
      try { datos = JSON.parse(await f.text()); } catch { throw new Error('El archivo no es un JSON válido. Descárgalo de nuevo desde Audio Audit.'); }
      await api(`surveys/interviews/${e.id}/transcripts`, 'POST', { consent: true, entrevista_codigo: e.codigo, datos, archivo: f.name });
      ir({ tipo: 'entrevista', id: e.id, paso: 'grabacion' });
      msg.show(`Transcripción vinculada a ${e.codigo}. Ahora indica quién es el encuestador.`);
    }), 'primary');
    add(cont,
      h('h3', { text: 'Vincular transcripción de la entrevista' }),
      h('p', { text: 'En Audio Audit, transcribe la grabación de esta entrevista y usa «Descargar JSON». Después súbelo aquí. Cada grabación se vincula a una sola entrevista.' }),
      h('div', { class: 'destino' }, 'Se vinculará a: ', h('strong', { text: `${e.codigo} · ${e.nombre}` })),
      t ? h('p', { class: 'muted', text: `Transcripción vinculada: ${t.archivo ?? 'archivo JSON'} · ${t.turns.length} intervenciones · ${t.hablantes.length} hablantes · ${fecha(t.vinculada_en)}` }) : null,
      field('Archivo JSON de Audio Audit', archivo),
      h('label', { class: 'check' }, permiso, 'Confirmo que cuento con autorización para usar esta grabación en la auditoría.'),
      h('div', { class: 'form-actions' }, vincular), local);
    if (!t) return;
    const ejemplos = (hablante: string) => t.turns.filter(x => x.speaker === hablante).slice(0, 2).map(x => `«${x.text.slice(0, 110)}»`).join(' ');
    const opciones = h('div', { class: 'hablantes' });
    for (const hablante of t.hablantes) {
      const r = input('radio', hablante, { name: `enc-${e.id}` }); r.checked = e.encuestador === hablante;
      opciones.append(h('label', { class: 'hablante' }, r, h('span', {}, h('strong', { text: hablante }), h('small', { text: ejemplos(hablante) }))));
    }
    const local2 = notice();
    const guardar = button('Guardar encuestador', () => run(guardar, local2, async () => {
      const elegido = opciones.querySelector<HTMLInputElement>('input:checked');
      if (!elegido) throw new Error('Elige cuál de los hablantes es el encuestador.');
      await api(`surveys/interviews/${e.id}/encuestador`, 'PATCH', { hablante: elegido.value });
      ir({ tipo: 'entrevista', id: e.id, paso: 'verificacion' });
      msg.show('Encuestador guardado. Ya puedes validar la entrevista contra la grabación.');
    }), 'primary');
    cont.append(h('h3', { text: '¿Quién es el encuestador?' }),
      h('p', { text: 'Elige el hablante que hace las preguntas. Las frases de ejemplo te ayudan a reconocerlo.' }), opciones,
      h('div', { class: 'form-actions' }, guardar), local2);
  }

  // ---- Verificación -------------------------------------------------------
  function pintarVerificacion(e: Entrevista, cont: HTMLElement) {
    const local = notice();
    const faltan = [e.status !== 'submitted' ? 'finalizar la entrevista (paso 1)' : '', !e.transcripcion ? 'vincular la transcripción (paso 2)' : '',
      e.transcripcion && !e.encuestador ? 'indicar quién es el encuestador (paso 2)' : ''].filter(Boolean);
    cont.append(h('p', { text: 'Se compara cada respuesta registrada con lo que se escucha en la grabación, usando las marcas de tiempo como evidencia. Las respuestas oficiales son las del formulario: la grabación no las modifica.' }));
    if (faltan.length) { cont.append(h('p', { class: 'empty', text: `Para verificar, primero debes ${faltan.join(' y ')}.` })); return; }
    const barra = h('progress', { max: 100, value: 0, hidden: true });
    const iniciar = button(e.hallazgos.length ? 'Volver a validar las pendientes' : 'Validar contra la grabación', () => run(iniciar, local, async () => {
      const prep = await api<{ lotes: number; preguntas: number; ya_revisadas: number }>(`surveys/interviews/${e.id}/verificacion`, 'POST');
      barra.hidden = false;
      for (let n = 0; n < prep.lotes; n++) {
        local.show(`Verificando ${prep.preguntas} respuestas contra la grabación… grupo ${n + 1} de ${prep.lotes}`);
        barra.value = n / prep.lotes * 100;
        for (let intento = 0; ; intento++) {
          try { await api(`surveys/interviews/${e.id}/verificacion/${n}`, 'POST', undefined, 290_000); break; }
          catch (error) {
            if (error instanceof ApiError && (error.data.reintentar || error.status === 504) && intento < 6) { local.show('Claude está ocupado; se reintentará en unos segundos…'); await pause(15_000 + intento * 10_000); continue; }
            throw error;
          }
        }
      }
      ir({ tipo: 'entrevista', id: e.id, paso: 'verificacion' });
      msg.show('Verificación terminada. Revisa los resultados, sobre todo los que no coinciden.');
    }), 'primary');
    cont.append(h('div', { class: 'form-actions' }, iniciar), barra, local);
    if (!e.hallazgos.length) return;
    const cuenta = (k: Hallazgo['estado']) => e.hallazgos.filter(x => x.estado === k).length;
    const revisadas = e.hallazgos.filter(x => x.revision.estado !== 'pendiente').length;
    const filtro = select([['todos', 'Todos los resultados'], ['discrepancia', 'No coinciden'], ['no_verificable', 'No verificables'], ['coincidencia', 'Coinciden'], ['pendiente', 'Pendientes de revisión']], 'todos');
    const lista = h('div');
    const pintarLista = () => {
      const orden = { discrepancia: 0, no_verificable: 1, coincidencia: 2 };
      const items = e.hallazgos.filter(x => filtro.value === 'todos' || x.estado === filtro.value || (filtro.value === 'pendiente' && x.revision.estado === 'pendiente'))
        .sort((a, b) => orden[a.estado] - orden[b.estado]);
      fill(lista, ...items.map(tarjetaHallazgo), items.length ? null : h('p', { class: 'empty', text: 'No hay resultados con este filtro.' }));
    };
    const tarjetaHallazgo = (x: Hallazgo): HTMLElement => {
      const [texto, tono] = ESTADO_VERIF[x.estado];
      const local2 = notice();
      const just = textarea('', 2, { maxlength: 1000, placeholder: 'Explica brevemente por qué confirmas o descartas este resultado' });
      const decidir = (estado: 'confirmado' | 'descartado') => run(null, local2, async () => {
        if (just.value.trim().length < 3) throw new Error('Escribe una justificación para registrar tu revisión.');
        x.revision = (await api<Hallazgo>(`surveys/interviews/${e.id}/findings/${x.id}`, 'PATCH', { estado, justificacion: just.value.trim() })).revision;
        caja.replaceWith(tarjetaHallazgo(x));
      });
      const caja = h('article', { class: `hallazgo ${x.estado}` },
        h('div', { class: 'rec-cabecera' }, chip(texto, tono), x.persona ? chip(`Persona ${x.persona}`, 'info') : null,
          x.revision.estado !== 'pendiente' ? chip(x.revision.estado === 'confirmado' ? 'Resultado confirmado' : 'Resultado descartado', 'neutral') : chip('Pendiente de revisión', 'warn')),
        h('h4', { text: `${x.codigo ? x.codigo + '. ' : ''}${x.pregunta}` }),
        h('div', { class: 'comparacion' },
          h('div', {}, h('small', { text: 'Respuesta registrada' }), h('p', { text: x.registrada })),
          h('div', {}, h('small', { text: 'Lo que se escucha' }), h('p', { text: x.escuchada || '—' }))),
        h('p', { text: x.explicacion }),
        x.evidencia.length ? h('details', { class: 'evidencia' }, h('summary', { text: `Evidencia en la grabación (${x.evidencia.map(v => minutos(v.inicio)).join(', ')})` }),
          ...x.evidencia.map(v => h('div', { class: 'turno' }, h('span', { class: 'time-button', text: `${minutos(v.inicio)}–${minutos(v.fin)}` }), h('strong', { text: v.rol }), h('span', { text: v.texto })))) : null,
        x.revision.estado !== 'pendiente' ? h('p', { class: 'muted', text: `Revisión: ${x.revision.justificacion} · ${x.revision.por ?? ''} · ${fecha(x.revision.en)}` })
          : h('div', { class: 'revision' }, field('Tu revisión', just), h('div', { class: 'form-actions' },
            button('Confirmar resultado', () => decidir('confirmado'), 'primary'), button('Descartar resultado', () => decidir('descartado')))),
        local2);
      return caja;
    };
    filtro.addEventListener('change', pintarLista);
    cont.append(h('div', { class: 'metrics' },
      ...([['Coinciden', cuenta('coincidencia')], ['No coinciden', cuenta('discrepancia')], ['No verificables', cuenta('no_verificable')], ['Revisadas', `${revisadas} de ${e.hallazgos.length}`]] as const)
        .map(([l, v]) => h('div', { class: 'metric' }, h('strong', { text: String(v) }), h('span', { text: l })))),
    h('div', { class: 'filtro' }, field('Mostrar', filtro)), lista);
    pintarLista();
  }

  void pintar();
}
