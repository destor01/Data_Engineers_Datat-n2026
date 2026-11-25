from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
ENCOVI_JEV_DIR = BASE_DIR / "encovi_jev"
EXAMPLE_TRANSCRIPT_PATH = ENCOVI_JEV_DIR / "examples" / "transcript_example.json"
DEFAULT_CACHE_DIR = BASE_DIR / ".jev_cache"

if ENCOVI_JEV_DIR.is_dir() and str(ENCOVI_JEV_DIR) not in sys.path:
    sys.path.insert(0, str(ENCOVI_JEV_DIR))

try:
    from audit import run_audit
    from calibration import Calibrator
    from jev_client import DEFAULT_MODEL, FakeJev, JevClient, JevError
    from rules import calibration_group, question_registry
    from rules_a1_a2 import SECTIONS
    from transcript import INTERVIEWER, OTHER, RESPONDENT, Turn, normalize_speaker

    JEV_IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover
    DEFAULT_MODEL = "typesafe/jev-1.14"
    INTERVIEWER, RESPONDENT, OTHER = "ENCUESTADOR", "INFORMANTE", "OTRA_PERSONA"
    JEV_IMPORT_ERROR = str(exc)

VALID_ROLES = (INTERVIEWER, RESPONDENT, OTHER)

_KNOWN_INTERVIEWER = {
    "E", "ENC", "ENCUESTADOR", "ENCUESTADORA", "ENTREVISTADOR", "ENTREVISTADORA", "INTERVIEWER",
}
_KNOWN_RESPONDENT = {
    "I", "INF", "INFORMANTE", "ENTREVISTADO", "ENTREVISTADA", "RESPONDENT",
}
_KNOWN_OTHER = {
    "O", "OTRO", "OTRA", "OTRA_PERSONA", "OTHER",
}

# Matches both "[00:01 - 00:05] Hablante 1:" (audio-audit TXT export) and "[00:01:02] ENCUESTADOR: texto"
_RANGE_HEADER_RE = re.compile(
    r"^\s*\[(?P<start>[\d:.]+)\s*[-–]\s*(?P<end>[\d:.]+)\]\s*(?P<label>[^:\[\]]+?)(?:\s*\[[^\]]+\])?\s*:\s*(?P<text>.*)$"
)
_SINGLE_LINE_RE = re.compile(
    r"^\s*(?:\[(?P<ts>[\d:.]+)\]\s*)?(?P<label>[\w áéíóúÁÉÍÓÚñÑ.-]{1,35}?)\s*:\s*(?P<text>.*)$"
)
_EXPORT_META_PREFIXES = (
    "TRANSCRIPCIÓN DE ENTREVISTA",
    "Archivo:",
    "Duración:",
    "Hablantes detectados:",
    "====",
)


def is_jev_available() -> bool:
    return JEV_IMPORT_ERROR is None


def _parse_seconds(ts: Any) -> float | None:
    if ts is None or ts == "":
        return None
    if isinstance(ts, (int, float)):
        return round(float(ts), 2)
    text = str(ts).strip()
    if not text:
        return None
    try:
        parts = [float(p) for p in text.split(":")]
        return round(sum(p * (60**i) for i, p in enumerate(reversed(parts))), 2)
    except ValueError:
        return None


def suggest_speaker_roles(speakers: Sequence[str]) -> dict[str, str]:
    """Suggest ENCUESTADOR / INFORMANTE / OTRA_PERSONA defaults for detected speakers."""
    suggestions: dict[str, str] = {}
    unassigned: list[str] = []

    for spk in speakers:
        norm = spk.strip().upper().replace(" ", "_")
        if norm in _KNOWN_INTERVIEWER:
            suggestions[spk] = INTERVIEWER
        elif norm in _KNOWN_RESPONDENT:
            suggestions[spk] = RESPONDENT
        elif norm in _KNOWN_OTHER:
            suggestions[spk] = OTHER
        else:
            unassigned.append(spk)

    has_interviewer = INTERVIEWER in suggestions.values()
    has_respondent = RESPONDENT in suggestions.values()

    for spk in unassigned:
        if not has_interviewer:
            suggestions[spk] = INTERVIEWER
            has_interviewer = True
        elif not has_respondent:
            suggestions[spk] = RESPONDENT
            has_respondent = True
        else:
            suggestions[spk] = OTHER

    return suggestions


def _looks_like_speaker_label(label: str) -> bool:
    raw = label.strip()
    norm = raw.upper().replace(" ", "_")
    if norm in _KNOWN_INTERVIEWER or norm in _KNOWN_RESPONDENT or norm in _KNOWN_OTHER:
        return True
    if re.match(r"^(HABLANTE|SPEAKER|LOCUTOR|PERSONA|VOZ)\s*[_#-]?\s*\d+$", raw, re.IGNORECASE):
        return True
    return raw.isupper() and any(ch.isalpha() for ch in raw)


def parse_uploaded_transcript(content: bytes, filename: str) -> dict[str, Any]:
    """Parse an uploaded .json or .txt transcript into audio-audit's standard turns payload."""
    try:
        raw_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw_text = content.decode("latin-1")

    ext = Path(filename or "transcripcion.txt").suffix.lower()
    turns: list[dict[str, Any]] = []
    note: str | None = None

    if ext == ".json":
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"El archivo JSON no es válido: {exc}") from exc

        if isinstance(data, dict):
            note = data.get("nota") or data.get("note")
            items = data.get("turns", data.get("turnos"))
        else:
            items = data

        if not isinstance(items, list):
            raise ValueError(
                "El JSON debe ser una lista de intervenciones o un objeto con la clave 'turns' / 'turnos'."
            )

        for it in items:
            if not isinstance(it, dict):
                continue
            text = str(it.get("text", it.get("texto", ""))).strip()
            if not text:
                continue
            speaker = str(it.get("speaker", it.get("hablante", ""))).strip() or "Hablante 1"
            start = _parse_seconds(it.get("start", it.get("inicio")))
            end = _parse_seconds(it.get("end", it.get("fin")))
            if end is None and start is not None:
                end = start
            turns.append(
                {
                    "speaker": speaker,
                    "start": start,
                    "end": end,
                    "text": text,
                    "has_overlap": bool(it.get("has_overlap", False)),
                }
            )
    else:
        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if not turns and any(line.startswith(prefix) for prefix in _EXPORT_META_PREFIXES):
                continue

            m_range = _RANGE_HEADER_RE.match(line)
            if m_range:
                turns.append(
                    {
                        "speaker": m_range.group("label").strip(),
                        "start": _parse_seconds(m_range.group("start")),
                        "end": _parse_seconds(m_range.group("end")),
                        "text": m_range.group("text").strip(),
                        "has_overlap": "[voces superpuestas]" in line.lower(),
                    }
                )
                continue

            m_single = _SINGLE_LINE_RE.match(line)
            if m_single and _looks_like_speaker_label(m_single.group("label")):
                ts = _parse_seconds(m_single.group("ts"))
                turns.append(
                    {
                        "speaker": m_single.group("label").strip(),
                        "start": ts,
                        "end": ts,
                        "text": m_single.group("text").strip(),
                        "has_overlap": False,
                    }
                )
                continue

            if turns:
                prev_text = turns[-1]["text"]
                turns[-1]["text"] = f"{prev_text} {line}".strip() if prev_text else line
            else:
                raise ValueError(
                    "No se reconoció el formato de la transcripción. Usa líneas como "
                    "'[00:01:02] ENCUESTADOR: texto', 'Hablante 1: texto' o un archivo JSON de turnos."
                )

        turns = [t for t in turns if t["text"]]

    if not turns:
        raise ValueError("El archivo no contiene intervenciones de texto válidas.")

    speakers: list[str] = []
    for t in turns:
        if t["speaker"] not in speakers:
            speakers.append(t["speaker"])

    # Compute approximate duration if timestamps exist
    ts_values = [
        v for t in turns for v in (t.get("start"), t.get("end")) if isinstance(v, (int, float))
    ]
    duration = max(ts_values) if ts_values else None

    return {
        "turns": turns,
        "speakers": speakers,
        "suggested_roles": suggest_speaker_roles(speakers),
        "duration_seconds": duration,
        "note": note,
        "warning": None,
    }


def load_example_transcript() -> dict[str, Any]:
    if not EXAMPLE_TRANSCRIPT_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró la entrevista de ejemplo en {EXAMPLE_TRANSCRIPT_PATH}."
        )
    parsed = parse_uploaded_transcript(
        EXAMPLE_TRANSCRIPT_PATH.read_bytes(),
        EXAMPLE_TRANSCRIPT_PATH.name,
    )
    parsed["filename"] = EXAMPLE_TRANSCRIPT_PATH.name
    return parsed


def _build_overall_summary(report: dict[str, Any]) -> dict[str, Any]:
    sections = report.get("sections") or {}
    instructions = report.get("instructions") or []

    total_n = len(instructions)
    sum_c = sum(float(ins.get("p_followed") or 0.0) for ins in instructions)
    sum_v = sum(float(ins.get("p_broken") or 0.0) for ins in instructions)
    applicable = sum_c + sum_v

    w_c = sum(float(ins.get("weight") or 1) * float(ins.get("p_followed") or 0.0) for ins in instructions)
    w_app = sum(
        float(ins.get("weight") or 1) * (float(ins.get("p_followed") or 0.0) + float(ins.get("p_broken") or 0.0))
        for ins in instructions
    )

    rate = round(sum_c / applicable, 4) if applicable > 1e-9 else None
    weighted_rate = round(w_c / w_app, 4) if w_app > 1e-9 else None
    coverage = round(applicable / total_n, 4) if total_n else None

    high_risk_count = sum(1 for ins in instructions if float(ins.get("p_broken") or 0.0) >= 0.7)
    review_count = sum(1 for ins in instructions if 0.3 <= float(ins.get("p_broken") or 0.0) < 0.7)

    score_ref = weighted_rate if weighted_rate is not None else rate
    if score_ref is None:
        verdict = {"label": "Sin evidencia suficiente", "level": "muted"}
    elif score_ref >= 0.90 and high_risk_count == 0:
        verdict = {"label": "Cumplimiento alto", "level": "ok"}
    elif score_ref >= 0.75 and high_risk_count <= 2:
        verdict = {"label": "Aceptable con observaciones", "level": "warn"}
    else:
        verdict = {"label": "Requiere revisión prioritaria", "level": "danger"}

    all_risks: list[dict[str, Any]] = []
    for sid, sec in sections.items():
        for risk in sec.get("top_risks") or []:
            all_risks.append({**risk, "section": sid, "section_title": sec.get("title", sid)})
    all_risks.sort(key=lambda r: -float(r.get("p_broken") or 0.0))

    return {
        "n_instructions": total_n,
        "compliance_rate": rate,
        "compliance_rate_weighted": weighted_rate,
        "expected_followed": round(sum_c, 2),
        "expected_broken": round(sum_v, 2),
        "coverage": coverage,
        "high_risk_count": high_risk_count,
        "review_count": review_count,
        "verdict": verdict,
        "top_risks": all_risks[:10],
    }


def _friendly_jev_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "no api key" in low or "openrouter_api_key" in low:
        return (
            "Falta configurar OPENROUTER_API_KEY en el archivo .env (o en el panel superior) "
            "para llamar al modelo JEV en OpenRouter."
        )
    if "http 401" in low or "unauthorized" in low or "invalid" in low and "key" in low:
        return (
            "OpenRouter rechazó la clave OPENROUTER_API_KEY (HTTP 401). "
            "Verifica que la clave esté completa y activa en https://openrouter.ai/keys."
        )
    if "http 402" in low or "credit" in low or "insufficient" in low:
        return (
            "Tu cuenta de OpenRouter no tiene saldo suficiente para esta consulta (HTTP 402). "
            "Recarga créditos o activa el «Modo prueba sin conexión» para probar la interfaz."
        )
    if "http 429" in low:
        return "OpenRouter limitó temporalmente las peticiones (HTTP 429). Intenta de nuevo en unos segundos."
    if "network error" in low or "connectionerror" in low or "timeout" in low:
        return f"No se pudo conectar con OpenRouter (error de red/tiempo de espera): {msg}"
    return f"Error al evaluar con JEV: {msg}"


def evaluate_transcript_with_jev(
    turns_data: Sequence[Mapping[str, Any]],
    *,
    speaker_map: Mapping[str, str] | None = None,
    first_contact: bool = True,
    mock: bool = False,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    cache_dir: Path | None = DEFAULT_CACHE_DIR,
) -> dict[str, Any]:
    """Run ENCOVI A1–A2 JEV evaluation on an in-memory list of turns."""
    if not is_jev_available():
        raise RuntimeError(
            f"El módulo encovi_jev no está disponible en {ENCOVI_JEV_DIR}: {JEV_IMPORT_ERROR}"
        )

    clean_map: dict[str, str] = {}
    if speaker_map:
        for raw_spk, role in speaker_map.items():
            role_upper = str(role or "").strip().upper()
            if role_upper not in VALID_ROLES:
                raise ValueError(
                    f"Rol inválido '{role}' para '{raw_spk}'. Usa ENCUESTADOR, INFORMANTE u OTRA_PERSONA."
                )
            clean_map[str(raw_spk).strip()] = role_upper

    jev_turns: list[Turn] = []
    for item in turns_data:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        raw_spk = str(item.get("speaker") or "").strip()
        mapped_spk = normalize_speaker(raw_spk, clean_map)
        start = _parse_seconds(item.get("start"))
        end = _parse_seconds(item.get("end"))
        jev_turns.append(Turn(mapped_spk, text, start, end))

    if not jev_turns:
        raise ValueError("La transcripción está vacía y no se puede evaluar.")

    if not any(t.speaker == INTERVIEWER for t in jev_turns):
        raise ValueError(
            "Debes asignar al menos un hablante como ENCUESTADOR antes de evaluar la entrevista con JEV."
        )

    if mock:
        reg = question_registry(SECTIONS)
        client = FakeJev(
            {k: calibration_group(k, SECTIONS) for k in reg},
            {k: q.roles for k, q in reg.items() if q.type == "choice"},
        )
    else:
        try:
            client = JevClient(
                api_key=api_key,
                model=model or DEFAULT_MODEL,
                cache_dir=cache_dir,
            )
        except JevError as exc:
            raise RuntimeError(_friendly_jev_error(exc)) from exc

    try:
        report = run_audit(
            jev_turns,
            client,
            SECTIONS,
            first_contact=first_contact,
            calibrator=Calibrator(),
        )
    except JevError as exc:
        raise RuntimeError(_friendly_jev_error(exc)) from exc

    report.pop("_windows_text", None)
    report["mock"] = bool(mock)
    report["speaker_map"] = clean_map
    if mock:
        report["warning"] = (
            "Modo prueba sin conexión: estas probabilidades son simuladas y no reflejan una evaluación real."
        )
    report["overall"] = _build_overall_summary(report)
    return report
