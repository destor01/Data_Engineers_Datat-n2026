"""The probability math, checked against brute-force enumeration."""
import itertools
import math
import random

import pytest

from rules import Kind, Scope
from rules_a1_a2 import SECTIONS
from scoring import (Outcome, apply_gate, combine_windows, evaluate_instruction, poisson_binomial,
                     rate_distribution, section_summary, window_outcome, InstructionResult)

BY_ID = {i.id: i for s in SECTIONS for i in s.instructions}


def _random_outcomes(rng, n):
    return [Outcome.make(rng.random(), rng.random(), rng.random()) for _ in range(n)]


def _probs(o):
    return [o.followed, o.broken, o.unknown]


def test_poisson_binomial_matches_brute_force():
    rng = random.Random(1)
    for _ in range(25):
        ps = [rng.random() for _ in range(rng.randint(1, 7))]
        expected = [0.0] * (len(ps) + 1)
        for bits in itertools.product((0, 1), repeat=len(ps)):
            expected[sum(bits)] += math.prod(p if b else 1 - p for p, b in zip(ps, bits))
        assert poisson_binomial(ps) == pytest.approx(expected, abs=1e-12)


def test_rate_distribution_matches_enumeration():
    rng = random.Random(2)
    for _ in range(10):
        outs = _random_outcomes(rng, 5)
        p_none = mass = tail80 = tail90 = 0.0
        for state in itertools.product(range(3), repeat=5):   # 0 followed, 1 broken, 2 unknown
            pr = math.prod(_probs(o)[s] for o, s in zip(outs, state))
            applicable = sum(s < 2 for s in state)
            if applicable == 0:
                p_none += pr
                continue
            rate = sum(s == 0 for s in state) / applicable
            mass += pr
            tail80 += pr * (rate >= 0.8 - 1e-12)
            tail90 += pr * (rate >= 0.9 - 1e-12)
        d = rate_distribution(outs)
        assert d["p_nothing_applicable"] == pytest.approx(p_none, abs=1e-4)
        assert d["p_rate_at_least_80"] == pytest.approx(tail80 / mass, abs=1e-4)
        assert d["p_rate_at_least_90"] == pytest.approx(tail90 / mass, abs=1e-4)


def test_combine_windows_matches_violation_dominates_rule():
    rng = random.Random(3)
    for kind in (Kind.CONDITIONAL, Kind.PROHIBITION):
        for _ in range(10):
            outs = _random_outcomes(rng, 3)
            if kind is Kind.PROHIBITION:
                outs = [Outcome.make(o.followed + o.unknown, o.broken, 0) for o in outs]
            expected = [0.0, 0.0, 0.0]
            for state in itertools.product(range(3), repeat=3):
                pr = math.prod(_probs(o)[s] for o, s in zip(outs, state))
                expected[1 if 1 in state else 0 if 0 in state else 2] += pr
            assert _probs(combine_windows(kind, outs)) == pytest.approx(expected, abs=1e-12)


def test_single_window_kinds_refuse_several_windows():
    with pytest.raises(ValueError):
        combine_windows(Kind.OBLIGATION, [Outcome.make(1, 0, 0)] * 2)


def test_gate_moves_mass_to_unknown():
    o = apply_gate(Outcome.make(0.7, 0.3, 0.0), 0.6)
    assert _probs(o) == pytest.approx([0.42, 0.18, 0.40])


def test_window_outcome_reads_each_kind():
    two_part_obligation = window_outcome(BY_ID["A1-02"], {
        "A1_02_nombre": {"type": "noul", "noul": 0.9}, "A1_02_ine": {"type": "noul", "noul": 0.8}})
    assert _probs(two_part_obligation) == pytest.approx([0.72, 0.28, 0.0])

    two_part_prohibition = window_outcome(BY_ID["A2-01"], {
        "A2_01_descortes": {"type": "noul", "noul": 0.1}, "A2_01_informal": {"type": "noul", "noul": 0.2}})
    assert _probs(two_part_prohibition) == pytest.approx([0.72, 0.28, 0.0])

    q = BY_ID["A1-17"].questions[0]
    probs = {q.roles["unknown"]: 0.5, q.roles["followed"]: 0.3, q.roles["broken"]: 0.2}
    conditional = window_outcome(BY_ID["A1-17"], {q.key: {"type": "choice", "probabilities": probs}})
    assert _probs(conditional) == pytest.approx([0.3, 0.2, 0.5])

    assert window_outcome(BY_ID["A1-01"], {}) is None
    assert window_outcome(BY_ID["A1-01"], {"A1_01_saludo": {"type": "refusal"}}) is None


def test_evaluate_instruction_scopes_and_gates():
    answers = {0: {"A1_01_saludo": {"type": "noul", "noul": 0.9}, "A2_10_promesas": {"type": "noul", "noul": 0.1}},
               1: {"A2_10_promesas": {"type": "noul", "noul": 0.5}}}
    scopes = {0: frozenset({Scope.OPENING, Scope.ALL}), 1: frozenset({Scope.CLOSING, Scope.ALL})}
    gates = {Scope.OPENING: 0.8, Scope.CLOSING: 1.0}

    opening = evaluate_instruction(BY_ID["A1-01"], answers, scopes, gates)
    assert _probs(opening.outcome) == pytest.approx([0.72, 0.08, 0.20])

    everywhere = evaluate_instruction(BY_ID["A2-10"], answers, scopes, gates)
    assert everywhere.outcome.broken == pytest.approx(1 - 0.9 * 0.5)
    assert everywhere.worst_window() == (1, pytest.approx(0.5))

    no_opening = evaluate_instruction(BY_ID["A1-01"], answers, {0: frozenset({Scope.ALL}), 1: scopes[1]}, gates)
    assert _probs(no_opening.outcome) == [0.0, 0.0, 1.0] and no_opening.note

    gate_missing = evaluate_instruction(BY_ID["A1-01"], answers, scopes, {Scope.OPENING: None})
    assert gate_missing.outcome.unknown == 1.0


def test_section_bounds_contain_independence_product():
    rng = random.Random(4)
    instrs = list(BY_ID.values())[:8]
    for _ in range(20):
        results = [InstructionResult(i, o) for i, o in zip(instrs, _random_outcomes(rng, 8))]
        s = section_summary(results)
        lo, hi = s["p_all_followed_bounds"]
        assert lo - 1e-4 <= s["p_all_followed"] <= hi + 1e-4
        assert s["expected_broken"] == pytest.approx(sum(r.outcome.broken for r in results), abs=1e-3)


def test_worked_example_from_the_guide():
    """The 4-instruction example in GUIDE_JEV_QUESTIONS.md, section 6."""
    outs = [Outcome.make(0.90, 0.10, 0.00), Outcome.make(0.60, 0.20, 0.20),
            Outcome.make(0.00, 0.00, 1.00), Outcome.make(0.95, 0.05, 0.00)]
    results = [InstructionResult(i, o) for i, o in zip(list(BY_ID.values())[:4], outs)]
    s = section_summary(results)
    assert s["compliance_rate"] == pytest.approx(2.45 / 2.80, abs=1e-4)
    assert s["p_all_followed"] == pytest.approx(0.9 * 0.8 * 1.0 * 0.95, abs=1e-4)
    assert s["p_all_followed_bounds"] == pytest.approx([0.65, 0.80], abs=1e-4)
    assert s["coverage"] == pytest.approx(0.70, abs=1e-4)
