"""Llamadas a Claude para Survey Audit y Quality Improvement.

Requiere ANTHROPIC_API_KEY. Modelos (opcionales):
  SURVEY_IA_MODELO   lectura de cuestionarios (por defecto claude-haiku-5-5)
  SURVEY_VERIF_MODELO validación cruzada con la grabación (por defecto, el de SURVEY_IA_MODELO)
  MEJORA_IA_MODELO   recomendaciones de Quality Improvement (por defecto claude-haiku-5-5)
  MEJORA_IA          0 para no usar IA en las recomendaciones aunque haya llave

Las respuestas se piden como JSON con esquema, así que llegan listas para usar.
Las pruebas reemplazan `responder` para no llamar a la API.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time

logger = logging.getLogger("quality_audit.ia")


class IANoDisponible(RuntimeError):
    """No hay llave configurada o la API no respondió."""


class IARespuestaLarga(IANoDisponible):
    """La respuesta no cupo en el máximo de tokens: hay que pedir menos contenido a la vez."""


class IAOcupada(IANoDisponible):
    """Claude está saturado o se alcanzó el límite de uso por minuto: conviene reintentar en un momento."""


def disponible() -> bool:
    return bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip())


MODELO = "claude-haiku-5-5"  # modelo económico para toda la plataforma
RESPALDO = {"SURVEY_VERIF_MODELO": "SURVEY_IA_MODELO"}  # la verificación usa el modelo del PDF si no se define


def modelo(variable: str) -> str:
    return (os.environ.get(variable) or os.environ.get(RESPALDO.get(variable, "")) or MODELO).strip()


def pdf(datos: bytes) -> dict:
    """Bloque de documento PDF: Claude lee el texto y también ve las páginas (sirve como OCR)."""
    return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                           "data": base64.standard_b64encode(datos).decode()}}


def _llamar(model: str, sistema: str, contenido: list[dict], esquema: dict, max_tokens: int) -> dict:
    import anthropic
    cliente = anthropic.Anthropic(timeout=240, max_retries=2)
    r = cliente.messages.create(
        model=model, max_tokens=max_tokens, system=sistema,
        messages=[{"role": "user", "content": contenido}],
        output_config={"format": {"type": "json_schema", "schema": esquema}},
    )
    if r.stop_reason == "max_tokens":
        raise IARespuestaLarga("La respuesta de la IA quedó incompleta por ser demasiado larga.")
    texto = next(b.text for b in r.content if b.type == "text")
    return json.loads(texto)


# Punto de reemplazo para pruebas: responder(model, sistema, contenido, esquema, max_tokens) -> dict
responder = _llamar


def generar(variable_modelo: str, sistema: str, contenido: list[dict] | str, esquema: dict,
            max_tokens: int = 16000) -> dict:
    if not disponible() and responder is _llamar:
        raise IANoDisponible("Esta función necesita la llave de Claude (ANTHROPIC_API_KEY) configurada en el servidor.")
    bloques = [{"type": "text", "text": contenido}] if isinstance(contenido, str) else contenido
    inicio = time.time()
    try:
        return responder(modelo(variable_modelo), sistema, bloques, esquema, max_tokens)
    except IANoDisponible:
        raise
    except Exception as exc:  # noqa: BLE001
        if type(exc).__name__ in {'RateLimitError', 'OverloadedError', 'InternalServerError'} or getattr(exc, 'status_code', None) in (429, 529):
            raise IAOcupada('Claude está atendiendo muchas solicitudes. Se volverá a intentar en unos segundos.') from exc
        if type(exc).__name__ == 'AuthenticationError':
            raise IANoDisponible('La llave de Claude (ANTHROPIC_API_KEY) no es válida. Revísala en la configuración del servidor.') from exc
        raise _error(exc, inicio) from exc


def _error(exc: Exception, inicio: float) -> IANoDisponible:
    logger.exception("Falló la llamada a la IA (%.1f s): %s", time.time() - inicio, exc)
    return IANoDisponible("La IA no respondió correctamente. Espera un momento y vuelve a intentarlo.")
