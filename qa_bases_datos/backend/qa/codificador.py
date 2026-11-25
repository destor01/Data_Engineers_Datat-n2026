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
        opciones: dict[str, tuple[str, str]] = {}          # texto normalizado -> (código, etiqueta mostrada)
        for cod, v in catalogo.valores.items():
            if not v.ignorado:
                opciones[normalizar(v.etiqueta)] = (cod, v.etiqueta)
        for texto, (cod, _) in catalogo.equivalencias.items():
            if cod in catalogo.valores:
                opciones.setdefault(texto, (cod, catalogo.valores[cod].etiqueta))
        claves = list(opciones)
        salida = {}
        for t in textos:
            n = normalizar(t)
            if not n or not claves:
                continue
            mejor = process.extractOne(n, claves, scorer=fuzz.ratio)
            if not mejor:
                continue
            clave, puntaje, _ = mejor
            conf = round(puntaje / 100, 3)
            if conf < self.minimo:
                continue
            cod, etq = opciones[clave]
            salida[t] = Sugerencia(cod, conf, f"Se parece a \"{etq}\" (similitud {puntaje:.0f} %)")
        return salida
