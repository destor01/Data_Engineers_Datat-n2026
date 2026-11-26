"""Prueba rápida del codificador con IA, sin procesar un archivo completo.

    python -m scripts.probar_ia                      # ejemplos de PNC, CIE-10 y sitio
    python -m scripts.probar_ia --catalogo PNC_CAUSA "AGRESION A FEMINA" "ROBO A TIENDA DE BARRIO"

Usa la misma configuración que la API (.env: QA_IA_PROVEEDOR, ANTHROPIC_API_KEY, QA_IA_MODELO).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qa.codificador_ia import CodificadorIA, crear_codificador  # noqa: E402
from qa.definicion import cargar_definicion  # noqa: E402

EJEMPLOS = {
    ("DETENIDOS", "PNC_CAUSA"): ["RESPONSABILIDAD DE CONDUCTORES", "LESIONES CULPOSAS EN HECHO DE TRANSITO",
                                 "AGRESION A FEMINA", "VIOLENTAR MEDIDAS DE SEGURIDAD", "PORTACION ILEGAL DE ARMA DE FUEGO",
                                 "NEGACION DE ASISTENCIA ECONOMICA", "TENECIA DE DROGA", "EXTORSION Y ASOCIACION ILICITA"],
    ("DEFUNCIONES", "CIE10"): ["Paro Cardiorrespiratorio", "Infarto Agudo al Miocardio", "Choque Septico",
                               "Neumonia adquirida en la comunidad", "Herida por arma de fuego en torax",
                               "Diabetes Mellitus tipo 2 descompensada", "Insuficiencia renal cronica"],
    ("DEFUNCIONES", "DEF_SITIO"): ["HOSPITAL ROOSEVELT", "Aldea Xesuc, Paraje Vista Hermosa", "IGSS Zona 9",
                                   "Km 45 Carretera Interamericana", "Sanatorio Nuestra Señora del Pilar"],
}


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    logging.basicConfig(level=logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--catalogo")
    ap.add_argument("textos", nargs="*")
    a = ap.parse_args()

    cod = crear_codificador()
    if not isinstance(cod, CodificadorIA):
        sys.exit("La IA no está configurada: pon QA_IA_PROVEEDOR=anthropic y ANTHROPIC_API_KEY en qa_bases_datos/.env "
                 "(o QA_IA_PROVEEDOR=ollama si usas un modelo local).")
    print(f"Proveedor: {type(cod.proveedor).__name__}  modelo: {getattr(cod.proveedor, 'modelo', '?')}\n")
    casos = EJEMPLOS
    if a.catalogo:
        base = next((b for (b, c) in EJEMPLOS if c == a.catalogo.upper()), "DEFUNCIONES")
        casos = {(base, a.catalogo.upper()): a.textos or EJEMPLOS.get((base, a.catalogo.upper()), [])}

    with psycopg.connect(a.db) as con, con.cursor() as cur:
        for (base, catalogo), textos in casos.items():
            cat = cargar_definicion(cur, base).catalogos[catalogo]
            cod.umbral_directo = 1.01            # en la prueba, todo pasa por la IA
            t0 = time.time()
            res = cod.sugerir(cat, textos)
            print(f"== {catalogo} ({time.time() - t0:.1f} s)")
            for t in textos:
                s = res.get(t)
                if s:
                    print(f"  {t[:45]:45} -> {s.codigo:5} {cat.valores[s.codigo].etiqueta[:40]:40} conf {s.confianza:.2f}")
                    print(f"  {'':45}    {s.justificacion[:110]}")
                else:
                    print(f"  {t[:45]:45} -> sin código")
            print()
    print("Estadísticas:", cod.estadisticas)


if __name__ == "__main__":
    main()
