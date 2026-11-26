/** Quality Improvement: recomendaciones a partir de Data Audit y manual institucional en PDF. */
import { api, button, card, chip, confirmar, errorText, fecha, fetchBlob, field, h, input, notice, run, saveBlob, select, tabs, textarea } from './ui';

type Evidencia = { columna: string | null; hoja: string | null; n: number; porcentaje: number | null; mensaje: string; filas: number[] };
type Rec = {
  id: string; institucion: string; institucion_nombre: string; base: string; base_nombre: string; periodo: string;
  regla: string; regla_nombre: string; prioridad: 'alta' | 'media' | 'baja'; afectados: number; total_registros: number | null;
  titulo: string; que_ocurrio: string; por_que: string; como_corregir: string; como_prevenir: string; acciones: string[];
  evidencia: { hallazgos: Evidencia[]; archivo: string | null }; generado_por: 'ia' | 'reglas'; estado: 'borrador' | 'aprobada';
  aprobacion: { cargo: string; por: string; en: string } | null; historial: { en: string; por: string; accion: string }[];
};
type Seccion = Pick<Rec, 'id' | 'titulo' | 'que_ocurrio' | 'por_que' | 'como_corregir' | 'como_prevenir' | 'acciones' | 'base_nombre' | 'periodo' | 'prioridad'>;
type Manual = {
  id: string; institucion: string; institucion_nombre: string; titulo: string; introduccion: string; cierre: string;
  secciones: Seccion[]; estado: 'borrador' | 'final'; version: number; creado_en: string; finalizacion: { cargo: string; en: string } | null;
};
type Institucion = { clave: string; nombre: string };

const TEXTOS: [keyof Rec & keyof Seccion, string][] = [
  ['que_ocurrio', 'Qué ocurrió'], ['por_que', 'Por qué es un problema'], ['como_corregir', 'Cómo corregirlo'], ['como_prevenir', 'Cómo prevenirlo']];
const PRIORIDAD = { alta: ['Prioridad alta', 'bad'], media: ['Prioridad media', 'warn'], baja: ['Prioridad baja', 'info'] } as const;

export function mountImprovement(page: HTMLElement): void {
  const msg = notice();
  const body = h('div');
  let vista: 'recomendaciones' | 'manual' = 'recomendaciones';
  let instituciones: Institucion[] = [];
  let filtro = '';
  const header = h('div');
  page.append(
    h('p', { class: 'eyebrow', text: 'QUALITY AUDIT / MEJORA INSTITUCIONAL' }),
    h('h1', { id: 'mejoraTitle', tabindex: -1, text: 'Quality Improvement' }),
    h('p', { class: 'lead', text: 'Convierte los hallazgos de Data Audit en recomendaciones claras para cada institución y en un manual listo para compartir.' }),
    header, msg, body);

  function cambiar(v: typeof vista) { vista = v; msg.show(''); void pintar(); }
  async function cargarInstituciones() {
    if (!instituciones.length) instituciones = await api<Institucion[]>('improvement/institutions');
  }

  async function pintar() {
    header.replaceChildren(tabs([['recomendaciones', '1. Recomendaciones'], ['manual', '2. Manual institucional']], k => cambiar(k as typeof vista), vista));
    body.replaceChildren(h('p', { class: 'muted', text: 'Cargando…' }));
    try {
      await cargarInstituciones();
      if (vista === 'recomendaciones') await pintarRecomendaciones(); else await pintarManuales();
    } catch (error) { body.replaceChildren(); msg.show(errorText(error), true); }
  }

  // -------------------------------------------------------------------------
  // Recomendaciones
  // -------------------------------------------------------------------------
  async function pintarRecomendaciones() {
    const archivo = input('file', '', { accept: '.json,application/json' });
    const inst = select([['', 'Detectar automáticamente'], ...instituciones.map(i => [i.clave, i.nombre] as [string, string])]);
    const generar = button('Generar recomendaciones', () => run(generar, msg, async () => {
      const f = archivo.files?.[0];
      if (!f) throw new Error('Selecciona el reporte JSON de Data Audit.');
      if (f.size > 15 * 1024 * 1024) throw new Error('El archivo es demasiado grande para ser un reporte de Data Audit.');
      let report: unknown;
      try { report = JSON.parse(await f.text()); } catch { throw new Error('El archivo no es un JSON válido. Descárgalo de nuevo desde Data Audit.'); }
      msg.show('Analizando los hallazgos del reporte… puede tardar hasta un minuto.');
      const r = await api<{ institucion: string; periodo: string; nuevas: number; actualizadas: number; con_ia: boolean }>(
        'improvement/reports', 'POST', { report, institucion: inst.value || null, archivo: f.name }, 300_000);
      filtro = r.institucion; archivo.value = '';
      await pintarRecomendaciones();
      return `Listo: ${r.nuevas} recomendaciones nuevas${r.actualizadas ? ` y ${r.actualizadas} actualizadas` : ''} para ${r.institucion} · ${r.periodo}.` +
        (r.con_ia ? '' : ' (Se usaron las explicaciones estándar de cada regla.)');
    }), 'primary');
    const subir = card('Subir reporte de Data Audit',
      h('p', { text: 'Al terminar una auditoría en Data Audit, usa «Descargar reporte JSON» y sube ese archivo aquí. Los hallazgos se agrupan por institución, base, período y regla de calidad, y cada grupo genera una recomendación.' }),
      h('div', { class: 'fields' }, field('Reporte de Data Audit (.json)', archivo), field('Institución', inst, 'Se identifica por la base del reporte; cámbiala solo si no se detecta.')),
      h('div', { class: 'form-actions' }, generar));

    const recs = await api<Rec[]>('improvement/recommendations');
    const filtroSel = select([['', 'Todas las instituciones'], ...instituciones.map(i => [i.clave, i.nombre] as [string, string])], filtro);
    filtroSel.addEventListener('change', () => { filtro = filtroSel.value; void pintarRecomendaciones(); });
    const visibles = recs.filter(r => !filtro || r.institucion === filtro);
    const lista = h('div');
    if (!visibles.length) lista.append(h('p', { class: 'empty', text: 'Todavía no hay recomendaciones. Sube un reporte de Data Audit para empezar.' }));
    const grupos = new Map<string, Rec[]>();
    for (const r of visibles) {
      const clave = `${r.institucion_nombre} · ${r.base_nombre} · ${r.periodo}`;
      grupos.set(clave, [...(grupos.get(clave) ?? []), r]);
    }
    for (const [titulo, items] of grupos) {
      const aprobadas = items.filter(r => r.estado === 'aprobada').length;
      lista.append(h('div', { class: 'grupo-titulo' }, h('h3', { text: titulo }), chip(`${aprobadas} de ${items.length} aprobadas`, aprobadas === items.length ? 'ok' : 'neutral')));
      for (const r of items) lista.append(tarjetaRecomendacion(r));
    }
    body.replaceChildren(subir, card(undefined,
      h('div', { class: 'card-heading' }, h('h2', { text: 'Recomendaciones' }), h('div', { class: 'filtro' }, field('Mostrar', filtroSel))),
      h('p', { class: 'muted', text: 'Revisa cada recomendación, ajusta el texto o las acciones si hace falta y apruébala indicando tu cargo. Solo las recomendaciones aprobadas forman parte del manual.' }),
      lista));
  }

  function tarjetaRecomendacion(r: Rec): HTMLElement {
    const box = h('article', { class: 'recomendacion' });
    const local = notice();
    const pintarLectura = () => {
      const [pTexto, pTono] = PRIORIDAD[r.prioridad];
      const estado = r.estado === 'aprobada' && r.aprobacion ? chip(`Aprobada · ${r.aprobacion.cargo}`, 'ok') : chip('Pendiente de aprobar', 'warn');
      const evidencia = h('details', { class: 'evidencia' }, h('summary', { text: `Evidencia de la auditoría (${r.evidencia.hallazgos.length} ${r.evidencia.hallazgos.length === 1 ? 'caso' : 'casos'})` }), tablaEvidencia(r));
      const historial = h('details', { class: 'historial' }, h('summary', { text: 'Historial de cambios' }),
        h('ul', {}, ...r.historial.slice().reverse().map(x => h('li', { text: `${fecha(x.en)} · ${x.por}: ${x.accion}` }))));
      const aprobar = h('div', { class: 'aprobar', hidden: true });
      const cargo = input('text', '', { placeholder: 'Ej.: Jefa de la Unidad de Calidad de Datos', maxlength: 150 });
      const confirmarBtn = button('Confirmar aprobación', () => run(confirmarBtn, local, async () => {
        if (cargo.value.trim().length < 2) throw new Error('Escribe tu cargo para registrar la aprobación.');
        Object.assign(r, await api<Rec>(`improvement/recommendations/${r.id}/approve`, 'POST', { cargo: cargo.value.trim() }));
        pintarLectura(); local.show('Recomendación aprobada.');
      }), 'primary');
      aprobar.append(field('Tu cargo', cargo, 'Se registra junto con tu correo y la fecha.'), h('div', { class: 'form-actions' }, confirmarBtn, button('Cancelar', () => { aprobar.hidden = true; })));
      const acciones = h('div', { class: 'form-actions' },
        button('Editar', () => pintarEdicion()),
        r.estado !== 'aprobada' ? button('Aprobar', () => { aprobar.hidden = false; cargo.focus(); }, 'primary') : null,
        button('Descartar', async () => {
          if (!confirmar('¿Descartar esta recomendación? No aparecerá en el manual.')) return;
          await run(null, local, async () => { await api(`improvement/recommendations/${r.id}/discard`, 'POST'); box.remove(); });
        }, 'link'));
      box.replaceChildren(
        h('div', { class: 'rec-cabecera' }, chip(pTexto, pTono), estado, r.generado_por === 'ia' ? chip('Redactada con IA', 'info') : null),
        h('h3', { text: r.titulo }),
        h('p', { class: 'muted', text: `Regla: ${r.regla_nombre} · ${r.afectados.toLocaleString('es-GT')} registros afectados${r.total_registros ? ` de ${r.total_registros.toLocaleString('es-GT')}` : ''}` }),
        ...TEXTOS.map(([k, t]) => h('div', { class: 'rec-bloque' }, h('h4', { text: t }), h('p', { text: String(r[k]) }))),
        h('div', { class: 'rec-bloque' }, h('h4', { text: 'Acciones de mejora' }), h('ol', {}, ...r.acciones.map(a => h('li', { text: a })))),
        evidencia, acciones, aprobar, local, historial);
    };
    const pintarEdicion = () => {
      const titulo = input('text', r.titulo, { maxlength: 200 });
      const campos = TEXTOS.map(([k, t]) => [k, textarea(String(r[k]), 3, { maxlength: 4000 }), t] as const);
      const acciones = listaEditable(r.acciones, 'Acción de mejora');
      const guardar = button('Guardar cambios', () => run(guardar, local, async () => {
        const datos = { titulo: titulo.value.trim(), acciones: acciones.valores(), ...Object.fromEntries(campos.map(([k, el]) => [k, el.value.trim()])) };
        if (datos.titulo.length < 3 || campos.some(([, el]) => el.value.trim().length < 3)) throw new Error('Completa el título y todos los textos.');
        if (!datos.acciones.length) throw new Error('Escribe al menos una acción de mejora.');
        const antes = r.estado;
        Object.assign(r, await api<Rec>(`improvement/recommendations/${r.id}`, 'PATCH', datos));
        pintarLectura();
        local.show(antes === 'aprobada' && r.estado !== 'aprobada' ? 'Cambios guardados. Como la recomendación cambió, necesita aprobarse de nuevo.' : 'Cambios guardados.');
      }), 'primary');
      box.replaceChildren(h('h3', { text: 'Editar recomendación' }), field('Título', titulo),
        ...campos.map(([, el, t]) => field(t, el)), field('Acciones de mejora', acciones.el, 'Cada acción en su propia línea. Puedes agregar, cambiar o quitar acciones.'),
        h('div', { class: 'form-actions' }, guardar, button('Cancelar', () => pintarLectura())), local);
      titulo.focus();
    };
    pintarLectura();
    return box;
  }

  function tablaEvidencia(r: Rec): HTMLElement {
    const filas = r.evidencia.hallazgos.map(e => h('tr', {},
      h('td', { text: e.columna ?? 'Archivo' }), h('td', { text: e.n.toLocaleString('es-GT') }),
      h('td', { text: e.porcentaje === null ? '—' : `${e.porcentaje.toFixed(1)} %` }),
      h('td', { text: e.filas.length ? e.filas.join(', ') : '—' }), h('td', { text: e.mensaje })));
    return h('div', { class: 'table-wrap' }, h('table', { class: 'tabla-simple' },
      h('thead', {}, h('tr', {}, ...['Columna', 'Registros', '%', 'Filas de ejemplo', 'Detalle'].map(t => h('th', { text: t })))),
      h('tbody', {}, ...filas)),
      h('p', { class: 'muted', text: r.evidencia.archivo ? `Fuente: ${r.evidencia.archivo}` : '' }));
  }

  // -------------------------------------------------------------------------
  // Manual
  // -------------------------------------------------------------------------
  async function pintarManuales(abrir?: string) {
    const recs = await api<Rec[]>('improvement/recommendations');
    const inst = select(instituciones.map(i => [i.clave, i.nombre] as [string, string]), filtro || instituciones[0]?.clave);
    const resumen = h('p', { class: 'muted' });
    const actualizar = () => {
      const de = recs.filter(r => r.institucion === inst.value);
      const ok = de.filter(r => r.estado === 'aprobada').length;
      resumen.textContent = ok ? `${ok} de ${de.length} recomendaciones aprobadas se incluirán en el manual.`
        : de.length ? `Hay ${de.length} recomendaciones, pero ninguna aprobada. Apruébalas en «Recomendaciones» para crear el manual.`
        : 'Esta institución todavía no tiene recomendaciones.';
      crear.disabled = !ok;
    };
    const crear = button('Crear manual', () => run(crear, msg, async () => {
      const m = await api<Manual>('improvement/manuals', 'POST', { institucion: inst.value });
      await pintarManuales(m.id);
      return 'Manual creado. Revisa y ajusta su contenido antes de finalizarlo.';
    }), 'primary');
    inst.addEventListener('change', () => { filtro = inst.value; actualizar(); void listar(); });
    const listado = h('div');
    const editor = h('div');
    async function listar() {
      const manuales = await api<Manual[]>(`improvement/manuals?institucion=${encodeURIComponent(inst.value)}`);
      listado.replaceChildren(manuales.length ? h('div', { class: 'lista' }, ...manuales.map(m => h('div', { class: 'fila' },
        h('div', {}, h('strong', { text: `${m.titulo} · versión ${m.version}` }), h('p', { class: 'muted', text: `${m.institucion_nombre} · ${m.secciones.length} ${m.secciones.length === 1 ? 'recomendación' : 'recomendaciones'} · ${fecha(m.creado_en)}` })),
        h('div', { class: 'fila-acciones' }, m.estado === 'final' ? chip(`Final · ${m.finalizacion?.cargo ?? ''}`, 'ok') : chip('Borrador', 'warn'),
          button(m.estado === 'final' ? 'Ver' : 'Revisar y editar', () => abrirManual(m.id)))))) : h('p', { class: 'empty', text: 'Todavía no hay manuales para esta institución.' }));
    }
    async function abrirManual(id: string) {
      const m = await api<Manual>(`improvement/manuals/${id}`);
      editor.replaceChildren(editorManual(m, () => { void listar(); }));
      editor.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    body.replaceChildren(card('Crear manual institucional',
      h('p', { text: 'El manual reúne las recomendaciones aprobadas de una institución: qué ocurrió, por qué importa, cómo corregirlo y cómo prevenirlo, con la evidencia de la auditoría. Podrás editar todo el contenido antes de finalizarlo y descargarlo en PDF.' }),
      field('Institución', inst), resumen, h('div', { class: 'form-actions' }, crear)),
      card('Manuales de la institución', listado), editor);
    actualizar();
    await listar();
    if (abrir) await abrirManual(abrir);
  }

  function editorManual(m: Manual, alCambiar: () => void): HTMLElement {
    const local = notice();
    const final = m.estado === 'final';
    const titulo = input('text', m.titulo, { maxlength: 200, disabled: final });
    const nombre = input('text', m.institucion_nombre, { maxlength: 200, disabled: final });
    const intro = textarea(m.introduccion, 6, { maxlength: 6000, disabled: final });
    const cierre = textarea(m.cierre, 3, { maxlength: 4000, disabled: final });
    const secciones = m.secciones.map((s, i) => {
      const t = input('text', s.titulo, { maxlength: 200, disabled: final });
      const textos = TEXTOS.map(([k, label]) => [k, textarea(String(s[k]), 3, { maxlength: 4000, disabled: final }), label] as const);
      const acciones = listaEditable(s.acciones, 'Acción de mejora', final);
      const el = h('details', { class: 'seccion-editor' }, h('summary', { text: `${i + 1}. ${s.titulo}` }),
        h('p', { class: 'muted', text: `${s.base_nombre} · ${s.periodo} · ${PRIORIDAD[s.prioridad][0]}` }),
        field('Título', t), ...textos.map(([, area, label]) => field(label, area)), field('Acciones de mejora', acciones.el));
      return { id: s.id, el, leer: () => ({ id: s.id, titulo: t.value.trim(), acciones: acciones.valores(), ...Object.fromEntries(textos.map(([k, area]) => [k, area.value.trim()])) }) };
    });
    const visor = h('div', { class: 'visor-pdf' });
    async function guardar(): Promise<void> {
      Object.assign(m, await api<Manual>(`improvement/manuals/${m.id}`, 'PATCH', {
        titulo: titulo.value.trim(), institucion_nombre: nombre.value.trim(), introduccion: intro.value.trim(), cierre: cierre.value.trim(),
        secciones: secciones.map(s => s.leer()) }));
    }
    async function verPdf(descargar: boolean) {
      if (!final) await guardar();
      const { blob, name } = await fetchBlob(`improvement/manuals/${m.id}/pdf${descargar ? '?descargar=true' : ''}`);
      if (descargar) { saveBlob(blob, name); return; }
      const url = URL.createObjectURL(blob);
      visor.replaceChildren(h('div', { class: 'card-heading' }, h('h3', { text: 'Vista previa del PDF' }),
        h('a', { class: 'button secondary', href: url, target: '_blank', rel: 'noopener', text: 'Abrir en otra pestaña' })),
        h('iframe', { src: url, title: 'Vista previa del manual en PDF', class: 'pdf-frame' }));
      visor.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    const bGuardar = button('Guardar cambios', () => run(bGuardar, local, async () => { await guardar(); alCambiar(); return 'Cambios guardados.'; }), 'primary');
    const bVer = button('Ver PDF', () => run(bVer, local, async () => { await verPdf(false); }));
    const bBajar = button('Descargar PDF', () => run(bBajar, local, async () => { await verPdf(true); }));
    const cargo = input('text', '', { placeholder: 'Ej.: Director de Calidad Estadística', maxlength: 150 });
    const bFinal = button('Finalizar manual', () => run(bFinal, local, async () => {
      if (cargo.value.trim().length < 2) throw new Error('Escribe tu cargo para finalizar el manual.');
      if (!confirmar('Al finalizar, el manual ya no se podrá editar. ¿Continuar?')) return;
      await guardar();
      Object.assign(m, await api<Manual>(`improvement/manuals/${m.id}/finalize`, 'POST', { cargo: cargo.value.trim() }));
      alCambiar();
      editorRaiz.replaceWith(editorManual(m, alCambiar));
    }), 'primary');
    const bBorrar = button('Eliminar borrador', async () => {
      if (!confirmar('¿Eliminar este borrador del manual?')) return;
      await run(null, local, async () => { await api(`improvement/manuals/${m.id}`, 'DELETE'); editorRaiz.remove(); alCambiar(); });
    }, 'link');
    const editorRaiz = card(final ? `Manual finalizado · versión ${m.version}` : `Editar manual · versión ${m.version}`,
      final ? h('p', { text: `Finalizado por ${m.finalizacion?.cargo ?? ''} el ${fecha(m.finalizacion?.en)} · Ya no se puede modificar.` })
        : h('p', { text: 'Ajusta el contenido y revisa la vista previa. Cuando esté listo, finalízalo indicando tu cargo.' }),
      field('Título del manual', titulo), field('Institución a la que va dirigido', nombre),
      field('Presentación', intro), h('h3', { text: 'Recomendaciones incluidas' }), ...secciones.map(s => s.el),
      field('Antes de cada envío (cierre)', cierre),
      h('div', { class: 'form-actions' }, final ? null : bGuardar, bVer, bBajar),
      final ? null : h('div', { class: 'finalizar' }, field('Tu cargo', cargo, 'Se registra en el manual como responsable de su aprobación.'), h('div', { class: 'form-actions' }, bFinal, bBorrar)),
      local, visor);
    return editorRaiz;
  }

  void pintar();
}

/** Lista de textos editable (una entrada por línea con botones para agregar y quitar). */
function listaEditable(valores: string[], placeholder: string, disabled = false): { el: HTMLElement; valores: () => string[] } {
  const cont = h('div', { class: 'lista-editable' });
  const filas = h('div');
  const agregar = (v = '') => {
    const campo = input('text', v, { placeholder, maxlength: 500, disabled, 'aria-label': placeholder });
    const fila: HTMLDivElement = h('div', { class: 'fila-editable' }, campo);
    if (!disabled) fila.append(button('Quitar', () => fila.remove(), 'link'));
    filas.append(fila);
    return campo;
  };
  valores.forEach(v => agregar(v));
  cont.append(filas);
  if (!disabled) cont.append(button('+ Agregar acción', () => agregar().focus(), 'link'));
  return { el: cont, valores: () => [...filas.querySelectorAll('input')].map(i => i.value.trim()).filter(Boolean) };
}
