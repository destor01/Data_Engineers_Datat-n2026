"""Probability math: Jev answers -> instruction outcome -> section summary.

Every instruction carries three probabilities that add up to 1:
    c = P(followed)    v = P(broken)    u = P(can't tell: it did not apply, its moment is not in
                                            the recording, or there is no audible evidence)
Window level (see rules.py for how each kind reads its Jev answers), then:
    single-window scope (OPENING / CLOSING), gate g = P(that moment is in the transcript):
        c = g * c_w        v = g * v_w        u = (1 - g) + g * u_w
    ALL scope (PROHIBITION, CONDITIONAL); a violation in any window breaks the instruction:
        u = prod(u_w)      v = 1 - prod(1 - v_w)      c = 1 - u - v
Section level: expected compliance rate sum(c) / sum(c + v); P(no instruction broken) =
prod(1 - v) with dependence-free bounds; the exact distribution of the number broken and of the
compliance rate. The products assume independence (see the guide for when that matters).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from calibration import Calibrator
from rules import ROLE_BAD, ROLE_NA, ROLE_OK, Instruction, Kind, Scope

FLAG_YES, FLAG_NO = 0.7, 0.3   # TypeSafe's starting Noul thresholds; the band between them is "review"
RISK_FLOOR = 0.3               # instructions with v >= this are listed as section risks


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
    if not outcomes:
        return UNKNOWN
    if kind in (Kind.OBLIGATION, Kind.EVIDENCE):
        if len(outcomes) != 1:
            raise ValueError(f"{kind.value} is single-window; got {len(outcomes)} windows")
        return outcomes[0]
    keep = math.prod(1 - o.broken for o in outcomes)
    none = math.prod(o.unknown for o in outcomes)
    return Outcome.make(keep - none, 1 - keep, none)


@dataclass
class InstructionResult:
    instruction: Instruction
    outcome: Outcome
    per_window: list = field(default_factory=list)   # [(window_index, Outcome)] after gating
    gate: float | None = None
    note: str = ""

    def worst_window(self) -> tuple[int, float] | None:
        if not self.per_window:
            return None
        w, o = max(self.per_window, key=lambda wo: wo[1].broken)
        return w, o.broken

    def to_dict(self, window_times: Mapping[int, tuple] | None = None) -> dict:
        ins, o = self.instruction, self.outcome
        worst = self.worst_window()
        d = {"id": ins.id, "section": ins.section, "text": ins.text, "pages": ins.pages,
             "kind": ins.kind.value, "scope": ins.scope.value, "weight": ins.weight,
             "verifiability": ins.verifiability,
             "p_followed": _r(o.followed), "p_broken": _r(o.broken), "p_unknown": _r(o.unknown),
             "p_followed_if_applicable": _r(o.followed_if_applicable()),
             "gate": _r(self.gate), "note": "; ".join(x for x in (self.note, ins.note) if x),
             "windows": [{"window": w, "followed": _r(x.followed), "broken": _r(x.broken),
                          "unknown": _r(x.unknown)} for w, x in self.per_window]}
        if worst:
            d["worst_window"] = {"window": worst[0], "p_broken": _r(worst[1]),
                                 "time": (window_times or {}).get(worst[0])}
        if ins.scope is Scope.ALL:
            d["expected_broken_windows"] = _r(sum(x.broken for _, x in self.per_window))
            d["windows_flagged"] = sum(x.broken >= FLAG_YES for _, x in self.per_window)
            d["windows_review"] = sum(FLAG_NO <= x.broken < FLAG_YES for _, x in self.per_window)
        return d


def evaluate_instruction(instr: Instruction, answers_by_window: Mapping[int, Mapping[str, dict]],
                         scopes_by_window: Mapping[int, frozenset], gates: Mapping[Scope, float | None],
                         calibrator: Calibrator | None = None) -> InstructionResult:
    windows = [w for w in sorted(answers_by_window) if instr.scope in scopes_by_window[w]]
    if not windows:
        return InstructionResult(instr, UNKNOWN, note="its moment is not part of this visit "
                                                        "(e.g. not a first-contact visit)")
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


def section_summary(results: Sequence[InstructionResult], title: str = "",
                    window_times: Mapping[int, tuple] | None = None) -> dict:
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
    risks = sorted((r for r in results if r.outcome.broken >= RISK_FLOOR), key=lambda r: -r.outcome.broken)
    return {
        "title": title,
        "n_instructions": len(results),
        "coverage": _r(applicable / len(results)) if results else None,
        "expected_followed": _r(sum(c)),
        "expected_broken": _r(sum(v)),
        "compliance_rate": _r(sum(c) / applicable) if applicable > 1e-9 else None,
        "compliance_rate_weighted": _r(sum(wi * ci for wi, ci in zip(w, c)) / w_app) if w_app > 1e-9 else None,
        "p_all_followed": _r(math.prod(1 - x for x in v)),
        "p_all_followed_bounds": [_r(max(0.0, 1 - sum(v))), _r(1 - max(v, default=0.0))],
        "p_at_most_1_broken": _r(sum(pmf[:2])),
        "broken_count_pmf": [_r(m) for m in pmf[:cut]],
        **rate_distribution(outs),
        "top_risks": [{"id": r.instruction.id, "p_broken": _r(r.outcome.broken), "text": r.instruction.text,
                       "worst_window": (r.worst_window() or (None,))[0],
                       "time": (window_times or {}).get((r.worst_window() or (None,))[0])} for r in risks[:5]],
    }


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(float(x), nd)
