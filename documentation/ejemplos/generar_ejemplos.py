"""Genera los archivos de ejemplo SINTÉTICOS para probar Survey Audit sin datos reales.

    python documentation/ejemplos/generar_ejemplos.py

Crea:
  cuestionario_sintetico.pdf    cuestionario de 2 páginas con secciones, opciones, pases, una tabla
                                de artículos y una sección por persona.
  transcripcion_sintetica.json  transcripción en el formato que descarga Audio Audit, con una
                                discrepancia sembrada (horas de agua: se dicen 8).
Ningún contenido proviene de una entrevista real.
"""
from __future__ import annotations

import json
from pathlib import Path

from fpdf import FPDF

AQUI = Path(__file__).resolve().parent
FUENTES = AQUI.parents[1] / "interfaz/backend/extensions/fuentes"


def pdf() -> None:
    doc = FPDF(orientation="P", format="Letter")
    doc.add_font("D", "", str(FUENTES / "DejaVuSans.ttf"))
    doc.add_font("D", "B", str(FUENTES / "DejaVuSans-Bold.ttf"))
    doc.set_auto_page_break(True, 15)

    def titulo(t):
        doc.set_font("D", "B", 12); doc.set_fill_color(225, 232, 245); doc.cell(0, 8, t, fill=True, new_x="LMARGIN", new_y="NEXT"); doc.ln(2)

    def texto(t, negrita=False, sangria=0):
        doc.set_font("D", "B" if negrita else "", 10); doc.set_x(doc.l_margin + sangria); doc.multi_cell(0, 5.5, t, new_x="LMARGIN", new_y="NEXT")

    doc.add_page()
    doc.set_font("D", "B", 15); doc.cell(0, 9, "Encuesta de Condiciones del Hogar (EJEMPLO SINTÉTICO)", new_x="LMARGIN", new_y="NEXT")
    doc.set_font("D", "", 9); doc.multi_cell(0, 5, "Cuestionario de demostración para Quality Audit. No pertenece a ninguna encuesta oficial. "
                                              "Lea cada pregunta tal como está escrita y anote el código de la respuesta.", new_x="LMARGIN", new_y="NEXT"); doc.ln(3)
    titulo("SECCIÓN A. VIVIENDA (una vez por hogar)")
    texto("A1. ¿Qué tipo de vivienda ocupa este hogar?", True)
    texto("1. Casa formal     2. Apartamento     3. Rancho     4. Otro", sangria=6)
    texto("A2. ¿La vivienda tiene servicio de agua entubada?", True)
    texto("1. Sí     2. No → PASE A A4", sangria=6)
    texto("A3. ¿Cuántas horas al día tiene servicio de agua?  ____ horas (0 a 24)", True)
    texto("A4. ¿Cuántos cuartos tiene la vivienda, sin contar baño ni cocina?  ____ cuartos (1 a 20)", True)
    doc.ln(2)
    titulo("SECCIÓN B. EQUIPAMIENTO DEL HOGAR")
    texto("Para cada artículo pregunte B1 y, si la respuesta es Sí, B2. Si responde No, pase al siguiente artículo (PS).")
    doc.ln(1); doc.set_font("D", "B", 9)
    anchos = [10, 60, 60, 50]
    for w, t in zip(anchos, ["Cód.", "Artículo", "B1. ¿El hogar tiene (...)?\n1. Sí  2. No → PS", "B2. ¿Cuántos(as) (...) tiene?"]):
        doc.cell(w, 10, t.split("\n")[0], border=1)
    doc.ln(); doc.set_font("D", "", 9)
    for cod, art in [("01", "Estufa"), ("02", "Refrigeradora"), ("03", "Televisor"), ("04", "Computadora")]:
        for w, t in zip(anchos, [cod, art, "1. Sí   2. No → PS", "____"]):
            doc.cell(w, 7, t, border=1)
        doc.ln()
    doc.add_page()
    titulo("SECCIÓN C. CARACTERÍSTICAS DE LAS PERSONAS (una vez por cada persona del hogar)")
    texto("C1. Sexo", True); texto("1. Hombre     2. Mujer", sangria=6)
    texto("C2. ¿Cuántos años cumplidos tiene?  ____ años (0 a 110)", True)
    texto("C3. ¿Trabajó la semana pasada, aunque fuera por una hora?", True)
    texto("1. Sí     2. No → PASE A LA SIGUIENTE PERSONA (fin de la sección)", sangria=6)
    texto("C4. ¿Cuánto ganó el mes pasado en su trabajo principal?  Q ______ (0 a 100,000)", True)
    doc.ln(4); doc.set_font("D", "", 9)
    doc.multi_cell(0, 5, "Al terminar, agradezca al informante y recuerde que la información es confidencial y se usa solo con fines estadísticos.",
                   new_x="LMARGIN", new_y="NEXT")
    doc.output(str(AQUI / "cuestionario_sintetico.pdf"))


def transcripcion() -> None:
    turnos = [
        ("ENC", 0, 6, "Buenos días, soy encuestadora de la encuesta de condiciones del hogar. La información es confidencial y solo con fines estadísticos."),
        ("INF", 6, 8, "Buenos días, pase adelante."),
        ("ENC", 9, 13, "¿Qué tipo de vivienda ocupa este hogar? ¿Casa formal, apartamento, rancho u otro?"),
        ("INF", 13, 15, "Es casa formal."),
        ("ENC", 16, 19, "¿La vivienda tiene servicio de agua entubada?"),
        ("INF", 19, 20, "Sí, sí tenemos."),
        ("ENC", 21, 24, "¿Cuántas horas al día tiene servicio de agua?"),
        ("INF", 24, 28, "Como ocho horas, en la mañana nada más."),
        ("ENC", 29, 33, "¿Cuántos cuartos tiene la vivienda, sin contar baño ni cocina?"),
        ("INF", 33, 35, "Tres cuartos."),
        ("ENC", 36, 39, "¿El hogar tiene estufa?"),
        ("INF", 39, 40, "Sí."),
        ("ENC", 41, 43, "¿Cuántas estufas tiene?"),
        ("INF", 43, 44, "Una."),
        ("ENC", 45, 47, "¿Y refrigeradora?"),
        ("INF", 47, 48, "No tenemos."),
        ("ENC", 60, 64, "Ahora sobre usted. ¿Cuántos años cumplidos tiene?"),
        ("INF", 64, 66, "Cuarenta y dos."),
        ("ENC", 67, 71, "¿Trabajó la semana pasada, aunque fuera por una hora?"),
        ("INF", 71, 74, "Sí, en la tienda."),
        ("ENC", 75, 79, "¿Cuánto ganó el mes pasado en su trabajo principal?"),
        ("INF", 79, 82, "Unos dos mil quinientos quetzales."),
        ("ENC", 83, 87, "Muchas gracias por su tiempo."),
    ]
    datos = {
        "fuente": "Audio Audit", "job_id": "ejemplo-sintetico-0001", "archivo": "entrevista_sintetica.mp3",
        "nota": "TRANSCRIPCIÓN SINTÉTICA para pruebas. Discrepancia sembrada: se dice 'ocho horas' de agua.",
        "result": {"speakers": ["ENC", "INF"],
                   "turns": [{"speaker": s, "start": a, "end": b, "text": t} for s, a, b, t in turnos]},
    }
    (AQUI / "transcripcion_sintetica.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    pdf(); transcripcion(); print("listo")
