"""Load a diarized transcript and cut it into windows small enough for Jev's default mode.

Accepted inputs
  .json  [{"speaker": "E", "text": "...", "start": 12.3, "end": 15.0}, ...]  or  {"turns": [...]}
         (Spanish keys hablante/texto/inicio/fin also work)
  .txt   one turn per line: "ENCUESTADOR: texto" or "[00:01:02] I: texto". A line starts a new turn only
         if its label is known, mapped or ALL CAPS (e.g. SPEAKER_00); other lines continue the previous turn.
Speakers are normalized to ENCUESTADOR / INFORMANTE / OTRA_PERSONA, the labels the questions use.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from rules import Scope

INTERVIEWER, RESPONDENT, OTHER = "ENCUESTADOR", "INFORMANTE", "OTRA_PERSONA"
_KNOWN = {
    INTERVIEWER: {"E", "ENC", "ENCUESTADOR", "ENCUESTADORA", "ENTREVISTADOR", "ENTREVISTADORA", "INTERVIEWER"},
    RESPONDENT: {"I", "INF", "INFORMANTE", "ENTREVISTADO", "ENTREVISTADA", "RESPONDENT"},
    OTHER: {"O", "OTRO", "OTRA", "OTRA_PERSONA", "OTHER"},
}
_LABEL_TO_SPEAKER = {alias: canon for canon, aliases in _KNOWN.items() for alias in aliases}
_TXT_LINE = re.compile(r"^\s*(?:\[(?P<ts>[\d:.]+)\]\s*)?(?P<label>[\w ]{1,30}?)\s*:\s*(?P<text>.*)$")


@dataclass(frozen=True)
class Turn:
    speaker: str
    text: str
    start: float | None = None
    end: float | None = None

    def render(self) -> str:
        return f"{self.speaker}: {self.text}"


@dataclass(frozen=True)
class Window:
    index: int
    first_turn: int          # inclusive; indices refer to turns after over-long ones are split
    last_turn: int           # inclusive
    text: str                # rendered turns, one per line
    start: float | None
    end: float | None
    scopes: frozenset        # Scope values this window plays

    @property
    def n_bytes(self) -> int:
        return len(self.text.encode("utf-8"))


def normalize_speaker(label: str, speaker_map: Mapping[str, str] | None = None) -> str:
    raw = (label or "").strip()
    if speaker_map and raw in speaker_map:
        mapped = speaker_map[raw].strip().upper()
        return _LABEL_TO_SPEAKER.get(mapped, mapped)
    return _LABEL_TO_SPEAKER.get(raw.upper().replace(" ", "_"), OTHER)


def _is_label(label: str, speaker_map: Mapping[str, str] | None) -> bool:
    """A 'label:' prefix starts a new turn only if it is a known alias, a mapped label or all caps,
    so continuation lines such as 'y le dije: no' are not mistaken for speakers."""
    raw = label.strip()
    return (raw.upper().replace(" ", "_") in _LABEL_TO_SPEAKER or bool(speaker_map and raw in speaker_map)
            or (raw.isupper() and any(ch.isalpha() for ch in raw)))


def _seconds(ts) -> float | None:
    if ts is None or ts == "":
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    parts = [float(p) for p in str(ts).split(":")]
    return sum(p * 60 ** i for i, p in enumerate(reversed(parts)))


def load_transcript(path: str | Path, speaker_map: Mapping[str, str] | None = None) -> list[Turn]:
    path = Path(path)
    raw_text = path.read_text(encoding="utf-8")
    turns: list[Turn] = []
    if path.suffix.lower() == ".json":
        data = json.loads(raw_text)
        items = data.get("turns", data.get("turnos")) if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ValueError("JSON transcript must be a list of turns or {'turns': [...]}")
        for it in items:
            text = str(it.get("text", it.get("texto", ""))).strip()
            if text:
                turns.append(Turn(normalize_speaker(str(it.get("speaker", it.get("hablante", ""))), speaker_map),
                                  text, _seconds(it.get("start", it.get("inicio"))),
                                  _seconds(it.get("end", it.get("fin")))))
    else:
        for line in raw_text.splitlines():
            if not line.strip():
                continue
            m = _TXT_LINE.match(line)
            if m and _is_label(m["label"], speaker_map):
                turns.append(Turn(normalize_speaker(m["label"], speaker_map), m["text"].strip(), _seconds(m["ts"])))
            elif turns:  # continuation of the previous turn
                last = turns[-1]
                turns[-1] = Turn(last.speaker, f"{last.text} {line.strip()}", last.start, last.end)
            else:
                raise ValueError(f"first line has no speaker label: {line[:60]!r}")
    if not any(t.speaker == INTERVIEWER for t in turns):
        labels = sorted({t.speaker for t in turns})
        raise ValueError(f"no {INTERVIEWER} turns found (labels after mapping: {labels}); "
                         f"pass a speaker map, e.g. SPEAKER_00={INTERVIEWER},SPEAKER_01={RESPONDENT}")
    return turns


def _split_long_turn(turn: Turn, max_bytes: int) -> list[Turn]:
    """Split a turn whose rendered line exceeds max_bytes at sentence, then word, boundaries."""
    budget = max_bytes - len(f"{turn.speaker}: ".encode("utf-8")) - 1
    pieces, current = [], ""
    for token in re.split(r"(?<=[.!?¿¡…])\s+|\s+", turn.text):
        candidate = f"{current} {token}".strip()
        if len(candidate.encode("utf-8")) <= budget:
            current = candidate
            continue
        if current:
            pieces.append(current)
        while len(token.encode("utf-8")) > budget:  # a single giant token: hard cut
            cut = token.encode("utf-8")[:budget].decode("utf-8", "ignore")
            pieces.append(cut)
            token = token[len(cut):]
        current = token
    if current:
        pieces.append(current)
    return [Turn(turn.speaker, p, turn.start, turn.end) for p in pieces]


def make_windows(turns: Sequence[Turn], max_bytes: int = 12_000, overlap_turns: int = 2,
                 first_contact: bool = True) -> list[Window]:
    """Consecutive windows of whole turns, each at most max_bytes of rendered text.

    Consecutive windows share `overlap_turns` turns so an exchange cut by a boundary is still seen
    whole in one window. Window 0 plays OPENING (first-contact visits only), the last plays CLOSING.
    """
    if max_bytes < 500:
        raise ValueError("max_bytes too small")
    flat: list[Turn] = []
    for t in turns:
        flat.extend(_split_long_turn(t, max_bytes) if len(t.render().encode("utf-8")) + 1 > max_bytes else [t])
    sizes = [len(t.render().encode("utf-8")) + 1 for t in flat]

    spans, start = [], 0
    while start < len(flat):
        end, size = start, 0
        while end < len(flat) and size + sizes[end] <= max_bytes:
            size += sizes[end]
            end += 1
        spans.append((start, end))
        if end >= len(flat):
            break
        start = max(end - overlap_turns, start + 1)

    windows = []
    for i, (a, b) in enumerate(spans):
        scopes = {Scope.ALL}
        if i == 0 and first_contact:
            scopes.add(Scope.OPENING)
        if i == len(spans) - 1:
            scopes.add(Scope.CLOSING)
        chunk = flat[a:b]
        starts = [t.start for t in chunk if t.start is not None]
        ends = [e for e in ((t.end if t.end is not None else t.start) for t in chunk) if e is not None]
        windows.append(Window(i, a, b - 1, "\n".join(t.render() for t in chunk),
                              min(starts) if starts else None, max(ends) if ends else None, frozenset(scopes)))
    return windows
