"""Codificadores: proponen un código de catálogo para un texto que no tiene equivalencia aprobada.

El motor usa cualquier objeto con el método `sugerir`. Hoy viene el de similitud
de texto (sin red, rápido, sirve para "Coban" -> Cobán o "ROBO COMERCIO" -> Robo a
comercios). El de IA tendrá la misma firma y se enchufa sin tocar el motor.

Toda sugerencia queda PENDIENTE: un analista la aprueba y desde ese momento es una
equivalencia aprobada que el motor aplica solo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from rapidfuzz import fuzz, process

from .definicion import Catalogo
from .texto import normalizar


@dataclass
class Sugerencia:
    codigo: str
    confianza: float          # 0 a 1
    justificacion: str


class Codificador(Protocol):
    nombre: str

    def sugerir(self, catalogo: Catalogo, textos: list[str],
                contexto: dict[str, dict] | None = None) -> dict[str, Sugerencia]:
        ...


class CodificadorSimilitud:
    """Compara contra las etiquetas del catálogo y las equivalencias aprobadas.

    Usa la distancia de edición (fuzz.ratio): encuentra errores de escritura y
    variantes cercanas ("PORTACION ILEGAL DE ARMA DE FUEGO" -> "Portación ilegal arma
    de fuego"), pero no inventa equivalencias de significado: eso es trabajo de la IA.
    """

    nombre = "similitud"

    def __init__(self, minimo: float = 0.6):
        self.minimo = minimo

    def sugerir(self, catalogo: Catalogo, textos: list[str], contexto=None) -> dict[str, Sugerencia]:
        # Dos fuentes: las etiquetas oficiales y los textos ya aprobados (equivalencias).
        # Un texto aprobado solo se usa si es casi idéntico (>= 90 %): "PORTACION ILEGALL DE ARMA"
        # sí, pero "TRASLADO ILEGAL DE ARMA" no debe heredar el código de "PORTACION ILEGAL DE ARMA".
        oficiales: dict[str, tuple[str, str]] = {}
        for cod, v in catalogo.valores.items():
            if not v.ignorado:
                oficiales[normalizar(v.etiqueta)] = (cod, v.etiqueta)
        aprobados: dict[str, tuple[str, str]] = {}
        for texto, (cod, _) in catalogo.equivalencias.items():
            if cod in catalogo.valores and texto not in oficiales:
                aprobados[texto] = (cod, catalogo.valores[cod].etiqueta)
        salida = {}
        for t in textos:
            n = normalizar(t)
            if not n:
                continue
            candidatos = []
            if oficiales:
                m = process.extractOne(n, list(oficiales), scorer=fuzz.ratio)
                if m:
                    cod, etq = oficiales[m[0]]
                    candidatos.append((m[1], cod, f"Se parece a \"{etq}\" (similitud {m[1]:.0f} %)"))
            if aprobados:
                m = process.extractOne(n, list(aprobados), scorer=fuzz.ratio)
                if m and m[1] >= 90:
                    cod, etq = aprobados[m[0]]
                    candidatos.append((m[1], cod, f"Casi igual a \"{m[0]}\", ya aprobado como {etq} "
                                                  f"(similitud {m[1]:.0f} %)"))
            if not candidatos:
                continue
            puntaje, cod, por_que = max(candidatos)
            conf = round(puntaje / 100, 3)
            if conf >= self.minimo:
                salida[t] = Sugerencia(cod, conf, por_que)
        return salida
