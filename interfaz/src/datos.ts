/**
 * Data Audit: historial de bases subidas, detalle de cada auditoría, revisión de correcciones
 * sugeridas, reproceso con las correcciones aprobadas, decisión técnica y correcciones guardadas.
 */
import { add, api, button, chip, confirmar, fecha, field, fill, h, input, notice, run, select, tabs, textarea } from './ui';
import { download } from './services/dataApi';

type Base = { codigo: string; nombre: string; institucion?: string; version?: string | null };
type Carga = {
  carga_id: string; base: string; institucion: string; anio: number; mes: number | null; estado: string; puntaje: number | null;
  creado_en: string; total_registros: number | null; registros_validos: number | null; registros_excluidos: number | null;
  sugerencias_pendientes: number | null; avance?: { etapa: string; porcentaje: number };
};
type Detalle = {
  carga_id: string; base: string; nombre_base: string; institucion: string; anio: number; mes: number | null; estado: string;
  puntaje: number | null; notas: string | null; creado_en: string; actualizado_en: string; usuario: string;
  ejecucion: { total_registros: number; registros_validos: number; registros_excluidos: number; finalizada_en: string | null } | null;
  puntajes?: Record<string, number>; hallazgos_por_severidad?: Record<string, number>; sugerencias_pendientes?: number;
  archivos?: { rol: string; nombre: string; tamano_bytes: number | null; creado_en: string }[];
  avance?: { estado: string; etapa: string; porcentaje: number; error: string | null };
};
type Hallazgo = { id: number; regla: string; nombre: string; dimension: string; severidad: string; columna: string | null; hoja: string | null; registros_afectados: number; porcentaje: number | null; mensaje: string };
type Sugerencia = {
  id: number; columna: string; valor_antes: string; valor_sugerido: string | null; registros_afectados: number; primera_fila: number | null;
  origen: string; confianza: number | null; justificacion: string | null; estado: string; regla: string; catalogo: string | null; etiqueta_sugerida: string | null;
};
type Excluido = { id: number; regla: string; nombre: string; motivo: string; hoja: string | null; registros_afectados: number; primera_fila: number | null };
type Equivalencia = { id: number; institucion: string; catalogo: string; nombre_catalogo: string; texto_origen: string; codigo: string; etiqueta: string | null; fuente: string; veces_usada: number; creado_en: string; aprobada_por: string | null };

const ESTADOS: Record<string, [string, 'ok' | 'warn' | 'bad' | 'info' | 'neutral']> = {
  recibida: ['Recibida', 'neutral'], procesando: ['Procesando', 'info'], con_observaciones: ['Con observaciones', 'warn'],
  aprobada: ['Aprobada', 'ok'], rechazada: ['Rechazada', 'bad'], error: ['Con error', 'bad'],
};
const SEVERIDAD: Record<string, [string, 'bad' | 'warn' | 'info']> = { error: ['Error', 'bad'], advertencia: ['Advertencia', 'warn'], info: ['Información', 'info'] };
const ORIGEN: Record<string, string> = { regla: 'Regla del diccionario', ia: 'Sugerida por IA', usuario: 'Usuario', manual: 'Corregida a mano', diccionario: 'Diccionario' };
const ARCHIVOS: Record<string, string> = { original: 'Archivo original', corregido: 'Base corregida', bitacora: 'Bitácora de cambios', reporte: 'Reporte JSON' };
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

const numero = (n: number | null | undefined) => n == null ? '—' : n.toLocaleString('es-GT');
const periodo = (anio: number, mes: number | null) => mes ? `${MESES[mes - 1]} ${anio}` : `Año ${anio}`;
const estadoChip = (e: string) => chip(...(ESTADOS[e] ?? [e, 'neutral']));
const tabla = (cabeza: string[], filas: Node[]) => h('div', { class: 'tabla-scroll' }, h('table', { class: 'tabla-jev' },
  h('thead', {}, h('tr', {}, ...cabeza.map(x => h('th', { scope: 'col', text: x })))), h('tbody', {}, ...filas)));

export function mountDatos(): { abrir: (cargaId: string) => Promise<void>; refrescar: () => Promise<void> } {
  const pagina = document.getElementById('datos');
  if (!pagina) throw new Error('Falta la página de Data Audit');
  document.getElementById('dataResult')?.remove();
  const msg = notice();
  const cabecera = h('div', { class: 'datos-pestanas' });
  const cuerpo = h('div');
  const detalle = h('div');
  add(pagina, msg, detalle, cabecera, cuerpo);

  let vista: 'cargas' | 'guardadas' = 'cargas';
  let bases: Base[] = [];
  let filtroBase = '', filtroEstado = '';

  const cambiar = (v: typeof vista) => { vista = v; void pintar(); };
  async function pintar() {
    fill(cabecera, tabs([['cargas', 'Bases subidas'], ['guardadas', 'Correcciones guardadas']], k => cambiar(k as typeof vista), vista));
    try {
      if (!bases.length) bases = await api<Base[]>('qa/bases').catch(() => []);
      if (vista === 'cargas') await pintarCargas(); else await pintarGuardadas();
    } catch (error) { msg.show(error instanceof Error ? error.message : 'No se pudo cargar la información.', true); }
  }

  // ---------------------------------------------------------------- Historial
  async function pintarCargas() {
    const params = new URLSearchParams({ limite: '200' });
    if (filtroBase) params.set('base', filtroBase);
    if (filtroEstado) params.set('estado', filtroEstado);
    const cargas = await api<Carga[]>(`qa/cargas?${params}`);
    const selBase = select([['', 'Todas las bases'], ...bases.map(b => [b.codigo, b.institucion ? `${b.nombre} · ${b.institucion}` : b.nombre] as [string, string])], filtroBase);
    selBase.addEventListener('change', () => { filtroBase = selBase.value; void pintar(); });
    const selEstado = select([['', 'Todos los estados'], ...Object.entries(ESTADOS).map(([k, [l]]) => [k, l] as [string, string])], filtroEstado);
    selEstado.addEventListener('change', () => { filtroEstado = selEstado.value; void pintar(); });
    const filas = cargas.map(c => h('tr', {},
      h('td', { text: fecha(c.creado_en) }),
      h('td', {}, h('strong', { text: bases.find(b => b.codigo === c.base)?.nombre ?? c.base }), h('p', { class: 'muted', text: c.institucion })),
      h('td', { text: periodo(c.anio, c.mes) }),
      h('td', {}, estadoChip(c.estado), c.avance ? h('p', { class: 'muted', text: `${c.avance.etapa} (${c.avance.porcentaje} %)` }) : null),
      h('td', { class: 'puntaje', text: c.puntaje != null ? Number(c.puntaje).toLocaleString('es-GT') : '—' }),
      h('td', { text: c.total_registros != null ? `${numero(c.registros_validos)} de ${numero(c.total_registros)}` : '—' }),
      h('td', {}, c.sugerencias_pendientes ? chip(`${c.sugerencias_pendientes} por revisar`, 'warn') : h('span', { class: 'muted', text: '—' })),
      h('td', {}, button('Abrir', () => void abrir(c.carga_id), 'secondary'))));
    fill(cuerpo, h('section', { class: 'card' },
      h('h2', { text: 'Bases subidas' }),
      h('p', { class: 'muted', text: 'Cada base que se audita queda guardada con su archivo original, sus resultados y las correcciones. Ábrela para revisar las correcciones sugeridas, aplicarlas o registrar la decisión técnica.' }),
      h('div', { class: 'campos-linea' }, field('Base', selBase), field('Estado', selEstado)),
      cargas.length ? tabla(['Fecha', 'Base', 'Período', 'Estado', 'Puntaje', 'Registros válidos', 'Correcciones', ''], filas)
        : h('p', { class: 'empty', text: 'Todavía no hay bases auditadas con estos filtros.' })));
  }

  // ---------------------------------------------------------------- Detalle de una carga
  async function abrir(cargaId: string) {
    const d = await api<Detalle>(`qa/cargas/${encodeURIComponent(cargaId)}`);
    const local = notice();
    const id = encodeURIComponent(cargaId);
    const recargar = async (aviso?: string) => { await abrir(cargaId); if (aviso) msg.show(aviso); void (vista === 'cargas' && pintar()); };
    const ej = d.ejecucion;
    const metricas = h('div', { class: 'kpis' }, ...([['Puntaje global', d.puntaje != null ? Number(d.puntaje).toLocaleString('es-GT') : '—'], ['Registros recibidos', numero(ej?.total_registros)],
      ['Válidos', numero(ej?.registros_validos)], ['Excluidos', numero(ej?.registros_excluidos)]] as const)
      .map(([t, v]) => h('div', { class: 'kpi' }, h('span', { class: 'kpi-titulo', text: t }), h('strong', { class: 'kpi-valor', text: v }))));
    const dimensiones = h('div', { class: 'secciones-jev' }, ...Object.entries(d.puntajes ?? {}).map(([k, v]) =>
      h('div', { class: 'seccion-jev' }, h('div', { class: 'seccion-jev-cabeza' }, h('h3', { text: k.replaceAll('_', ' ') }), h('strong', { text: v.toLocaleString('es-GT') })),
        h('div', { class: 'barra' }, h('div', { class: `relleno ${v >= 85 ? 'nivel-ok' : v >= 70 ? 'nivel-warn' : 'nivel-bad'}`, style: `width:${Math.max(0, Math.min(100, v))}%` })))));

    // Descargas guardadas
    const descargas = h('div', { class: 'form-actions' }, ...(d.archivos ?? []).sort((a, b) => Object.keys(ARCHIVOS).indexOf(a.rol) - Object.keys(ARCHIVOS).indexOf(b.rol)).map(a => {
      const b = button(`Descargar ${ARCHIVOS[a.rol]?.toLowerCase() ?? a.rol}`, () => run(b, local, async () => {
        if (a.rol === 'original' && !confirmar('El archivo original puede contener datos personales. La descarga queda registrada. ¿Continuar?')) return;
        await download(`/api/qa/cargas/${id}/descargar/${a.rol}`);
      }), a.rol === 'corregido' ? 'primary' : 'secondary');
      return b;
    }));

    // Hallazgos
    const hallazgosZona = h('div');
    let severidad = '';
    const pintarHallazgos = async () => {
      const lista = await api<Hallazgo[]>(`qa/cargas/${id}/hallazgos${severidad ? `?severidad=${severidad}` : ''}`);
      fill(hallazgosZona, lista.length ? tabla(['Severidad', 'Regla', 'Columna', 'Registros', 'Detalle'], lista.map(x => h('tr', {},
        h('td', {}, chip(...(SEVERIDAD[x.severidad] ?? [x.severidad, 'info']))),
        h('td', {}, h('strong', { text: x.nombre }), h('p', { class: 'muted', text: `${x.regla} · ${x.dimension}` })),
        h('td', { text: x.columna ?? '—' }),
        h('td', { text: `${numero(x.registros_afectados)}${x.porcentaje != null ? ` (${Number(x.porcentaje).toLocaleString('es-GT', { maximumFractionDigits: 1 })} %)` : ''}` }),
        h('td', { text: x.mensaje })))) : h('p', { class: 'empty', text: 'No hay hallazgos con este filtro.' }));
    };
    const selSev = select([['', 'Todas las severidades'], ['error', 'Errores'], ['advertencia', 'Advertencias'], ['info', 'Información']]);
    selSev.addEventListener('change', () => { severidad = selSev.value; void pintarHallazgos(); });

    // Correcciones sugeridas
    const sugerenciasZona = h('div');
    let estadoSug = 'pendiente';
    const pestanasSug = h('div');
    const pintarSugerencias = async () => {
      fill(pestanasSug, tabs([['pendiente', 'Por revisar'], ['aplicada', 'Aprobadas'], ['rechazada', 'Rechazadas'], ['todas', 'Todas']], k => { estadoSug = k; void pintarSugerencias(); }, estadoSug));
      const lista = await api<Sugerencia[]>(`qa/cargas/${id}/sugerencias?estado=${estadoSug}`);
      fill(sugerenciasZona, lista.length ? h('div', { class: 'lista' }, ...lista.map(tarjetaSugerencia))
        : h('p', { class: 'empty', text: estadoSug === 'pendiente' ? 'No hay correcciones por revisar.' : 'No hay correcciones en este estado.' }));
    };
    const tarjetaSugerencia = (s: Sugerencia): HTMLElement => {
      const caja = h('div', { class: 'sugerencia' });
      const aviso = notice();
      const sugerido = s.valor_sugerido ? `${s.valor_sugerido}${s.etiqueta_sugerida ? ` · ${s.etiqueta_sugerida}` : ''}` : 'Sin sugerencia: elige el código';
      const acciones = h('div', { class: 'form-actions' });
      if (s.estado === 'pendiente') {
        const aprobar = button('Aprobar', () => run(aprobar, aviso, async () => {
          await api(`qa/sugerencias/${s.id}/aprobar`, 'POST', {});
          await pintarSugerencias(); return 'Aprobada. Usa «Aplicar correcciones aprobadas» para generar la base corregida.';
        }), 'primary');
        aprobar.disabled = !s.valor_sugerido;
        const corregir = button(s.valor_sugerido ? 'Elegir otro código' : 'Elegir código', () => {
          const buscar = input('search', '', { placeholder: 'Escribe parte del nombre o el código…' });
          const opciones = select([['', 'Escribe para buscar en el catálogo']]);
          let espera = 0;
          buscar.addEventListener('input', () => {
            window.clearTimeout(espera);
            espera = window.setTimeout(async () => {
              if (!s.catalogo || buscar.value.trim().length < 2) return;
              const r = await api<{ codigo: string; etiqueta: string }[]>(`qa/catalogos/${encodeURIComponent(s.catalogo)}?q=${encodeURIComponent(buscar.value.trim())}&limite=30`).catch(() => []);
              fill(opciones, ...(r.length ? r.map(x => new Option(`${x.codigo} · ${x.etiqueta}`, x.codigo)) : [new Option('No hay coincidencias', '')]));
            }, 300);
          });
          const confirmarCodigo = button('Aprobar con este código', () => run(confirmarCodigo, aviso, async () => {
            if (!opciones.value) throw new Error('Busca y elige un código del catálogo.');
            await api(`qa/sugerencias/${s.id}/aprobar`, 'POST', { codigo: opciones.value });
            await pintarSugerencias(); return 'Corrección guardada con el código elegido.';
          }), 'primary');
          fill(acciones, h('div', { class: 'campos-linea' }, field(`Buscar en el catálogo ${s.catalogo ?? ''}`, buscar), field('Código', opciones)), confirmarCodigo,
            button('Cancelar', () => void pintarSugerencias(), 'link'));
          buscar.focus();
        });
        corregir.disabled = !s.catalogo;
        if (!s.valor_sugerido) { corregir.className = 'button primary'; aprobar.hidden = true; }
        const rechazar = button('Rechazar', () => {
          const motivo = textarea('', 2, { maxlength: 500, placeholder: 'Ej.: el texto no corresponde a ningún municipio.' });
          const confirmarRechazo = button('Confirmar rechazo', () => run(confirmarRechazo, aviso, async () => {
            await api(`qa/sugerencias/${s.id}/rechazar`, 'POST', { comentario: motivo.value.trim() || null });
            await pintarSugerencias(); return 'Sugerencia rechazada.';
          }), 'danger');
          fill(acciones, field('Motivo del rechazo (opcional)', motivo), confirmarRechazo, button('Cancelar', () => void pintarSugerencias(), 'link'));
        }, 'link');
        add(acciones, aprobar, corregir, rechazar);
      }
      add(caja,
        h('div', { class: 'fila-chips' }, chip(s.columna, 'info'), chip(s.estado === 'pendiente' ? 'Por revisar' : s.estado === 'aplicada' ? 'Aprobada' : 'Rechazada', s.estado === 'pendiente' ? 'warn' : s.estado === 'aplicada' ? 'ok' : 'neutral'),
          h('span', { class: 'muted', text: `${numero(s.registros_afectados)} ${s.registros_afectados === 1 ? 'registro' : 'registros'}${s.primera_fila ? ` · primera fila ${s.primera_fila}` : ''} · ${ORIGEN[s.origen] ?? s.origen}${s.confianza != null ? ` · confianza ${Math.round(Number(s.confianza) * 100)} %` : ''}` })),
        h('div', { class: 'cambio' }, h('div', {}, h('span', { class: 'kpi-titulo', text: 'Valor en la base' }), h('p', { text: s.valor_antes })),
          h('span', { class: 'flecha', text: '→' }), h('div', {}, h('span', { class: 'kpi-titulo', text: s.estado === 'aplicada' ? 'Código aprobado' : 'Código sugerido' }), h('p', { text: sugerido }))),
        s.justificacion ? h('p', { class: 'muted', text: s.justificacion }) : null,
        acciones, aviso);
      return caja;
    };

    const reprocesar = button('Aplicar correcciones aprobadas', () => run(reprocesar, local, async () => {
      if (!confirmar('Se volverá a validar la base con las correcciones aprobadas y se generará una nueva base corregida. ¿Continuar?')) return;
      local.show('Volviendo a validar la base… puede tardar según su tamaño.');
      await api(`qa/cargas/${id}/reprocesar`, 'POST', undefined, 600_000);
      await recargar('La base se volvió a validar con las correcciones aprobadas.');
    }), 'primary');

    // Excluidos
    const excluidos = await api<Excluido[]>(`qa/cargas/${id}/excluidos`).catch(() => [] as Excluido[]);

    // Decisión técnica
    const comentario = textarea(d.notas ?? '', 2, { maxlength: 2000, placeholder: 'Comentario de la revisión técnica (opcional)' });
    const decidir = (accion: 'aprobar' | 'rechazar') => {
      const b = button(accion === 'aprobar' ? 'Aprobar base' : 'Rechazar base', () => run(b, local, async () => {
        await api(`qa/cargas/${id}/${accion}`, 'POST', { comentario: comentario.value.trim() || null });
        await recargar(accion === 'aprobar' ? 'Base aprobada.' : 'Base rechazada.');
      }), accion === 'aprobar' ? 'primary' : 'danger');
      return b;
    };
    const decidible = ['con_observaciones', 'aprobada', 'rechazada'].includes(d.estado);

    const cerrar = button('Cerrar detalle', () => { detalle.replaceChildren(); }, 'link');
    fill(detalle, h('section', { class: 'card detalle-carga' },
      h('div', { class: 'card-heading' }, h('div', {}, h('span', { class: 'eyebrow', text: 'AUDITORÍA GUARDADA' }),
        h('div', { class: 'fila-chips' }, h('h2', { text: `${d.nombre_base} · ${periodo(d.anio, d.mes)}` }), estadoChip(d.estado))), cerrar),
      h('p', { class: 'muted', text: `${d.institucion} · subida por ${d.usuario} el ${fecha(d.creado_en)}${ej?.finalizada_en ? ` · última validación ${fecha(ej.finalizada_en)}` : ''}` }),
      d.avance?.error ? h('p', { class: 'aviso error', text: d.avance.error }) : d.estado === 'error' && d.notas ? h('p', { class: 'aviso error', text: d.notas }) : null,
      metricas, dimensiones, local,
      h('h3', { text: 'Archivos guardados' }), descargas,
      h('h3', { text: 'Correcciones sugeridas' }),
      h('p', { class: 'muted', text: 'Revisa cada valor que no coincide con el catálogo. Al aprobar, la corrección queda guardada para la institución y se aplica sola en las próximas bases. Para generar la base corregida con lo aprobado, usa «Aplicar correcciones aprobadas».' }),
      pestanasSug, sugerenciasZona, h('div', { class: 'form-actions' }, reprocesar),
      h('h3', { text: 'Hallazgos' }), field('Mostrar', selSev), hallazgosZona,
      excluidos.length ? h('details', {}, h('summary', { text: `Registros excluidos (${excluidos.reduce((a, x) => a + x.registros_afectados, 0).toLocaleString('es-GT')})` }),
        tabla(['Regla', 'Motivo', 'Registros', 'Primera fila'], excluidos.map(x => h('tr', {}, h('td', {}, h('strong', { text: x.nombre }), h('p', { class: 'muted', text: x.regla })),
          h('td', { text: x.motivo }), h('td', { text: numero(x.registros_afectados) }), h('td', { text: x.primera_fila != null ? String(x.primera_fila) : '—' }))))) : null,
      h('h3', { text: 'Decisión técnica' }),
      decidible ? h('div', {}, field('Comentario', comentario), h('div', { class: 'form-actions' }, decidir('aprobar'), decidir('rechazar')))
        : h('p', { class: 'muted', text: 'La decisión se registra cuando la validación termina.' })));
    await Promise.all([pintarHallazgos(), pintarSugerencias()]);
    detalle.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ---------------------------------------------------------------- Correcciones guardadas
  let filtroInst = '', filtroTexto = '';
  async function pintarGuardadas() {
    const params = new URLSearchParams();
    if (filtroInst) params.set('institucion', filtroInst);
    if (filtroTexto) params.set('q', filtroTexto);
    const lista = await api<Equivalencia[]>(`qa/equivalencias?${params}`);
    const instituciones = [...new Set(bases.map(b => b.institucion).filter((x): x is string => Boolean(x)))];
    const selInst = select([['', 'Todas las instituciones'], ...instituciones.map(i => [i, i] as [string, string])], filtroInst);
    selInst.addEventListener('change', () => { filtroInst = selInst.value; void pintar(); });
    const buscar = input('search', filtroTexto, { placeholder: 'Texto original, código o nombre…' });
    buscar.addEventListener('change', () => { filtroTexto = buscar.value.trim(); void pintar(); });
    const local = notice();
    const filas = lista.map(e => {
      const quitar: HTMLButtonElement = button('Quitar', () => run(quitar, local, async () => {
        if (!confirmar(`¿Dejar de corregir «${e.texto_origen}» como ${e.codigo}? Las bases ya validadas no cambian hasta volver a aplicarlas.`)) return;
        await api(`qa/equivalencias/${e.id}`, 'DELETE');
        await pintar(); msg.show('Corrección quitada.');
      }), 'link');
      return h('tr', {},
        h('td', { text: e.institucion }), h('td', {}, h('strong', { text: e.nombre_catalogo }), h('p', { class: 'muted', text: e.catalogo })),
        h('td', { text: e.texto_origen }), h('td', {}, h('strong', { text: e.codigo }), e.etiqueta ? h('p', { class: 'muted', text: e.etiqueta }) : null),
        h('td', { text: ORIGEN[e.fuente] ?? e.fuente }), h('td', {}, h('span', { text: fecha(e.creado_en) }), e.aprobada_por ? h('p', { class: 'muted', text: e.aprobada_por }) : null),
        h('td', { text: numero(e.veces_usada) }), h('td', {}, quitar));
    });
    fill(cuerpo, h('section', { class: 'card' },
      h('h2', { text: 'Correcciones guardadas' }),
      h('p', { class: 'muted', text: 'Cada corrección aprobada se guarda para la institución: cuando ese mismo texto vuelve a aparecer en una base, se corrige solo con el código indicado.' }),
      h('div', { class: 'campos-linea' }, field('Institución', selInst), field('Buscar', buscar)), local,
      lista.length ? tabla(['Institución', 'Catálogo', 'Texto original', 'Código', 'Origen', 'Aprobada', 'Veces usada', ''], filas)
        : h('p', { class: 'empty', text: 'Todavía no hay correcciones guardadas. Se crean al aprobar las correcciones sugeridas de una base.' })));
  }

  let iniciado = false;
  const iniciar = () => { if (!iniciado && !pagina.hidden && !document.getElementById('app')?.hidden) { iniciado = true; void pintar(); } };
  new MutationObserver(iniciar).observe(pagina, { attributes: true, attributeFilter: ['hidden'] });
  const app = document.getElementById('app');
  if (app) new MutationObserver(iniciar).observe(app, { attributes: true, attributeFilter: ['hidden'] });
  iniciar();

  return {
    abrir: async (cargaId: string) => {
      try { await abrir(cargaId); } catch (error) { msg.show(error instanceof Error ? error.message : 'No se pudo abrir la auditoría.', true); }
    },
    refrescar: async () => { iniciado = true; await pintar(); },
  };
}
