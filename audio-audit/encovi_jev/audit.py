"""Audit one interview transcript against sections A1 and A2 with Jev (OpenRouter Decisions API).

    export OPENROUTER_API_KEY=...
    python audit.py transcripcion.json --out reporte.json
    python audit.py examples/transcript_example.json --mock          # offline plumbing test, FAKE scores
    python audit.py t.json --export-labels labels/                    # template for gold labels
    python audit.py t.json --calibration calibration.json             # after calibration.py fit
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from calibration import Calibrator
from jev_client import DEFAULT_MODEL, FakeJev, JevClient, body_bytes
from rules import (
    GATES,
    Kind,
    Question,
    Scope,
    Section,
    calibration_group,
    question_registry,
    questions_for_scopes,
)
from rules_a1_a2 import SECTIONS
from scoring import (
    TRIGGER_THRESHOLD,
    estimate_duration_hours,
    evaluate_instruction,
    section_summary,
    trigger_probability,
)
from transcript import Window, load_transcript, make_windows

STATE_DESCRIPTION = (
    "Fragmento de la transcripción automática de una visita de la Encuesta Nacional de Condiciones de Vida "
    "(ENCOVI 2023) del INE de Guatemala. ENCUESTADOR es quien aplica la encuesta; INFORMANTE es la persona del "
    "hogar que responde; OTRA_PERSONA es cualquier otra voz."
)


@dataclass(frozen=True)
class Batch:
    window: int
    state: dict
    questions: dict   # question key -> payload


def build_state(window: Window, n_windows: int) -> dict:
    pos = f"Fragmento {window.index + 1} de {n_windows}."
    if window.index == 0:
        pos += " Empieza al inicio de la grabación."
    if window.index == n_windows - 1:
        pos += " Termina al final de la grabación."
    return {"descripcion": STATE_DESCRIPTION, "posicion": pos, "transcripcion": window.text}


def _pack_window_questions(
    window: Window,
    n_windows: int,
    questions: Sequence[Question],
    model: str,
    max_request_bytes: int,
) -> list[Batch]:
    batches: list[Batch] = []
    state = build_state(window, n_windows)
    current: dict = {}
    for q in questions:
        trial = {**current, q.key: q.payload()}
        if current and body_bytes({"model": model, "state": state, "questions": trial}) > max_request_bytes:
            batches.append(Batch(window.index, state, current))
            trial = {q.key: q.payload()}
        if body_bytes({"model": model, "state": state, "questions": trial}) > max_request_bytes:
            raise ValueError(
                f"window {window.index}: state plus question {q.key} exceeds {max_request_bytes} "
                f"bytes; lower --window-bytes"
            )
        current = trial
    if current:
        batches.append(Batch(window.index, state, current))
    return batches


def plan_batches(
    windows: Sequence[Window],
    sections: Sequence[Section],
    model: str,
    max_request_bytes: int,
    *,
    stage1_only: bool = True,
) -> list[Batch]:
    """Pack Stage-1 questions for each window so no request body exceeds max_request_bytes.

    Keeping bodies under ~32,000 bytes keeps Jev in its default mode: OpenRouter switches to the
    slower, less accurate long-context mode above about that size.
    """
    batches: list[Batch] = []
    for w in windows:
        qs = questions_for_scopes(sections, w.scopes, stage1_only=stage1_only)
        batches.extend(_pack_window_questions(w, len(windows), qs, model, max_request_bytes))
    return batches


def plan_stage2_batches(
    windows: Sequence[Window],
    sections: Sequence[Section],
    stage1_answers: dict[int, dict[str, dict]],
    calibrator: Calibrator,
    model: str,
    max_request_bytes: int,
    *,
    trigger_threshold: float = TRIGGER_THRESHOLD,
) -> list[Batch]:
    """Pack Stage-2 response questions ONLY for (window, conditional rule) pairs whose trigger fired."""
    batches: list[Batch] = []
    for w in windows:
        w_ans = stage1_answers.get(w.index, {})
        to_ask: dict[str, Question] = {}
        for sec in sections:
            for ins in sec.instructions:
                if ins.kind is not Kind.CONDITIONAL or ins.trigger is None:
                    continue
                if ins.scope not in w.scopes:
                    continue
                p_t = trigger_probability(ins, w_ans, calibrator)
                if p_t is not None and p_t >= trigger_threshold:
                    for q in ins.questions:
                        to_ask.setdefault(q.key, q)
        if to_ask:
            batches.extend(
                _pack_window_questions(w, len(windows), list(to_ask.values()), model, max_request_bytes)
            )
    return batches


def _average(answers: Sequence[dict]) -> dict:
    """Mean of repeated answers to the same question (refusals dropped)."""
    good = [a for a in answers if a.get("type") != "refusal"]
    if not good:
        return {"type": "refusal"}
    if good[0]["type"] == "noul":
        return {"type": "noul", "noul": sum(a["noul"] for a in good) / len(good)}
    keys = set().union(*(a["probabilities"] for a in good))
    probs = {k: sum(a["probabilities"].get(k, 0.0) for a in good) / len(good) for k in keys}
    return {"type": "choice", "probabilities": probs, "choice": max(probs, key=probs.get)}


def _run_batches(
    batches: Sequence[Batch],
    client: Any,
    repeats: int,
    workers: int,
    collected: dict[int, dict[str, list]],
) -> None:
    if not batches:
        return
    jobs = [(b, r) for b in batches for r in range(repeats)]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        responses = list(pool.map(lambda job: client.decide(job[0].state, job[0].questions, job[1]), jobs))
    for (batch, _), resp in zip(jobs, responses):
        for key in batch.questions:
            collected.setdefault(batch.window, {}).setdefault(key, []).append(resp["answers"][key])


def run_audit(
    turns,
    client,
    sections: Sequence[Section] = SECTIONS,
    *,
    window_bytes: int = 12_000,
    overlap_turns: int = 2,
    max_request_bytes: int = 30_000,
    first_contact: bool = True,
    calibrator: Calibrator | None = None,
    repeats: int = 1,
    workers: int = 4,
    trigger_threshold: float = TRIGGER_THRESHOLD,
    duration_seconds: float | None = None,
) -> dict:
    calibrator = calibrator or Calibrator()
    model_name = getattr(client, "model", DEFAULT_MODEL)
    windows = make_windows(turns, window_bytes, overlap_turns, first_contact)

    # Stage 1: gates, obligations, prohibitions, evidence, and conditional trigger checks
    stage1_batches = plan_batches(windows, sections, model_name, max_request_bytes, stage1_only=True)
    collected: dict[int, dict[str, list]] = {}
    _run_batches(stage1_batches, client, repeats, workers, collected)
    answers = {w: {k: _average(v) for k, v in qs.items()} for w, qs in collected.items()}

    # Stage 2: judge conditional responses ONLY on windows where Stage-1 trigger fired
    stage2_batches = plan_stage2_batches(
        windows,
        sections,
        answers,
        calibrator,
        model_name,
        max_request_bytes,
        trigger_threshold=trigger_threshold,
    )
    if stage2_batches:
        _run_batches(stage2_batches, client, repeats, workers, collected)
        answers = {w: {k: _average(v) for k, v in qs.items()} for w, qs in collected.items()}

    scopes = {w.index: w.scopes for w in windows}
    gates: dict[Scope, float | None] = {}
    for scope, gate in GATES.items():
        idx = [w.index for w in windows if scope in w.scopes]
        a = answers.get(idx[0], {}).get(gate.key) if idx else None
        gates[scope] = calibrator.noul(a["noul"], "gate") if a and a.get("type") == "noul" else None

    times = {w.index: [w.start, w.end] for w in windows}
    total_bytes = sum(w.n_bytes for w in windows)
    dur_hours = estimate_duration_hours(times, duration_seconds=duration_seconds, total_bytes=total_bytes)

    instructions, sections_out = [], {}
    for sec in sections:
        results = [
            evaluate_instruction(
                i,
                answers,
                scopes,
                gates,
                calibrator,
                trigger_threshold=trigger_threshold,
            )
            for i in sec.instructions
        ]
        sections_out[sec.id] = section_summary(results, sec.title, times, duration_hours=dur_hours)
        instructions += [r.to_dict(times, duration_hours=dur_hours) for r in results]

    return {
        "model": getattr(client, "model", None),
        "settings": {
            "window_bytes": window_bytes,
            "overlap_turns": overlap_turns,
            "repeats": repeats,
            "max_request_bytes": max_request_bytes,
            "first_contact": first_contact,
            "trigger_threshold": trigger_threshold,
            "duration_hours": round(dur_hours, 4),
            "stage1_requests": len(stage1_batches),
            "stage2_requests": len(stage2_batches),
            "calibrated": calibrator.to_dict(),
        },
        "windows": [
            {
                "window": w.index,
                "turns": [w.first_turn, w.last_turn],
                "bytes": w.n_bytes,
                "time": times[w.index],
                "scopes": sorted(s.value for s in w.scopes),
            }
            for w in windows
        ],
        "gates": {s.value: g for s, g in gates.items()},
        "sections": sections_out,
        "instructions": instructions,
        "raw_answers": {str(w): a for w, a in answers.items()},
        "usage": client.usage.as_dict(),
        "_windows_text": {w.index: w.text for w in windows},   # dropped before writing the report
    }


def export_label_template(report: dict, sections: Sequence[Section], out_dir: str | Path) -> None:
    """labels_template.csv (one row per window x question, label column empty) + windows.md."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    registry = question_registry(sections)
    with open(out / "labels_template.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["window", "question_key", "group", "question_type", "instructions", "options", "raw", "label"])
        for w, answers in report["raw_answers"].items():
            for key, a in answers.items():
                if a.get("type") == "refusal":
                    continue
                q = registry[key]
                raw = a["noul"] if q.type == "noul" else json.dumps(a["probabilities"], ensure_ascii=False)
                options = "1=sí / 0=no" if q.type == "noul" else " | ".join(q.criteria)
                wr.writerow([w, key, calibration_group(key, sections), q.type, q.instructions, options, raw, ""])
    with open(out / "windows.md", "w", encoding="utf-8") as fh:
        for w, text in report["_windows_text"].items():
            fh.write(f"## Ventana {w}  {report['windows'][w]['time']}\n\n```\n{text}\n```\n\n")


def _fmt(x: Any, pct: bool = True) -> str:
    if x is None:
        return "n/a"
    return f"{x:.0%}" if pct else f"{x:.2f}"


def print_summary(report: dict, name: str) -> None:
    u = report["usage"]
    print(f"{name} | model {report['model']} | {len(report['windows'])} windows | {u['requests']} requests "
          f"({u['cache_hits']} cached) | {u['input_tokens']:,} input tokens | ${u['cost_usd']:.4f}")
    print(f"gates: opening={_fmt(report['gates'].get('opening'))} closing={_fmt(report['gates'].get('closing'))}")
    for sid, s in report["sections"].items():
        print(f"\n{sid} {s['title']} ({s['n_instructions']} instructions)")
        print(f"  compliance rate {_fmt(s['compliance_rate'])} (weighted {_fmt(s['compliance_rate_weighted'])})"
              f" | conduct flagged/hr {s.get('conduct_flagged_per_hour', 0.0):.2f} ({s.get('conduct_flagged_windows', 0)} win)"
              f" | expected broken {s['expected_broken']:.1f} | coverage {_fmt(s['coverage'])}")
        for r in s["top_risks"]:
            print(f"  risk {r['id']}  p_broken {r['p_broken']:.2f}  window {r['worst_window']} {r['time']}  "
                  f"{r['text'][:70]}")


def _speaker_map(arg: str | None) -> dict:
    if not arg:
        return {}
    pairs = [p.split("=", 1) for p in arg.split(",") if p.strip()]
    return {k.strip(): v.strip() for k, v in pairs}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--out", default="reporte.json")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--mock", action="store_true", help="offline fake Jev (FAKE probabilities, plumbing test)")
    ap.add_argument("--window-bytes", type=int, default=12_000)
    ap.add_argument("--overlap-turns", type=int, default=2)
    ap.add_argument("--request-bytes", type=int, default=30_000)
    ap.add_argument("--repeats", type=int, default=1, help="ask each request N times and average")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--not-first-contact", action="store_true", help="e.g. second-round visit: skip opening rules")
    ap.add_argument("--speaker-map", help="SPEAKER_00=ENCUESTADOR,SPEAKER_01=INFORMANTE")
    ap.add_argument("--calibration", help="calibration.json from calibration.py fit")
    ap.add_argument("--export-labels", metavar="DIR", help="write a gold-label template to DIR")
    ap.add_argument("--cache-dir", default=".jev_cache")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args(argv)

    turns = load_transcript(args.transcript, _speaker_map(args.speaker_map))
    if args.mock:
        reg = question_registry(SECTIONS)
        client = FakeJev({k: calibration_group(k, SECTIONS) for k in reg},
                         {k: q.roles for k, q in reg.items() if q.type == "choice"})
    else:
        client = JevClient(model=args.model, cache_dir=None if args.no_cache else args.cache_dir)
    calibrator = Calibrator.load(args.calibration) if args.calibration else Calibrator()
    report = run_audit(turns, client, SECTIONS, window_bytes=args.window_bytes, overlap_turns=args.overlap_turns,
                       max_request_bytes=args.request_bytes, first_contact=not args.not_first_contact,
                       calibrator=calibrator, repeats=args.repeats, workers=args.workers)
    report["transcript"] = str(args.transcript)
    if args.mock:
        report["warning"] = "FAKE probabilities from --mock; not a real audit."
    if args.export_labels:
        export_label_template(report, SECTIONS, args.export_labels)
    report.pop("_windows_text")
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print_summary(report, Path(args.transcript).name)
    print(f"\nreport: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
