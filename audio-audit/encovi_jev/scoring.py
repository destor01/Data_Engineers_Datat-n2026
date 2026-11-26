"""Probability math: Jev answers -> length-invariant instruction outcome -> section summary.

Every instruction carries three probabilities that add up to 1:
    c = P(followed)    v = P(broken)    u = P(can't tell: it did not apply, its moment is not in
                                            the recording, or there is no audible evidence)

Length-invariant aggregation across windows:
    - Single-window scope (OPENING / CLOSING), gate g = P(that moment is in the transcript):
        c = g * c_w        v = g * v_w        u = (1 - g) + g * u_w
    - Two-stage CONDITIONAL rules ("if X happens, do Y"):
        Stage 1 asks whether X happened in each window (`p_trigger`). Windows with `p_trigger < threshold`
        stay `UNKNOWN (0, 0, 1)` without accumulating false positives. Only triggered windows are judged
        in Stage 2 and aggregated by mean across triggered occurrences.
    - Conduct rules (PROHIBITION, Scope.ALL):
        Aggregated by per-window mean (length-invariant compliance share across windows) rather than
        `1 - prod(1 - v_w)` so small baseline false positives do not compound on 2-hour interviews.
        Verdicts and risk reporting also track `windows_flagged` (v_w >= 0.70) and `flagged_per_hour`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from calibration import Calibrator
from rules import ROLE_BAD, ROLE_NA, ROLE_OK, Instruction, Kind, Scope

FLAG_YES, FLAG_NO = 0.7, 0.3   # TypeSafe's starting Noul thresholds; the band between them is "review"
RISK_FLOOR = 0.3               # instructions with v >= this (or flagged/review windows) are listed as risks
TRIGGER_THRESHOLD = 0.5        # Stage-1 trigger probability required to evaluate a conditional rule in Stage 2
ESTIMATED_BYTES_PER_HOUR = 865 * 60   # Empirical Spanish transcript rate from GUIDE_JEV_QUESTIONS.md (~865 B/min)


@dataclass(frozen=True)
class Outcome:
    followed: float
    broken: float
    unknown: float

    @classmethod
    def make(cls, c: float, v: float, u: float) -> "Outcome":
        """Clip float noise and renormalize so c + v + u == 1."""
        c, v, u = (max(0.0, float(x)) for x in (c, v, u))
        s = c + v + u
        return cls(c / s, v / s, u / s) if s > 0 else cls(0.0, 0.0, 1.0)

    @property
    def applicable(self) -> float:
        return self.followed + self.broken

    def followed_if_applicable(self) -> float | None:
        return self.followed / self.applicable if self.applicable > 1e-9 else None


UNKNOWN = Outcome(0.0, 0.0, 1.0)


class _Unanswered(Exception):
    pass


def _noul(answers: Mapping[str, dict], key: str) -> float:
    a = answers.get(key)
    if not a or a.get("type") != "noul":
        raise _Unanswered(key)
    return float(a["noul"])


def _choice(answers: Mapping[str, dict], key: str, options: Sequence[str]) -> dict:
    a = answers.get(key)
    if not a or a.get("type") != "choice":
        raise _Unanswered(key)
    return {opt: float(a["probabilities"].get(opt, 0.0)) for opt in options}


def trigger_probability(
    instr: Instruction,
    answers: Mapping[str, dict],
    calibrator: Calibrator | None = None,
) -> float | None:
    """Calibrated Stage-1 trigger probability for a CONDITIONAL instruction in one window."""
    if instr.trigger is None:
        return None
    cal = calibrator or Calibrator()
    try:
        return cal.noul(_noul(answers, instr.trigger.key), "trigger")
    except _Unanswered:
        return None


def window_outcome(instr: Instruction, answers: Mapping[str, dict],
                   calibrator: Calibrator | None = None) -> Outcome | None:
    """Outcome of one instruction in one window; None if an answer is missing or refused."""
    cal = calibrator or Calibrator()
    group = instr.kind.value
    try:
        if instr.kind is Kind.OBLIGATION:      # every part must happen
            p = math.prod(cal.noul(_noul(answers, q.key), group) for q in instr.questions)
            return Outcome.make(p, 1 - p, 0)
        if instr.kind is Kind.PROHIBITION:     # any part breaks it
            keep = math.prod(1 - cal.noul(_noul(answers, q.key), group) for q in instr.questions)
            return Outcome.make(keep, 1 - keep, 0)
        q = instr.questions[0]                 # CONDITIONAL / EVIDENCE: one 3-option choice
        probs = cal.choice(_choice(answers, q.key, list(q.criteria)), group)
        return Outcome.make(probs[q.roles[ROLE_OK]], probs[q.roles[ROLE_BAD]], probs[q.roles[ROLE_NA]])
    except _Unanswered:
        return None


def apply_gate(o: Outcome, g: float) -> Outcome:
    g = min(1.0, max(0.0, float(g)))
    return Outcome.make(g * o.followed, g * o.broken, (1 - g) + g * o.unknown)


def combine_windows(kind: Kind, outcomes: Sequence[Outcome]) -> Outcome:
    """Length-invariant aggregation across windows.

    - Single-window kinds (OBLIGATION, EVIDENCE): exactly one window.
    - PROHIBITION (conduct across all windows): mean (c, v, u) across windows so baseline noise
      does not compound with interview length.
    - CONDITIONAL (multi-window): mean (c, v, u) across triggered/applicable windows (or UNKNOWN
      if the trigger never occurred).
    """
    if not outcomes:
        return UNKNOWN
    if kind in (Kind.OBLIGATION, Kind.EVIDENCE):
        if len(outcomes) != 1:
            raise ValueError(f"{kind.value} is single-window; got {len(outcomes)} windows")
        return outcomes[0]
    if kind is Kind.CONDITIONAL:
        applicable = [o for o in outcomes if o.applicable > 1e-9]
        if not applicable:
            return UNKNOWN
        n = len(applicable)
        return Outcome.make(
            sum(o.followed for o in applicable) / n,
            sum(o.broken for o in applicable) / n,
            sum(o.unknown for o in applicable) / n,
        )
    # PROHIBITION: per-window mean (length-invariant compliance share)
    n = len(outcomes)
    return Outcome.make(
        sum(o.followed for o in outcomes) / n,
        sum(o.broken for o in outcomes) / n,
        sum(o.unknown for o in outcomes) / n,
    )


def estimate_duration_hours(
    window_times: Mapping[int, Sequence[float | None]] | None = None,
    *,
    duration_seconds: float | None = None,
    total_bytes: int | None = None,
) -> float:
    """Best available interview duration in hours (used to compute flagged windows per hour)."""
    if duration_seconds is not None and duration_seconds > 0:
        return float(duration_seconds) / 3600.0
    if window_times:
        starts = [t[0] for t in window_times.values() if t and len(t) >= 1 and t[0] is not None]
        ends = [t[1] for t in window_times.values() if t and len(t) >= 2 and t[1] is not None]
        if starts and ends:
            span = max(ends) - min(starts)
            if span > 0:
                return float(span) / 3600.0
            if max(ends) > 0:
                return float(max(ends)) / 3600.0
    if total_bytes and total_bytes > 0:
        return float(total_bytes) / ESTIMATED_BYTES_PER_HOUR
    return 1.0


@dataclass
class InstructionResult:
    instruction: Instruction
    outcome: Outcome
    per_window: list = field(default_factory=list)   # [(window_index, Outcome)] after gating
    gate: float | None = None
    note: str = ""
    trigger_probs: dict[int, float] = field(default_factory=dict)
    triggered_windows: list[int] = field(default_factory=list)

    def worst_window(self) -> tuple[int, float] | None:
        if not self.per_window:
            return None
        w, o = max(self.per_window, key=lambda wo: wo[1].broken)
        return w, o.broken

    def windows_flagged_count(self) -> int:
        if self.instruction.scope is not Scope.ALL:
            return 0
        return sum(1 for _, x in self.per_window if x.broken >= FLAG_YES)

    def windows_review_count(self) -> int:
        if self.instruction.scope is not Scope.ALL:
            return 0
        return sum(1 for _, x in self.per_window if FLAG_NO <= x.broken < FLAG_YES)

    def risk_score(self) -> float:
        """Ranking score for top_risks: catches clearly flagged windows even on long visits."""
        base = self.outcome.broken
        if self.instruction.scope is Scope.ALL:
            worst = self.worst_window()
            if worst and worst[1] >= RISK_FLOOR:
                return max(base, worst[1])
        return base

    def to_dict(
        self,
        window_times: Mapping[int, tuple] | None = None,
        *,
        duration_hours: float | None = None,
    ) -> dict:
        ins, o = self.instruction, self.outcome
        worst = self.worst_window()
        win_entries = []
        for w, x in self.per_window:
            entry = {
                "window": w,
                "followed": _r(x.followed),
                "broken": _r(x.broken),
                "unknown": _r(x.unknown),
            }
            if w in self.trigger_probs:
                entry["p_trigger"] = _r(self.trigger_probs[w])
                entry["triggered"] = w in self.triggered_windows
            win_entries.append(entry)

        d: dict = {
            "id": ins.id,
            "section": ins.section,
            "text": ins.text,
            "pages": ins.pages,
            "kind": ins.kind.value,
            "scope": ins.scope.value,
            "weight": ins.weight,
            "verifiability": ins.verifiability,
            "p_followed": _r(o.followed),
            "p_broken": _r(o.broken),
            "p_unknown": _r(o.unknown),
            "p_followed_if_applicable": _r(o.followed_if_applicable()),
            "gate": _r(self.gate),
            "note": "; ".join(x for x in (self.note, ins.note) if x),
            "windows": win_entries,
        }
        if worst:
            d["worst_window"] = {
                "window": worst[0],
                "p_broken": _r(worst[1]),
                "time": (window_times or {}).get(worst[0]),
            }
        if ins.trigger is not None:
            d["triggered_windows"] = len(self.triggered_windows)
            d["max_trigger_prob"] = _r(max(self.trigger_probs.values())) if self.trigger_probs else None
        if ins.scope is Scope.ALL:
            flagged = self.windows_flagged_count()
            review = self.windows_review_count()
            d["expected_broken_windows"] = _r(sum(x.broken for _, x in self.per_window))
            d["windows_flagged"] = flagged
            d["windows_review"] = review
            if duration_hours is not None and duration_hours > 0:
                eff_h = max(duration_hours, 1.0 / 60.0)
                d["flagged_per_hour"] = round(flagged / eff_h, 2)
        return d


def evaluate_instruction(
    instr: Instruction,
    answers_by_window: Mapping[int, Mapping[str, dict]],
    scopes_by_window: Mapping[int, frozenset],
    gates: Mapping[Scope, float | None],
    calibrator: Calibrator | None = None,
    *,
    trigger_threshold: float = TRIGGER_THRESHOLD,
) -> InstructionResult:
    windows = [w for w in sorted(answers_by_window) if instr.scope in scopes_by_window[w]]
    if not windows:
        return InstructionResult(
            instr,
            UNKNOWN,
            note="its moment is not part of this visit (e.g. not a first-contact visit)",
        )

    # Two-stage CONDITIONAL evaluation: gate each window by Stage-1 trigger ("did X happen?")
    if instr.kind is Kind.CONDITIONAL and instr.trigger is not None:
        trig_probs: dict[int, float] = {}
        triggered_ws: list[int] = []
        per: list[tuple[int, Outcome]] = []
        triggered_outcomes: list[Outcome] = []

        for w in windows:
            w_ans = answers_by_window[w]
            p_t = trigger_probability(instr, w_ans, calibrator)
            if p_t is None:
                # Fallback: if caller passed Stage-2 answer directly without Stage-1 trigger (legacy/tests)
                direct = window_outcome(instr, w_ans, calibrator)
                if direct is not None:
                    per.append((w, direct))
                    if direct.applicable > 1e-9:
                        triggered_ws.append(w)
                        triggered_outcomes.append(direct)
                continue

            trig_probs[w] = p_t
            if p_t < trigger_threshold:
                per.append((w, UNKNOWN))
                continue

            triggered_ws.append(w)
            resp = window_outcome(instr, w_ans, calibrator)
            if resp is None:
                per.append((w, UNKNOWN))
                continue
            gated_resp = apply_gate(resp, p_t)
            per.append((w, gated_resp))
            triggered_outcomes.append(gated_resp)

        if not per:
            return InstructionResult(instr, UNKNOWN, note="no usable Jev answer (refused or missing)")

        if instr.scope is Scope.ALL:
            combined = combine_windows(Kind.CONDITIONAL, triggered_outcomes) if triggered_outcomes else UNKNOWN
            return InstructionResult(
                instr,
                combined,
                per,
                trigger_probs=trig_probs,
                triggered_windows=triggered_ws,
            )

        # Single-window CONDITIONAL (OPENING): apply opening gate as well
        g = gates.get(instr.scope)
        if g is None:
            return InstructionResult(
                instr,
                UNKNOWN,
                note=f"{instr.scope.value} gate unanswered",
                trigger_probs=trig_probs,
                triggered_windows=triggered_ws,
            )
        w, o = per[0]
        gated = apply_gate(o, g)
        return InstructionResult(
            instr,
            gated,
            [(w, gated)],
            g,
            trigger_probs=trig_probs,
            triggered_windows=triggered_ws,
        )

    # Standard OBLIGATION / PROHIBITION / EVIDENCE / un-triggered CONDITIONAL
    per = [(w, o) for w in windows if (o := window_outcome(instr, answers_by_window[w], calibrator))]
    if not per:
        return InstructionResult(instr, UNKNOWN, note="no usable Jev answer (refused or missing)")
    if instr.scope is Scope.ALL:
        return InstructionResult(instr, combine_windows(instr.kind, [o for _, o in per]), per)
    g = gates.get(instr.scope)
    if g is None:
        return InstructionResult(instr, UNKNOWN, note=f"{instr.scope.value} gate unanswered")
    w, o = per[0]   # exactly one window plays OPENING (the first) or CLOSING (the last)
    gated = apply_gate(o, g)
    return InstructionResult(instr, gated, [(w, gated)], g)


# --- section level -------------------------------------------------------------------------

def poisson_binomial(ps: Sequence[float]) -> list[float]:
    """P(K = k), K = number of broken instructions, instructions independent."""
    pmf = [1.0]
    for p in ps:
        nxt = [0.0] * (len(pmf) + 1)
        for k, m in enumerate(pmf):
            nxt[k] += m * (1 - p)
            nxt[k + 1] += m * p
        pmf = nxt
    return pmf


def rate_distribution(outcomes: Sequence[Outcome], thresholds: Sequence[float] = (0.8, 0.9),
                      quantiles: Sequence[float] = (0.05, 0.5, 0.95)) -> dict:
    """Exact distribution of followed / applicable over the section, instructions independent.

    Each instruction lands in (applicable, followed) = (1,1) w.p. c, (1,0) w.p. v, (0,0) w.p. u.
    Tail probabilities and quantiles are conditional on at least one instruction applying.
    """
    dp = {(0, 0): 1.0}
    for o in outcomes:
        nxt: dict = {}
        for (a, f), m in dp.items():
            for da, df, p in ((1, 1, o.followed), (1, 0, o.broken), (0, 0, o.unknown)):
                if p > 0:
                    nxt[(a + da, f + df)] = nxt.get((a + da, f + df), 0.0) + m * p
        dp = nxt
    p_none = sum(m for (a, _), m in dp.items() if a == 0)
    out: dict = {"p_nothing_applicable": _r(p_none)}
    mass = 1 - p_none
    tails = {f"p_rate_at_least_{round(t * 100)}": None for t in thresholds}
    if mass <= 1e-12:
        return {**out, **tails, "rate_quantiles": None}
    pts = sorted((f / a, m / mass) for (a, f), m in dp.items() if a > 0)
    for t in thresholds:
        tails[f"p_rate_at_least_{round(t * 100)}"] = _r(sum(m for r, m in pts if r >= t - 1e-12))
    qs, cum, i = {}, 0.0, 0
    for q in sorted(quantiles):
        while i < len(pts) and cum + pts[i][1] < q - 1e-12:
            cum += pts[i][1]
            i += 1
        qs[f"q{round(q * 100):02d}"] = _r(pts[min(i, len(pts) - 1)][0])
    return {**out, **tails, "rate_quantiles": qs}


def section_summary(
    results: Sequence[InstructionResult],
    title: str = "",
    window_times: Mapping[int, tuple] | None = None,
    *,
    duration_hours: float | None = None,
) -> dict:
    outs = [r.outcome for r in results]
    c = [o.followed for o in outs]
    v = [o.broken for o in outs]
    w = [r.instruction.weight for r in results]
    applicable = sum(c) + sum(v)
    w_app = sum(wi * (ci + vi) for wi, ci, vi in zip(w, c, v))
    pmf = poisson_binomial(v)
    cum, cut = 0.0, len(pmf)
    for k, m in enumerate(pmf):           # trim the tail once 99.9% of the mass is covered
        cum += m
        if cum >= 0.999:
            cut = k + 1
            break

    eff_hours = max(duration_hours if duration_hours is not None else estimate_duration_hours(window_times), 1.0 / 60.0)
    conduct_results = [r for r in results if r.instruction.kind is Kind.PROHIBITION and r.instruction.scope is Scope.ALL]
    conduct_flagged = sum(r.windows_flagged_count() for r in conduct_results)
    all_flagged = sum(r.windows_flagged_count() for r in results)

    risks = sorted(
        (r for r in results if r.risk_score() >= RISK_FLOOR),
        key=lambda r: -r.risk_score(),
    )

    top_risk_entries = []
    for r in risks[:5]:
        ww = r.worst_window()
        top_risk_entries.append(
            {
                "id": r.instruction.id,
                "kind": r.instruction.kind.value,
                "p_broken": _r(r.risk_score()),
                "mean_p_broken": _r(r.outcome.broken),
                "windows_flagged": r.windows_flagged_count(),
                "text": r.instruction.text,
                "worst_window": (ww or (None,))[0],
                "time": (window_times or {}).get((ww or (None,))[0]),
            }
        )

    return {
        "title": title,
        "n_instructions": len(results),
        "coverage": _r(applicable / len(results)) if results else None,
        "expected_followed": _r(sum(c)),
        "expected_broken": _r(sum(v)),
        "compliance_rate": _r(sum(c) / applicable) if applicable > 1e-9 else None,
        "compliance_rate_weighted": _r(sum(wi * ci for wi, ci in zip(w, c)) / w_app) if w_app > 1e-9 else None,
        "conduct_flagged_windows": conduct_flagged,
        "conduct_flagged_per_hour": round(conduct_flagged / eff_hours, 2),
        "flagged_windows_total": all_flagged,
        "flagged_windows_per_hour": round(all_flagged / eff_hours, 2),
        "duration_hours": round(eff_hours, 4),
        "p_at_most_1_broken": _r(sum(pmf[:2])),
        "broken_count_pmf": [_r(m) for m in pmf[:cut]],
        **rate_distribution(outs),
        "top_risks": top_risk_entries,
    }


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(float(x), nd)
