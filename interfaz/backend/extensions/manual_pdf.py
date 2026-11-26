"""Manual institucional en PDF (fpdf2, fuentes DejaVu incluidas para acentos y símbolos)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

FUENTES = Path(__file__).resolve().parent / 'fuentes'
AZUL = (0, 64, 128)
CELESTE = (0, 128, 255)
GRIS = (96, 117, 133)
TEXTO = (27, 52, 66)
FONDO = (238, 246, 255)
PRIORIDAD = {'alta': ((180, 35, 24), 'Prioridad alta'), 'media': ((176, 110, 0), 'Prioridad media'),
             'baja': ((60, 110, 80), 'Prioridad baja')}
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre']


def _fecha(iso: str | None) -> str:
    try:
        d = datetime.fromisoformat(iso) if iso else datetime.now()
    except ValueError:
        d = datetime.now()
    return f'{d.day} de {MESES[d.month - 1]} de {d.year}'


class _Manual(FPDF):
    def __init__(self, m: dict):
        super().__init__(format='Letter')
        self.m = m
        self.borrador = m['estado'] != 'final'
        self.add_font('DejaVu', '', str(FUENTES / 'DejaVuSans.ttf'))
        self.add_font('DejaVu', 'B', str(FUENTES / 'DejaVuSans-Bold.ttf'))
        self.add_font('DejaVu', 'I', str(FUENTES / 'DejaVuSans-Oblique.ttf'))
        self.set_auto_page_break(True, margin=20)
        self.set_margins(20, 18, 20)
        self.set_text_shaping(False)
        self.set_title(m['titulo'])
        self.set_author('Quality Audit · Data Engineers')

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font('DejaVu', '', 8)
        self.set_text_color(*GRIS)
        self.cell(0, 6, f"{self.m['institucion_nombre']} · {self.m['titulo']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*CELESTE)
        self.line(20, self.get_y(), self.w - 20, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-14)
        self.set_font('DejaVu', '', 8)
        self.set_text_color(*GRIS)
        estado = 'BORRADOR · ' if self.borrador else ''
        self.cell(0, 6, f'{estado}Quality Audit · Instituto Nacional de Estadística de Guatemala', align='L')
        self.set_x(-40)
        self.cell(20, 6, f'Página {self.page_no()} de {{nb}}', align='R')

    # -- piezas ---------------------------------------------------------------
    def titulo_seccion(self, texto: str):
        self.ln(3)
        self.set_font('DejaVu', 'B', 14)
        self.set_text_color(*AZUL)
        self.multi_cell(0, 7, texto, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*CELESTE)
        self.set_line_width(0.6)
        self.line(20, self.get_y() + 1, 50, self.get_y() + 1)
        self.set_line_width(0.2)
        self.ln(4)

    def parrafo(self, texto: str, tam: float = 10.5):
        self.set_font('DejaVu', '', tam)
        self.set_text_color(*TEXTO)
        self.multi_cell(0, 5.6, texto, align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1.5)

    def subtitulo(self, texto: str):
        self.set_font('DejaVu', 'B', 10.5)
        self.set_text_color(*AZUL)
        self.cell(0, 6.5, texto, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def lista(self, items: list[str], numerada: bool = True):
        self.set_font('DejaVu', '', 10.5)
        self.set_text_color(*TEXTO)
        for i, item in enumerate(items, 1):
            marca = f'{i}.' if numerada else '•'
            self.set_x(24)
            self.cell(7, 5.6, marca)
            self.multi_cell(0, 5.6, item, align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1.5)


def _portada(pdf: _Manual, m: dict):
    pdf.add_page()
    pdf.set_fill_color(*AZUL)
    pdf.rect(0, 0, pdf.w, 72, style='F')
    pdf.set_xy(20, 22)
    pdf.set_font('DejaVu', 'B', 9)
    pdf.set_text_color(170, 205, 255)
    pdf.cell(0, 6, 'INSTITUTO NACIONAL DE ESTADÍSTICA · GUATEMALA', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(20)
    pdf.set_font('DejaVu', 'B', 22)
    pdf.set_text_color(255, 255, 255)
    pdf.multi_cell(pdf.w - 40, 10, m['titulo'], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)
    pdf.set_x(20)
    pdf.set_font('DejaVu', '', 13)
    pdf.multi_cell(pdf.w - 40, 7, f"Dirigido a: {m['institucion_nombre']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if pdf.borrador:
        pdf.set_xy(pdf.w - 62, 58)
        pdf.set_fill_color(255, 214, 102)
        pdf.set_text_color(90, 60, 0)
        pdf.set_font('DejaVu', 'B', 10)
        pdf.cell(42, 8, 'BORRADOR', align='C', fill=True)
    pdf.set_xy(20, 84)
    secciones = m['secciones']
    alcance = sorted({f"{s['base_nombre']} · {s['periodo']}" for s in secciones})
    datos = [('Versión', str(m['version'])),
             ('Fecha', _fecha((m.get('finalizacion') or {}).get('en') or m.get('creado_en'))),
             ('Bases revisadas', ', '.join(alcance)),
             ('Recomendaciones', str(len(secciones)))]
    if m.get('finalizacion'):
        datos.append(('Aprobado por', m['finalizacion']['cargo']))
    for etiqueta, valor in datos:
        pdf.set_font('DejaVu', 'B', 10)
        pdf.set_text_color(*GRIS)
        pdf.cell(45, 7, etiqueta)
        pdf.set_font('DejaVu', '', 10.5)
        pdf.set_text_color(*TEXTO)
        pdf.multi_cell(0, 7, valor, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)
    pdf.titulo_seccion('Presentación')
    pdf.parrafo(m['introduccion'])

    # Resumen
    pdf.titulo_seccion('Resumen de problemas encontrados')
    anchos = (86, 52, 38)
    pdf.set_font('DejaVu', 'B', 9)
    pdf.set_fill_color(*AZUL)
    pdf.set_text_color(255, 255, 255)
    for texto, ancho in zip(('Problema', 'Base y período', 'Prioridad'), anchos):
        pdf.cell(ancho, 7, f' {texto}', fill=True)
    pdf.ln()
    pdf.set_font('DejaVu', '', 9)
    for i, s in enumerate(secciones, 1):
        textos = [f'{i}. {s["titulo"]}', f'{s["base_nombre"]} · {s["periodo"]}',
                  PRIORIDAD[s['prioridad']][1].replace('Prioridad ', '').capitalize()]
        lineas = [pdf.multi_cell(a - 3, 5.5, t, dry_run=True, output='LINES') for t, a in zip(textos, anchos)]
        alto = 5.5 * max(len(l) for l in lineas) + 2
        if pdf.get_y() + alto > pdf.h - 22:
            pdf.add_page()
        y = pdf.get_y()
        pdf.set_fill_color(*(FONDO if i % 2 else (255, 255, 255)))
        pdf.rect(20, y, sum(anchos), alto, style='F')
        pdf.set_text_color(*TEXTO)
        x = 20
        for texto, ancho in zip(textos, anchos):
            pdf.set_xy(x + 1.5, y + 1)
            pdf.multi_cell(ancho - 3, 5.5, texto, align='L')
            x += ancho
        pdf.set_xy(20, y + alto)


def _recomendacion(pdf: _Manual, n: int, s: dict):
    pdf.add_page()
    color, etiqueta = PRIORIDAD[s['prioridad']]
    pdf.set_font('DejaVu', 'B', 8.5)
    pdf.set_fill_color(*color)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(pdf.get_string_width(etiqueta) + 8, 6, etiqueta, align='C', fill=True)
    pdf.set_text_color(*GRIS)
    pdf.set_font('DejaVu', '', 9)
    pdf.cell(0, 6, f"   {s['base_nombre']} · {s['periodo']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_font('DejaVu', 'B', 15)
    pdf.set_text_color(*AZUL)
    pdf.multi_cell(0, 7.5, f"{n}. {s['titulo']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)
    for subtitulo, clave in (('Qué ocurrió', 'que_ocurrio'), ('Por qué es un problema', 'por_que'),
                             ('Cómo corregirlo', 'como_corregir'), ('Cómo prevenirlo', 'como_prevenir')):
        pdf.subtitulo(subtitulo)
        pdf.parrafo(s[clave])
    pdf.subtitulo('Acciones de mejora')
    pdf.lista(s['acciones'])

    evidencia = [e for e in s.get('evidencia') or [] if e.get('n') or e.get('columna')]
    if evidencia:
        pdf.subtitulo('Evidencia de la auditoría')
        pdf.set_font('DejaVu', 'I', 8.5)
        pdf.set_text_color(*GRIS)
        total = s.get('total_registros')
        pdf.multi_cell(0, 5, f"Cifras del reporte de Data Audit{f' sobre {total:,} registros recibidos'.replace(',', ' ') if total else ''}. "
                       'Las filas indican la posición en el archivo enviado.', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)
        anchos = (48, 26, 20, 82)
        pdf.set_font('DejaVu', 'B', 8.5)
        pdf.set_fill_color(*FONDO)
        pdf.set_text_color(*AZUL)
        for texto, ancho in zip(('Columna', 'Registros', '%', 'Filas de ejemplo'), anchos):
            pdf.cell(ancho, 6, f' {texto}', fill=True)
        pdf.ln()
        pdf.set_font('DejaVu', '', 8.5)
        pdf.set_text_color(*TEXTO)
        for e in evidencia[:25]:
            pct = f"{e['porcentaje']:.1f}" if isinstance(e.get('porcentaje'), (int, float)) else '—'
            filas = ', '.join(str(f) for f in e.get('filas') or []) or '—'
            for texto, ancho in zip((e.get('columna') or 'Archivo', f"{e['n']:,}".replace(',', ' '), pct, filas), anchos):
                pdf.cell(ancho, 5.5, f' {texto}'[:60])
            pdf.ln()
        if len(evidencia) > 25:
            pdf.cell(0, 5.5, f' … y {len(evidencia) - 25} columnas más', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
    if s.get('aprobacion'):
        pdf.set_font('DejaVu', 'I', 8.5)
        pdf.set_text_color(*GRIS)
        pdf.multi_cell(0, 5, f"Recomendación aprobada por: {s['aprobacion']['cargo']} · {_fecha(s['aprobacion'].get('en'))}",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def generar_pdf(m: dict) -> bytes:
    pdf = _Manual(m)
    _portada(pdf, m)
    for i, s in enumerate(m['secciones'], 1):
        _recomendacion(pdf, i, s)
    if m.get('cierre'):
        pdf.ln(4)
        pdf.titulo_seccion('Antes de cada envío')
        pdf.parrafo(m['cierre'])
    pdf.set_font('DejaVu', 'I', 8.5)
    pdf.set_text_color(*GRIS)
    pdf.ln(2)
    pdf.multi_cell(0, 5, 'Documento generado con Quality Audit a partir de la auditoría automática de datos. '
                   'Las recomendaciones fueron revisadas y aprobadas por personal técnico.' if not pdf.borrador else
                   'Borrador: el contenido puede cambiar antes de su versión final.', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())
