"""End-to-end plumbing with the offline fake: two-stage conditional gating, windowing, request sizes, report shape."""
from pathlib import Path

import pytest

from audit import export_label_template, plan_batches, run_audit
from jev_client import FakeJev, Usage, body_bytes
from rules import GATES, Kind, Scope, calibration_group, question_registry
from rules_a1_a2 import SECTIONS
from transcript import INTERVIEWER, OTHER, RESPONDENT, Turn, load_transcript, make_windows

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "transcript_example.json"


def _fake():
    reg = question_registry(SECTIONS)
    return FakeJev({k: calibration_group(k, SECTIONS) for k in reg},
                   {k: q.roles for k, q in reg.items() if q.type == "choice"})


def test_rule_inventory():
    a1, a2 = SECTIONS
    assert [i.id for i in a1.instructions] == [f"A1-{n:02d}" for n in range(1, 25)]
    assert [i.id for i in a2.instructions] == [f"A2-{n:02d}" for n in range(1, 28)]
    # Every CONDITIONAL instruction must carry a Stage-1 trigger Noul question
    conditionals = [i for s in SECTIONS for i in s.instructions if i.kind is Kind.CONDITIONAL]
    assert len(conditionals) == 15
    assert all(i.trigger is not None and i.trigger.type == "noul" for i in conditionals)


def test_payloads_follow_the_decisions_api_schema():
    for q in question_registry(SECTIONS).values():
        p = q.payload()
        assert p["type"] in {"noul", "choice"} and p["instructions"].strip()
        if p["type"] == "noul":
            assert set(p["criteria"]) == {"true", "false"}
        else:
            assert 1 <= len(p["criteria"]) <= 255 and all(v.strip() for v in p["criteria"].values())


def test_windows_respect_size_overlap_and_roles():
    turns = load_transcript(EXAMPLE)
    windows = make_windows(turns, max_bytes=1500, overlap_turns=2)
    assert len(windows) > 1
    assert all(w.n_bytes <= 1500 for w in windows)
    for a, b in zip(windows, windows[1:]):
        assert b.first_turn == a.last_turn - 1          # two shared turns
    assert Scope.OPENING in windows[0].scopes and Scope.CLOSING in windows[-1].scopes
    assert all(Scope.OPENING not in w.scopes for w in windows[1:])


def test_end_to_end_with_fake_client(tmp_path):
    client = _fake()
    report = run_audit(load_transcript(EXAMPLE), client, SECTIONS, window_bytes=1500, max_request_bytes=30_000)
    assert set(report["sections"]) == {"A1", "A2"}
    assert len(report["instructions"]) == 51
    for ins in report["instructions"]:
        total = ins["p_followed"] + ins["p_broken"] + ins["p_unknown"]
        assert total == pytest.approx(1.0, abs=1e-3)

    n_windows = len(report["windows"])
    opening_only = {q.key for s in SECTIONS for i in s.instructions if i.scope is Scope.OPENING for q in i.questions}
    opening_only |= {i.trigger.key for s in SECTIONS for i in s.instructions if i.scope is Scope.OPENING and i.trigger}
    closing_only = {q.key for s in SECTIONS for i in s.instructions if i.scope is Scope.CLOSING for q in i.questions}
    opening_only.add(GATES[Scope.OPENING].key)
    closing_only.add(GATES[Scope.CLOSING].key)
    for body in client.bodies:
        assert body_bytes(body) <= 30_000
        window = int(body["state"]["posicion"].split()[1]) - 1
        keys = set(body["questions"])
        if window != 0:
            assert not keys & opening_only
        if window != n_windows - 1:
            assert not keys & closing_only

    export_label_template(report, SECTIONS, tmp_path)
    rows = (tmp_path / "labels_template.csv").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("window,question_key,group") and len(rows) > 50
    assert (tmp_path / "windows.md").exists()


def test_two_stage_conditional_only_judges_triggered_windows():
    """Stage-2 choice questions are never called for windows where Stage-1 trigger did not fire."""
    reg = question_registry(SECTIONS)
    groups = {k: calibration_group(k, SECTIONS) for k in reg}
    cond_choice_keys = {
        q.key for s in SECTIONS for i in s.instructions if i.kind is Kind.CONDITIONAL for q in i.questions
    }

    class CleanInterviewerStub:
        model = "stub/jev"

        def __init__(self):
            self.usage = Usage()
            self.asked_keys = []

        def decide(self, state, questions, repeat_index=0):
            self.asked_keys.extend(questions.keys())
            ans = {}
            for k, q in questions.items():
                g = groups[k]
                if q["type"] == "noul":
                    if g in ("gate", "obligation"):
                        ans[k] = {"type": "noul", "noul": 0.96}
                    elif g == "trigger":
                        # Only trigger A1-24 once, in window 0
                        is_win0 = "Fragmento 1 de" in state["posicion"]
                        ans[k] = {"type": "noul", "noul": 0.92 if (k == "T_A1_24_desconfianza" and is_win0) else 0.04}
                    else:
                        # Small false-positive baseline noise on every conduct rule in every window
                        ans[k] = {"type": "noul", "noul": 0.04}
                else:
                    roles = reg[k].roles
                    ans[k] = {
                        "type": "choice",
                        "choice": roles["followed"],
                        "probabilities": {roles["followed"]: 0.92, roles["broken"]: 0.04, roles["unknown"]: 0.04},
                        "confidence": 0.92,
                    }
            return {"model": self.model, "answers": ans, "usage": {"input_tokens": 100, "cost": 0.0}}

    turns = [
        Turn(INTERVIEWER, "Buenos días, vengo del INE. " + "pregunta " * 30, i * 60.0, i * 60.0 + 55.0)
        for i in range(120)   # 2-hour visit (~120 minutes)
    ]
    stub = CleanInterviewerStub()
    report = run_audit(turns, stub, SECTIONS, window_bytes=3000, max_request_bytes=30_000)
    assert len(report["windows"]) >= 10
    # Only A1_24_desconfianza_datos should have been asked in Stage 2!
    asked_conds = set(stub.asked_keys) & cond_choice_keys
    assert asked_conds == {"A1_24_desconfianza_datos"}
    # Conduct flagged windows/hr must stay 0.0 across a 2-hour clean interview
    assert report["sections"]["A2"]["conduct_flagged_windows"] == 0
    assert report["sections"]["A2"]["conduct_flagged_per_hour"] == 0.0
    assert report["sections"]["A2"]["compliance_rate"] >= 0.94


def test_not_first_contact_skips_opening_rules():
    report = run_audit(load_transcript(EXAMPLE), _fake(), SECTIONS, first_contact=False)
    opening = [i for i in report["instructions"] if i["scope"] == "opening"]
    assert opening and all(i["p_unknown"] == 1.0 for i in opening)


def test_default_window_needs_one_request_per_middle_window():
    """At the default 12,000-byte window, Stage-1 ALL-scope questions plus state fit in one 30,000-byte body."""
    turns = load_transcript(EXAMPLE) * 12   # ~60 KB of text
    windows = make_windows(turns)
    batches = plan_batches(windows, SECTIONS, "typesafe/jev-1.14", 30_000)
    per_window = [sum(b.window == w.index for b in batches) for w in windows]
    assert all(n == 1 for n in per_window[1:-1])


def test_text_transcript_with_speaker_map(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("[00:00:01] SPEAKER_00: Buenos días, soy del INE.\n[00:00:04] SPEAKER_01: Buenos días.\n"
                 "continúa la misma frase\nSPEAKER_02: ¡Mamá!\n", encoding="utf-8")
    turns = load_transcript(f, {"SPEAKER_00": "ENCUESTADOR", "SPEAKER_01": "informante"})
    assert [t.speaker for t in turns] == [INTERVIEWER, RESPONDENT, OTHER]
    assert turns[1].text.endswith("continúa la misma frase") and turns[0].start == 1.0
    with pytest.raises(ValueError):
        load_transcript(f)   # no mapping: no interviewer turns


def test_continuation_line_with_colon_is_not_a_speaker(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("ENCUESTADOR: ¿Qué le dijo el vecino?\nINFORMANTE: Pues yo le dije:\ny le dije: no, gracias.\n",
                 encoding="utf-8")
    turns = load_transcript(f)
    assert len(turns) == 2 and turns[1].text.endswith("y le dije: no, gracias.")
