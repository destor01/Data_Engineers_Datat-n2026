from __future__ import annotations

import copy
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
ENCOVI_JEV_DIR = BASE_DIR / "encovi_jev"
EXAMPLE_TRANSCRIPT_PATH = ENCOVI_JEV_DIR / "examples" / "transcript_example.json"
IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
DEFAULT_CACHE_DIR = Path("/tmp/.jev_cache") if IS_VERCEL else (BASE_DIR / ".jev_cache")

if ENCOVI_JEV_DIR.is_dir() and str(ENCOVI_JEV_DIR) not in sys.path:
    sys.path.insert(0, str(ENCOVI_JEV_DIR))

try:
    from audit import run_audit
    from calibration import MIN_LABELS as CALIBRATION_MIN_LABELS, Calibrator, fit_from_records
    from jev_client import DEFAULT_MODEL, FakeJev, JevClient, JevError
    from rules import Instruction, Kind, Question, Scope, Section, calibration_group, question_registry
    from rules_a1_a2 import SECTIONS
    from scoring import (
        FLAG_NO,
        FLAG_YES,
        InstructionResult,
        Outcome,
        estimate_duration_hours,
        section_summary,
    )
    from transcript import INTERVIEWER, OTHER, RESPONDENT, Turn, normalize_speaker

    JEV_IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover
    DEFAULT_MODEL = "typesafe/jev-1.14"
    CALIBRATION_MIN_LABELS = 30
    INTERVIEWER, RESPONDENT, OTHER = "ENCUESTADOR", "INFORMANTE", "OTRA_PERSONA"
    JEV_IMPORT_ERROR = str(exc)

VALID_ROLES = (INTERVIEWER, RESPONDENT, OTHER)

# Length-invariant conduct thresholds (clearly flagged windows per hour, v_w >= 0.70)
CONDUCT_FLAGGED_PER_HOUR_HIGH_COMPLIANCE = 0.5
CONDUCT_FLAGGED_PER_HOUR_ACCEPTABLE = 2.5

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
        except (json.JSONDecodeError, RecursionError) as exc:  # deeply nested JSON -> RecursionError
            raise ValueError(f"El archivo JSON no es válido: {type(exc).__name__}") from exc

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


# =====================================================================
# Editable Rules Catalog & Dynamic Section Builder
# =====================================================================

def _default_instruction_map() -> dict[str, Instruction]:
    if not is_jev_available():
        return {}
    return {ins.id: ins for sec in SECTIONS for ins in sec.instructions}


def _question_to_dict(
    q: Question,
    override_q: Mapping[str, Any] | None = None,
    *,
    is_trigger: bool = False,
) -> dict[str, Any]:
    ov_instr = str((override_q or {}).get("instructions") or "").strip()
    ov_crit = (override_q or {}).get("criteria") or {}
    merged_crit = dict(q.criteria)
    if isinstance(ov_crit, Mapping):
        for k in list(merged_crit.keys()):
            if k in ov_crit and str(ov_crit[k] or "").strip():
                merged_crit[k] = str(ov_crit[k]).strip()

    return {
        "key": q.key,
        "type": q.type,
        "is_trigger": is_trigger,
        "instructions": ov_instr or q.instructions,
        "criteria": merged_crit,
        "roles": dict(q.roles),
        "default_instructions": q.instructions,
        "default_criteria": dict(q.criteria),
    }


def serialize_rules_catalog(overrides: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Return all 51 ENCOVI A1–A2 rules with both active customized fields and original defaults."""
    if not is_jev_available():
        return []
    overrides = overrides or {}
    catalog: list[dict[str, Any]] = []

    for sec in SECTIONS:
        for ins in sec.instructions:
            ov = overrides.get(ins.id) or {}
            q_ovs = ov.get("questions_override") or {}
            custom_text = str(ov.get("custom_text") or "").strip()
            raw_weight = ov.get("weight")
            weight = int(raw_weight) if raw_weight in (1, 2, 3) else ins.weight
            enabled = bool(ov.get("enabled", True))
            guidance = str(ov.get("auditor_guidance") or "").strip()

            questions_serialized: list[dict[str, Any]] = []
            if ins.trigger is not None:
                questions_serialized.append(
                    _question_to_dict(
                        ins.trigger,
                        q_ovs.get(ins.trigger.key) if isinstance(q_ovs, Mapping) else None,
                        is_trigger=True,
                    )
                )
            for q in ins.questions:
                questions_serialized.append(
                    _question_to_dict(
                        q,
                        q_ovs.get(q.key) if isinstance(q_ovs, Mapping) else None,
                        is_trigger=False,
                    )
                )

            has_q_diff = any(
                qs["instructions"] != qs["default_instructions"]
                or qs["criteria"] != qs["default_criteria"]
                for qs in questions_serialized
            )
            is_customized = bool(
                ov
                and (
                    (custom_text and custom_text != ins.text)
                    or weight != ins.weight
                    or not enabled
                    or bool(guidance)
                    or has_q_diff
                )
            )

            catalog.append(
                {
                    "id": ins.id,
                    "section": ins.section,
                    "section_title": sec.title,
                    "text": custom_text or ins.text,
                    "default_text": ins.text,
                    "pages": ins.pages,
                    "kind": ins.kind.value,
                    "scope": ins.scope.value,
                    "weight": weight,
                    "default_weight": ins.weight,
                    "verifiability": ins.verifiability,
                    "note": ins.note,
                    "enabled": enabled,
                    "auditor_guidance": guidance,
                    "is_customized": is_customized,
                    "updated_at": ov.get("updated_at"),
                    "questions": questions_serialized,
                }
            )

    return catalog


def _customize_question(
    ins_id: str,
    q: Question,
    q_ovs: Mapping[str, Any],
    guidance: str,
) -> Question:
    q_ov = q_ovs.get(q.key) if isinstance(q_ovs, Mapping) else None
    base_instr = str((q_ov or {}).get("instructions") or "").strip() or q.instructions
    eff_instr = f"{base_instr}\nCriterio adicional del auditor: {guidance}" if guidance else base_instr

    eff_crit = dict(q.criteria)
    if isinstance(q_ov, Mapping) and isinstance(q_ov.get("criteria"), Mapping):
        for ck in list(eff_crit.keys()):
            val = str(q_ov["criteria"].get(ck) or "").strip()
            if val:
                eff_crit[ck] = val

    changed = eff_instr != q.instructions or eff_crit != dict(q.criteria)
    eff_key = f"{ins_id.replace('-', '_')}__custom__{q.key}" if changed else q.key
    return Question(
        key=eff_key,
        type=q.type,
        instructions=eff_instr,
        criteria=eff_crit,
        roles=dict(q.roles),
    )


def build_effective_sections(
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[tuple[Section, ...], dict[str, dict[str, Any]]]:
    """Build Section/Instruction/Question objects incorporating global rule rewrites and two-stage triggers."""
    overrides = overrides or {}
    catalog_by_id = {item["id"]: item for item in serialize_rules_catalog(overrides)}
    built_sections: list[Section] = []

    for sec in SECTIONS:
        new_instructions: list[Instruction] = []
        for ins in sec.instructions:
            meta = catalog_by_id.get(ins.id)
            if meta and not meta["enabled"]:
                continue

            ov = overrides.get(ins.id) or {}
            q_ovs = ov.get("questions_override") if isinstance(ov.get("questions_override"), Mapping) else {}
            guidance = str(ov.get("auditor_guidance") or "").strip()
            custom_text = str(ov.get("custom_text") or "").strip() or ins.text
            raw_w = ov.get("weight")
            weight = int(raw_w) if raw_w in (1, 2, 3) else ins.weight

            eff_trigger = (
                _customize_question(ins.id, ins.trigger, q_ovs, "")
                if ins.trigger is not None
                else None
            )
            new_qs = tuple(_customize_question(ins.id, q, q_ovs, guidance) for q in ins.questions)

            new_instructions.append(
                Instruction(
                    id=ins.id,
                    section=ins.section,
                    text=custom_text,
                    pages=ins.pages,
                    kind=ins.kind,
                    scope=ins.scope,
                    questions=new_qs,
                    weight=weight,
                    verifiability=ins.verifiability,
                    note=ins.note,
                    trigger=eff_trigger,
                )
            )

        if new_instructions:
            built_sections.append(Section(sec.id, sec.title, tuple(new_instructions)))

    return tuple(built_sections), catalog_by_id


# =====================================================================
# Length-Invariant Overall Summary & Verdict
# =====================================================================

def _report_duration_hours(report: Mapping[str, Any]) -> float:
    settings = report.get("settings") or {}
    if isinstance(settings, Mapping) and settings.get("duration_hours"):
        return max(float(settings["duration_hours"]), 1.0 / 60.0)
    window_times: dict[int, Any] = {}
    total_bytes = 0
    for w in report.get("windows") or []:
        if isinstance(w, Mapping) and "window" in w:
            window_times[int(w["window"])] = w.get("time")
            total_bytes += int(w.get("bytes") or 0)
    return max(estimate_duration_hours(window_times, total_bytes=total_bytes or None), 1.0 / 60.0)


def _build_overall_summary(report: dict[str, Any]) -> dict[str, Any]:
    sections = report.get("sections") or {}
    instructions = report.get("instructions") or []
    dur_hours = _report_duration_hours(report)

    total_n = len(instructions)
    sum_c = sum(float(ins.get("p_followed") or 0.0) for ins in instructions)
    sum_v = sum(float(ins.get("p_broken") or 0.0) for ins in instructions)
    applicable = sum_c + sum_v

    w_c = sum(float(ins.get("weight") or 1) * float(ins.get("p_followed") or 0.0) for ins in instructions)
    w_app = sum(
        float(ins.get("weight") or 1)
        * (float(ins.get("p_followed") or 0.0) + float(ins.get("p_broken") or 0.0))
        for ins in instructions
    )

    rate = round(sum_c / applicable, 4) if applicable > 1e-9 else None
    weighted_rate = round(w_c / w_app, 4) if w_app > 1e-9 else None
    coverage = round(applicable / total_n, 4) if total_n else None

    conduct_flagged_windows = sum(
        int(ins.get("windows_flagged") or 0)
        for ins in instructions
        if ins.get("kind") == "prohibition" and ins.get("scope") == "all"
    )
    conduct_flagged_per_hour = round(conduct_flagged_windows / dur_hours, 2)

    flagged_windows_total = sum(
        int(ins.get("windows_flagged") or 0)
        for ins in instructions
        if ins.get("scope") == "all"
    )
    flagged_windows_per_hour = round(flagged_windows_total / dur_hours, 2)

    procedural_high_risk_count = 0
    conduct_flagged_rules_count = 0
    review_count = 0

    for ins in instructions:
        is_conduct = ins.get("kind") == "prohibition" and ins.get("scope") == "all"
        p_b = float(ins.get("p_broken") or 0.0)
        wf = int(ins.get("windows_flagged") or 0)
        wr = int(ins.get("windows_review") or 0)
        if is_conduct:
            if wf > 0:
                conduct_flagged_rules_count += 1
            elif wr > 0 or p_b >= FLAG_NO:
                review_count += 1
        else:
            if p_b >= FLAG_YES or wf > 0:
                procedural_high_risk_count += 1
            elif p_b >= FLAG_NO or wr > 0:
                review_count += 1

    high_risk_count = procedural_high_risk_count + conduct_flagged_rules_count
    manual_edit_count = sum(1 for ins in instructions if ins.get("manual_override"))

    # Length-invariant verdict: combines compliance rate on applicable rules with clearly flagged conduct windows/hr
    score_ref = weighted_rate if weighted_rate is not None else rate
    if score_ref is None and conduct_flagged_windows == 0:
        verdict = {"label": "Sin evidencia suficiente", "level": "muted"}
    elif (
        (score_ref is None or score_ref >= 0.90)
        and procedural_high_risk_count == 0
        and conduct_flagged_per_hour < CONDUCT_FLAGGED_PER_HOUR_HIGH_COMPLIANCE
    ):
        verdict = {"label": "Cumplimiento alto", "level": "ok"}
    elif (
        (score_ref is None or score_ref >= 0.75)
        and procedural_high_risk_count <= 2
        and conduct_flagged_per_hour < CONDUCT_FLAGGED_PER_HOUR_ACCEPTABLE
    ):
        verdict = {"label": "Aceptable con observaciones", "level": "warn"}
    else:
        verdict = {"label": "Requiere revisión prioritaria", "level": "danger"}

    all_risks: list[dict[str, Any]] = []
    for sid, sec in sections.items():
        for risk in sec.get("top_risks") or []:
            matching_ins = next((i for i in instructions if i.get("id") == risk.get("id")), None)
            all_risks.append(
                {
                    **risk,
                    "section": sid,
                    "section_title": sec.get("title", sid),
                    "manual_override": matching_ins.get("manual_override") if matching_ins else None,
                    "is_rule_customized": bool(matching_ins.get("is_rule_customized")) if matching_ins else False,
                }
            )
    all_risks.sort(key=lambda r: -float(r.get("p_broken") or 0.0))

    return {
        "n_instructions": total_n,
        "compliance_rate": rate,
        "compliance_rate_weighted": weighted_rate,
        "expected_followed": round(sum_c, 2),
        "expected_broken": round(sum_v, 2),
        "coverage": coverage,
        "duration_hours": round(dur_hours, 4),
        "conduct_flagged_windows": conduct_flagged_windows,
        "conduct_flagged_per_hour": conduct_flagged_per_hour,
        "flagged_windows_total": flagged_windows_total,
        "flagged_windows_per_hour": flagged_windows_per_hour,
        "procedural_high_risk_count": procedural_high_risk_count,
        "high_risk_count": high_risk_count,
        "review_count": review_count,
        "manual_edit_count": manual_edit_count,
        "verdict": verdict,
        "top_risks": all_risks[:10],
    }


# =====================================================================
# Supervisor Overrides + Gold-Label Extraction for Calibration
# =====================================================================

def extract_calibration_records_for_edit(
    evaluation: Mapping[str, Any],
    *,
    rule_id: str,
    override_status: str,
    window_index: int | None = None,
) -> list[dict[str, Any]]:
    """Extract (window, question_key, group, question_type, raw_prob, gold_label) records from a supervisor edit."""
    if not is_jev_available():
        return []
    status_clean = override_status.strip().lower()
    if status_clean not in {"followed", "broken", "unknown", "reset"}:
        return []

    default_map = _default_instruction_map()
    base_ins = default_map.get(rule_id)
    if base_ins is None:
        return []

    instructions = evaluation.get("instructions") or []
    target_ins = next((i for i in instructions if i.get("id") == rule_id), None)
    if target_ins is None:
        return []

    # Resolve target window
    if window_index is not None:
        w_idx = int(window_index)
    elif isinstance(target_ins.get("worst_window"), Mapping) and target_ins["worst_window"].get("window") is not None:
        w_idx = int(target_ins["worst_window"]["window"])
    elif target_ins.get("windows"):
        w_idx = int(target_ins["windows"][0]["window"])
    else:
        w_idx = 0

    raw_answers = evaluation.get("raw_answers") or {}
    raw_window = raw_answers.get(str(w_idx)) or {}
    model_version = str(evaluation.get("model") or DEFAULT_MODEL)
    is_mock = bool(evaluation.get("mock", False))
    prefix = f"{rule_id.replace('-', '_')}__custom__"

    def _find_raw(q_key: str) -> tuple[str, dict[str, Any] | None]:
        custom_key = f"{prefix}{q_key}"
        if custom_key in raw_window:
            return custom_key, raw_window[custom_key]
        if q_key in raw_window:
            return q_key, raw_window[q_key]
        return q_key, None

    records: list[dict[str, Any]] = []

    def _add_noul(q_key: str, group: str, raw_ans: Mapping[str, Any] | None, label: str | None) -> None:
        if not raw_ans or raw_ans.get("type") != "noul":
            return
        raw_p = round(float(raw_ans["noul"]), 6)
        records.append(
            {
                "window_index": w_idx,
                "question_key": q_key,
                "question_type": "noul",
                "calibration_group": group,
                "raw_probability": raw_p,
                "raw_probabilities": {"noul": raw_p},
                "gold_label": label,
                "model_version": model_version,
                "is_mock": is_mock,
            }
        )

    def _add_choice(
        q_key: str,
        group: str,
        raw_ans: Mapping[str, Any] | None,
        roles: Mapping[str, str],
        label_role: str | None,
    ) -> None:
        if not raw_ans or raw_ans.get("type") != "choice":
            return
        probs = raw_ans.get("probabilities") or {}
        if not isinstance(probs, Mapping) or not probs:
            return
        clean_probs = {str(k): round(float(v), 6) for k, v in probs.items()}
        broken_opt = roles.get("broken")
        raw_scalar = clean_probs.get(broken_opt, max(clean_probs.values())) if broken_opt else max(clean_probs.values())
        gold_opt = roles.get(label_role) if label_role else None
        records.append(
            {
                "window_index": w_idx,
                "question_key": q_key,
                "question_type": "choice",
                "calibration_group": group,
                "raw_probability": round(float(raw_scalar), 6),
                "raw_probabilities": clean_probs,
                "gold_label": gold_opt,
                "model_version": model_version,
                "is_mock": is_mock,
            }
        )

    if base_ins.kind is Kind.OBLIGATION:
        found = [(_find_raw(q.key)) for q in base_ins.questions]
        valid = [(k, a) for k, a in found if a and a.get("type") == "noul"]
        if status_clean == "reset":
            for k, a in valid:
                _add_noul(k, "obligation", a, None)
        elif status_clean == "followed":
            for k, a in valid:
                _add_noul(k, "obligation", a, "1")
        elif status_clean == "broken" and valid:
            # For multi-part obligations, label the part JEV rated lowest (avoid mislabeling the satisfied part)
            failing_k, failing_a = min(valid, key=lambda ka: float(ka[1]["noul"]))
            _add_noul(failing_k, "obligation", failing_a, "0")

    elif base_ins.kind is Kind.PROHIBITION:
        found = [(_find_raw(q.key)) for q in base_ins.questions]
        valid = [(k, a) for k, a in found if a and a.get("type") == "noul"]
        if status_clean == "reset":
            for k, a in valid:
                _add_noul(k, "prohibition", a, None)
        elif status_clean == "followed":
            # For prohibition, noul=1 means violation happened; followed means NO violation (0)
            for k, a in valid:
                _add_noul(k, "prohibition", a, "0")
        elif status_clean == "broken" and valid:
            violating_k, violating_a = max(valid, key=lambda ka: float(ka[1]["noul"]))
            _add_noul(violating_k, "prohibition", violating_a, "1")

    elif base_ins.kind is Kind.CONDITIONAL:
        if base_ins.trigger is not None:
            tk, ta = _find_raw(base_ins.trigger.key)
            if status_clean == "reset":
                _add_noul(tk, "trigger", ta, None)
            elif status_clean == "unknown":
                _add_noul(tk, "trigger", ta, "0")
            elif status_clean in {"followed", "broken"}:
                _add_noul(tk, "trigger", ta, "1")

        q = base_ins.questions[0]
        qk, qa = _find_raw(q.key)
        if qa and qa.get("type") == "choice":
            _add_choice(qk, "conditional", qa, q.roles, None if status_clean == "reset" else status_clean)

    elif base_ins.kind is Kind.EVIDENCE:
        q = base_ins.questions[0]
        qk, qa = _find_raw(q.key)
        if qa and qa.get("type") == "choice":
            _add_choice(qk, "evidence", qa, q.roles, None if status_clean == "reset" else status_clean)

    return records


def fit_calibration_from_edits(
    edits: Sequence[Mapping[str, Any]],
    *,
    model_version: str = DEFAULT_MODEL,
    min_labels: int = CALIBRATION_MIN_LABELS,
    include_mock: bool = False,
) -> dict[str, Any]:
    """Deduplicate supervisor edit records by (job_id, window_index, question_key) and fit Platt/temp calibration."""
    if not is_jev_available():
        return {
            "model_version": model_version,
            "min_labels": min_labels,
            "total_labels": 0,
            "is_calibrated": False,
            "calibrator": {"noul_platt": {}, "choice_temperature": {}},
            "groups": {},
        }

    # Latest supervisor label wins for each (job_id, window_index, question_key); reset (gold_label=None) removes it
    latest_by_key: dict[tuple[str, int, str], Mapping[str, Any]] = {}
    for row in edits:
        if not include_mock and row.get("is_mock"):
            continue
        row_model = row.get("model_version")
        if model_version and row_model and row_model != model_version:
            continue
        qkey = row.get("question_key")
        w_idx = row.get("window_index")
        job_id = row.get("job_id")
        if not qkey or w_idx is None or not job_id:
            continue
        dedup_k = (str(job_id), int(w_idx), str(qkey))
        if row.get("override_status") == "reset" or row.get("gold_label") in (None, ""):
            latest_by_key.pop(dedup_k, None)
        else:
            latest_by_key[dedup_k] = row

    fit_rows: list[dict[str, Any]] = []
    for row in latest_by_key.values():
        qtype = str(row.get("question_type") or "").lower()
        group = str(row.get("calibration_group") or "").strip()
        label = row.get("gold_label")
        if qtype == "noul":
            raw_val: Any = row.get("raw_probability")
            if raw_val is None and isinstance(row.get("raw_probabilities"), Mapping):
                raw_val = row["raw_probabilities"].get("noul")
        elif qtype == "choice":
            raw_val = row.get("raw_probabilities")
        else:
            continue
        if raw_val is None or not group or label in (None, ""):
            continue
        fit_rows.append(
            {
                "group": group,
                "question_type": qtype,
                "raw": raw_val,
                "label": label,
            }
        )

    calibrator, report = fit_from_records(fit_rows, min_labels=min_labels)
    return {
        "model_version": model_version,
        "min_labels": min_labels,
        "total_labels": len(fit_rows),
        "is_calibrated": calibrator.is_fitted,
        "calibrator": calibrator.to_dict(),
        "groups": report,
    }


def apply_instruction_override(
    evaluation: Mapping[str, Any],
    *,
    rule_id: str,
    override_status: str,
    custom_probs: Mapping[str, float] | None = None,
    auditor_comment: str | None = None,
    window_index: int | None = None,
    new_weight: int | None = None,
    new_text: str | None = None,
    is_rule_customized: bool | None = None,
    auditor_guidance: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Apply or reset a human override on one instruction in an existing JEV evaluation and recompute all KPIs."""
    if not is_jev_available():
        raise RuntimeError("El motor encovi_jev no está disponible.")

    report = copy.deepcopy(dict(evaluation))
    instructions: list[dict[str, Any]] = list(report.get("instructions") or [])
    target = next((ins for ins in instructions if ins.get("id") == rule_id), None)
    if target is None:
        raise ValueError(f"No se encontró la regla '{rule_id}' en esta evaluación.")

    prev_outcome = {
        "p_followed": float(target.get("p_followed") or 0.0),
        "p_broken": float(target.get("p_broken") or 0.0),
        "p_unknown": float(target.get("p_unknown") or 0.0),
    }

    if "original_outcome" not in target:
        target["original_outcome"] = dict(prev_outcome)
    if "original_windows" not in target:
        target["original_windows"] = copy.deepcopy(target.get("windows") or [])

    status_clean = override_status.strip().lower()
    if status_clean == "followed":
        out = Outcome.make(1.0, 0.0, 0.0)
    elif status_clean == "broken":
        out = Outcome.make(0.0, 1.0, 0.0)
    elif status_clean == "unknown":
        out = Outcome.make(0.0, 0.0, 1.0)
    elif status_clean == "custom":
        cp = custom_probs or {}
        out = Outcome.make(
            float(cp.get("p_followed", prev_outcome["p_followed"])),
            float(cp.get("p_broken", prev_outcome["p_broken"])),
            float(cp.get("p_unknown", prev_outcome["p_unknown"])),
        )
    elif status_clean == "reset":
        orig = target.get("original_outcome") or prev_outcome
        out = Outcome.make(
            float(orig.get("p_followed") or 0.0),
            float(orig.get("p_broken") or 0.0),
            float(orig.get("p_unknown") or 0.0),
        )
    elif status_clean == "keep":
        out = Outcome.make(
            prev_outcome["p_followed"],
            prev_outcome["p_broken"],
            prev_outcome["p_unknown"],
        )
    else:
        raise ValueError(
            f"Estado de corrección inválido: '{override_status}'. Usa followed, broken, unknown, custom, keep o reset."
        )

    dur_hours = _report_duration_hours(report)
    window_times: dict[int, Any] = {}
    for w_info in report.get("windows") or []:
        if isinstance(w_info, Mapping) and "window" in w_info:
            window_times[int(w_info["window"])] = w_info.get("time")

    # Keep per-window outcomes synchronized so windows_flagged and flagged_per_hour update immediately
    if status_clean == "reset":
        target["windows"] = copy.deepcopy(target.get("original_windows") or [])
    elif status_clean in {"followed", "broken", "unknown", "custom"}:
        win_list = list(target.get("windows") or [])
        if win_list:
            if status_clean in {"followed", "unknown"} and window_index is None:
                # Clearing a conduct/conditional rule at interview level clears flagged windows cleanly
                for w_entry in win_list:
                    w_entry["followed"] = round(out.followed, 4)
                    w_entry["broken"] = round(out.broken, 4)
                    w_entry["unknown"] = round(out.unknown, 4)
            else:
                target_w = (
                    int(window_index)
                    if window_index is not None
                    else int((target.get("worst_window") or {}).get("window", win_list[0]["window"]))
                )
                for w_entry in win_list:
                    if int(w_entry["window"]) == target_w:
                        w_entry["followed"] = round(out.followed, 4)
                        w_entry["broken"] = round(out.broken, 4)
                        w_entry["unknown"] = round(out.unknown, 4)
            target["windows"] = win_list

    target["p_followed"] = round(out.followed, 4)
    target["p_broken"] = round(out.broken, 4)
    target["p_unknown"] = round(out.unknown, 4)
    f_if_app = out.followed_if_applicable()
    target["p_followed_if_applicable"] = round(f_if_app, 4) if f_if_app is not None else None

    if target.get("scope") == "all":
        win_list = target.get("windows") or []
        flagged = sum(1 for w in win_list if float(w.get("broken") or 0.0) >= FLAG_YES)
        review = sum(1 for w in win_list if FLAG_NO <= float(w.get("broken") or 0.0) < FLAG_YES)
        if not win_list:
            flagged = 1 if out.broken >= FLAG_YES else 0
            review = 1 if FLAG_NO <= out.broken < FLAG_YES else 0
        target["windows_flagged"] = flagged
        target["windows_review"] = review
        target["flagged_per_hour"] = round(flagged / dur_hours, 2)
        if win_list:
            worst_w = max(win_list, key=lambda w: float(w.get("broken") or 0.0))
            target["worst_window"] = {
                "window": int(worst_w["window"]),
                "p_broken": round(float(worst_w.get("broken") or 0.0), 4),
                "time": window_times.get(int(worst_w["window"])),
            }

    if new_weight in (1, 2, 3):
        target["weight"] = int(new_weight)
    if new_text and new_text.strip():
        target["text"] = new_text.strip()
    if is_rule_customized is not None:
        target["is_rule_customized"] = bool(is_rule_customized)
    if auditor_guidance is not None:
        target["auditor_guidance"] = auditor_guidance.strip()

    comment_clean = (auditor_comment or "").strip()
    if status_clean == "reset":
        target.pop("manual_override", None)
    elif status_clean != "keep" or comment_clean:
        existing_mo = target.get("manual_override") or {}
        eff_status = status_clean if status_clean != "keep" else existing_mo.get("status", "custom")
        target["manual_override"] = {
            "status": eff_status,
            "comment": comment_clean if auditor_comment is not None else existing_mo.get("comment", ""),
        }

    # Recompute exact section summaries using encovi_jev/scoring.py
    default_map = _default_instruction_map()
    sections_dict = report.get("sections") or {}
    new_sections: dict[str, Any] = {}
    for sec in SECTIONS:
        sec_ins_dicts = [i for i in instructions if i.get("section") == sec.id]
        if not sec_ins_dicts:
            continue
        sec_results: list[InstructionResult] = []
        for item in sec_ins_dicts:
            base_ins = default_map.get(str(item.get("id")))
            if base_ins is None:
                continue
            w_val = int(item.get("weight") or base_ins.weight)
            w_val = w_val if w_val in (1, 2, 3) else base_ins.weight
            eff_ins = Instruction(
                id=base_ins.id,
                section=base_ins.section,
                text=str(item.get("text") or base_ins.text),
                pages=base_ins.pages,
                kind=base_ins.kind,
                scope=base_ins.scope,
                questions=base_ins.questions,
                weight=w_val,
                verifiability=base_ins.verifiability,
                note=base_ins.note,
                trigger=base_ins.trigger,
            )
            item_out = Outcome.make(
                float(item.get("p_followed") or 0.0),
                float(item.get("p_broken") or 0.0),
                float(item.get("p_unknown") or 0.0),
            )
            per_w: list[tuple[int, Outcome]] = []
            for w_entry in item.get("windows") or []:
                per_w.append(
                    (
                        int(w_entry["window"]),
                        Outcome.make(
                            float(w_entry.get("followed") or 0.0),
                            float(w_entry.get("broken") or 0.0),
                            float(w_entry.get("unknown") or 0.0),
                        ),
                    )
                )
            if not per_w:
                ww = item.get("worst_window")
                if isinstance(ww, Mapping) and ww.get("window") is not None:
                    per_w.append((int(ww["window"]), item_out))
            sec_results.append(InstructionResult(eff_ins, item_out, per_w))

        sec_title = (sections_dict.get(sec.id) or {}).get("title") or sec.title
        new_sections[sec.id] = section_summary(
            sec_results, sec_title, window_times, duration_hours=dur_hours
        )

    report["instructions"] = instructions
    report["sections"] = new_sections
    report["overall"] = _build_overall_summary(report)

    new_outcome = {
        "p_followed": target["p_followed"],
        "p_broken": target["p_broken"],
        "p_unknown": target["p_unknown"],
    }
    return report, prev_outcome, new_outcome


def _friendly_jev_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "no api key" in low or "openrouter_api_key" in low:
        return (
            "Falta configurar OPENROUTER_API_KEY en las variables de entorno (o en el panel superior) "
            "para llamar al modelo JEV en OpenRouter."
        )
    if "http 401" in low or "unauthorized" in low or ("invalid" in low and "key" in low):
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
    rule_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    calibration_data: Mapping[str, Any] | Calibrator | None = None,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    """Run ENCOVI A1–A2 JEV evaluation with custom rules, two-stage conditional gating, and active calibration."""
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

    effective_sections, catalog_by_id = build_effective_sections(rule_overrides)
    if not effective_sections:
        raise ValueError("Todas las reglas de evaluación están desactivadas. Activa al menos una regla.")

    # Load fitted supervisor Calibrator (falls back to identity when no group has >= 30 labels yet)
    if isinstance(calibration_data, Calibrator):
        calibrator = calibration_data
        cal_meta = {
            "is_calibrated": calibrator.is_fitted,
            "fitted_groups": sorted(
                [f"noul/{g}" for g in calibrator.noul_params]
                + [f"choice/{g}" for g in calibrator.choice_params]
            ),
            "total_labels": None,
            "min_labels": CALIBRATION_MIN_LABELS,
        }
    elif isinstance(calibration_data, Mapping):
        raw_cal = calibration_data.get("calibrator", calibration_data)
        calibrator = Calibrator.from_dict(raw_cal if isinstance(raw_cal, Mapping) else None)
        cal_meta = {
            "is_calibrated": calibrator.is_fitted,
            "fitted_groups": sorted(
                [f"noul/{g}" for g in calibrator.noul_params]
                + [f"choice/{g}" for g in calibrator.choice_params]
            ),
            "total_labels": calibration_data.get("total_labels", 0),
            "min_labels": calibration_data.get("min_labels", CALIBRATION_MIN_LABELS),
        }
    else:
        calibrator = Calibrator()
        cal_meta = {
            "is_calibrated": False,
            "fitted_groups": [],
            "total_labels": 0,
            "min_labels": CALIBRATION_MIN_LABELS,
        }

    if mock:
        reg = question_registry(effective_sections)
        client = FakeJev(
            {k: calibration_group(k, effective_sections) for k in reg},
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
            effective_sections,
            first_contact=first_contact,
            calibrator=calibrator,
            duration_seconds=duration_seconds,
        )
    except JevError as exc:
        raise RuntimeError(_friendly_jev_error(exc)) from exc

    report.pop("_windows_text", None)
    report["mock"] = bool(mock)
    report["speaker_map"] = clean_map
    report["calibration"] = cal_meta
    if mock:
        report["warning"] = (
            "Modo prueba sin conexión: estas probabilidades son simuladas y no reflejan una evaluación real."
        )

    customized_applied = 0
    for ins_dict in report.get("instructions") or []:
        rid = str(ins_dict.get("id") or "")
        cat = catalog_by_id.get(rid)
        ins_dict["original_outcome"] = {
            "p_followed": ins_dict.get("p_followed"),
            "p_broken": ins_dict.get("p_broken"),
            "p_unknown": ins_dict.get("p_unknown"),
        }
        ins_dict["original_windows"] = copy.deepcopy(ins_dict.get("windows") or [])
        if cat:
            ins_dict["is_rule_customized"] = bool(cat.get("is_customized"))
            ins_dict["auditor_guidance"] = cat.get("auditor_guidance") or ""
            if cat.get("is_customized"):
                customized_applied += 1

    report["customized_rules_applied"] = customized_applied
    report["overall"] = _build_overall_summary(report)
    return report
