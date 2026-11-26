"""Rule model: ENCOVI interviewer instructions expressed as Jev (TypeSafe System One) questions.

An Instruction is one line of the rules file (e.g. A1-01). It owns one or more Jev questions
and a `kind` that says how the answers become (followed, broken, unknown) probabilities for
one transcript window:

  kind         Jev question(s)                                     window outcome (c, v, u)
  -----------  --------------------------------------------------  ---------------------------------
  OBLIGATION   1+ Noul, true = the required act happened           (P(all parts), 1 - P(all parts), 0)
  PROHIBITION  1+ Noul, true = the forbidden act happened          (1 - P(any part), P(any part), 0)
  CONDITIONAL  Stage 1 Noul trigger + Stage 2 Choice (only where   (0, 0, 1) if trigger < threshold;
               trigger fired in that window)                       else trigger-gated (p_ok, p_bad, p_na)
  EVIDENCE     1 Choice {done | sign of not done | no mention}     (p_done, p_not_done, p_no_mention)

`scope` says which windows the questions are asked on. OBLIGATION and EVIDENCE are single-window
by design (opening or closing); PROHIBITION and CONDITIONAL may span every window.
Question text is Spanish because the transcripts are Spanish.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping


class Kind(str, Enum):
    OBLIGATION = "obligation"
    PROHIBITION = "prohibition"
    CONDITIONAL = "conditional"
    EVIDENCE = "evidence"


class Scope(str, Enum):
    OPENING = "opening"  # first window of a first-contact visit
    CLOSING = "closing"  # last window of the visit
    ALL = "all"          # every window


# Roles of the three options of a CONDITIONAL / EVIDENCE choice.
ROLE_OK, ROLE_BAD, ROLE_NA = "followed", "broken", "unknown"
ROLES = (ROLE_NA, ROLE_OK, ROLE_BAD)  # order the options are sent in


@dataclass(frozen=True)
class Question:
    """One Jev question. `key` is the request id; Jev never sees its meaning, only the text."""

    key: str
    type: str                                    # "noul" | "choice"
    instructions: str
    criteria: Mapping[str, str]                  # noul: {"true","false"}; choice: option -> description
    roles: Mapping[str, str] = field(default_factory=dict)  # choice only: role -> option name

    def payload(self) -> dict:
        """The question object exactly as sent to the Decisions API."""
        return {"type": self.type, "instructions": self.instructions, "criteria": dict(self.criteria)}


@dataclass(frozen=True)
class Instruction:
    id: str
    section: str
    text: str                      # rule text as in the rules file
    pages: str                     # printed page(s) of the manual
    kind: Kind
    scope: Scope
    questions: tuple[Question, ...]
    weight: int = 1                # proposed severity 1-3; agree on it before looking at results
    verifiability: str = "alta"    # alta / media / baja: how much of the rule is audible
    note: str = ""
    trigger: Question | None = None  # Stage-1 Noul gate for CONDITIONAL rules ("did X happen?")

    def __post_init__(self) -> None:
        if not self.questions:
            raise ValueError(f"{self.id}: no questions")
        if self.kind in (Kind.OBLIGATION, Kind.PROHIBITION):
            if any(q.type != "noul" for q in self.questions):
                raise ValueError(f"{self.id}: {self.kind.value} questions must all be noul")
        else:
            if len(self.questions) != 1 or self.questions[0].type != "choice":
                raise ValueError(f"{self.id}: {self.kind.value} needs exactly one choice question")
            if set(self.questions[0].roles) != set(ROLES):
                raise ValueError(f"{self.id}: choice must map roles {ROLES}")
        if self.trigger is not None:
            if self.kind is not Kind.CONDITIONAL:
                raise ValueError(f"{self.id}: trigger is only valid for conditional instructions")
            if self.trigger.type != "noul":
                raise ValueError(f"{self.id}: trigger question must be noul")
        if self.kind in (Kind.OBLIGATION, Kind.EVIDENCE) and self.scope is Scope.ALL:
            raise ValueError(f"{self.id}: {self.kind.value} is single-window; use OPENING or CLOSING")
        if self.weight not in (1, 2, 3):
            raise ValueError(f"{self.id}: weight must be 1, 2 or 3")


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    instructions: tuple[Instruction, ...]


# --- question builders ---------------------------------------------------------------------

def noul(key: str, instructions: str, true: str, false: str) -> Question:
    """Yes/no question. Phrase it so that true means the event happened."""
    return Question(key, "noul", instructions, {"true": true, "false": false})


def tri_choice(key: str, instructions: str, *, unknown: tuple[str, str],
               followed: tuple[str, str], broken: tuple[str, str]) -> Question:
    """Three exclusive, exhaustive options; each argument is (option_name, description)."""
    options = {ROLE_NA: unknown, ROLE_OK: followed, ROLE_BAD: broken}
    criteria = {options[r][0]: options[r][1] for r in ROLES}
    if len(criteria) != 3:
        raise ValueError(f"{key}: option names must be distinct")
    return Question(key, "choice", instructions, criteria, {r: options[r][0] for r in ROLES})


# Gate questions: is the moment that OPENING / CLOSING rules refer to inside the transcript at all?
GATE_OPENING = noul(
    "G_APERTURA",
    "El fragmento incluye el primer contacto del ENCUESTADOR con el hogar: su llegada, el saludo "
    "o su presentación, antes de empezar las preguntas del cuestionario.",
    true="La transcripción empieza con la llegada, el saludo o la presentación del ENCUESTADOR, o los incluye.",
    false="La transcripción empieza con la entrevista ya en marcha, en medio de preguntas del cuestionario, "
          "sin la llegada ni la presentación.",
)
GATE_CLOSING = noul(
    "G_CIERRE",
    "El fragmento incluye el final de la visita: el momento en que el ENCUESTADOR termina las preguntas "
    "del día y se despide o acuerda volver.",
    true="Se escucha el cierre: el ENCUESTADOR anuncia que terminó, agradece, se despide o acuerda la próxima visita.",
    false="La transcripción se corta mientras todavía se hacen preguntas del cuestionario, sin cierre ni despedida.",
)
GATES = {Scope.OPENING: GATE_OPENING, Scope.CLOSING: GATE_CLOSING}


# --- helpers over a set of sections -----------------------------------------------------------

def question_registry(sections: Iterable[Section]) -> dict[str, Question]:
    """All distinct questions by key (including gates and conditional triggers)."""
    reg: dict[str, Question] = {g.key: g for g in GATES.values()}
    for sec in sections:
        for ins in sec.instructions:
            if ins.trigger is not None:
                if ins.trigger.key in reg and reg[ins.trigger.key] != ins.trigger:
                    raise ValueError(f"trigger key {ins.trigger.key} defined twice with different content")
                reg[ins.trigger.key] = ins.trigger
            for q in ins.questions:
                if q.key in reg and reg[q.key] != q:
                    raise ValueError(f"question key {q.key} defined twice with different content")
                reg[q.key] = q
    return reg


def questions_for_scopes(
    sections: Iterable[Section],
    scopes: Iterable[Scope],
    *,
    stage1_only: bool = True,
) -> list[Question]:
    """Questions to ask on a window that plays the given scopes, gates first, without duplicates.

    When `stage1_only=True` (default), CONDITIONAL instructions with a `trigger` ask ONLY their
    Stage-1 trigger question here; their Stage-2 response question is asked only on windows where
    the trigger actually fired.
    """
    scopes = set(scopes)
    out: dict[str, Question] = {}
    for scope in (Scope.OPENING, Scope.CLOSING):
        if scope in scopes:
            out[GATES[scope].key] = GATES[scope]
    for sec in sections:
        for ins in sec.instructions:
            if ins.scope in scopes:
                if stage1_only and ins.trigger is not None:
                    out.setdefault(ins.trigger.key, ins.trigger)
                else:
                    for q in ins.questions:
                        out.setdefault(q.key, q)
    return list(out.values())


def calibration_group(question_key: str, sections: Iterable[Section]) -> str:
    """Calibration is pooled per kind/role (gate, trigger, obligation, prohibition, conditional, evidence)."""
    if question_key in {g.key for g in GATES.values()}:
        return "gate"
    for sec in sections:
        for ins in sec.instructions:
            if ins.trigger is not None and ins.trigger.key == question_key:
                return "trigger"
            if any(q.key == question_key for q in ins.questions):
                return ins.kind.value
    raise KeyError(question_key)
