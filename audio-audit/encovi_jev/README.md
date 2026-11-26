# ENCOVI 2023 interviewer audit with Jev: sections A1–A2

This code checks one interview transcript against sections A1 (*Apertura y contacto inicial*, 24 instructions) and A2 (*Conducta y actitud*, 27 instructions) of the rules file. It uses TypeSafe's Jev decision model through OpenRouter.

It outputs, per instruction, P(followed), P(broken) and P(can't tell), and per section the scores described in `GUIDE_JEV_QUESTIONS.md`, which explains the method.

| File | What it does |
|---|---|
| `GUIDE_JEV_QUESTIONS.md` | How to turn each instruction into a Jev question and score it by section |
| `rules.py` | Rule model, question builders, opening and closing gates |
| `rules_a1_a2.py` | The 51 instructions of A1 and A2 as 58 Jev questions, in Spanish |
| `transcript.py` | Loads JSON or TXT transcripts, normalizes speakers, builds windows |
| `jev_client.py` | OpenRouter Decisions API client (retries, cache, response checks) and an offline fake |
| `scoring.py` | Per-window → per-instruction → per-section probability math |
| `calibration.py` | Platt and temperature calibration from your gold labels |
| `audit.py` | Command-line entry point; writes `reporte.json` |
| `examples/transcript_example.json` | **Synthetic** transcript with planted errors, for testing |
| `tests/` | 29 tests: math against brute force, API schema, windowing, client |

## Setup

```bash
pip install -r requirements.txt          # requests (pytest for the tests)
export OPENROUTER_API_KEY=sk-or-...
```

## Run

```bash
python audit.py examples/transcript_example.json --mock          # offline; FAKE probabilities
python audit.py examples/transcript_example.json                 # real Jev; ~$0.0004
python audit.py visita.json --out reporte.json --speaker-map SPEAKER_00=ENCUESTADOR,SPEAKER_01=INFORMANTE
python audit.py visita2.json --not-first-contact                 # second-round visit: skip opening rules
```

The synthetic example has these errors planted on purpose:
- no "solo con fines estadísticos" during the presentation (A1-11)
- the second visit is mentioned only at the goodbye (A1-12)
- no mention of people with disabilities (A1-08)
- a promise of a possible aid program (A2-10)

Running it with your key is a quick check of whether Jev catches them.

**Transcript input.** Either JSON turns `[{"speaker": "E", "text": "...", "start": 12.3}]`, or TXT lines `[00:01:02] ENCUESTADOR: texto`. Labels E, ENCUESTADOR, I and INFORMANTE are recognized; anything else becomes OTRA_PERSONA unless you map it with `--speaker-map`.

## Report (`reporte.json`)

- `sections.A1` and `sections.A2` contain:
  - `compliance_rate` and `compliance_rate_weighted`
  - `p_all_followed`, with `p_all_followed_bounds`
  - `p_rate_at_least_90`
  - `p_at_most_1_broken` and `broken_count_pmf`
  - `coverage`
  - `top_risks`, each with its window and time range
- `instructions[]` holds, per rule:
  - `p_followed`, `p_broken`, `p_unknown`, `p_followed_if_applicable`
  - the per-window values and `worst_window`
  - for prohibitions, `windows_flagged` (window probability ≥ 0.7)
- `raw_answers` holds Jev's answers per window. `usage` holds the requests, input tokens and cost in USD.

## Calibrate (do this before trusting the section numbers)

```bash
python audit.py visita.json --export-labels labels/     # labels_template.csv + windows.md
#   fill the "label" column for ~300 rows (1/0 for noul, the correct option name for choice)
python calibration.py fit labels/labels_template.csv --out calibration.json
python audit.py visita.json --calibration calibration.json
```

## Tests

```bash
python -m pytest -q
```

## Notes

- **Endpoint.** `https://openrouter.ai/api/alpha/decisions` is an alpha endpoint, so its shape may change.
- **Model version.** The model is pinned to `typesafe/jev-1.14`. Calibration is only valid for the version it was fitted on.
- **Cache.** Responses are cached in `.jev_cache/`, keyed by the exact request. Re-runs are free and give the same answers. Delete the folder to force fresh calls.
- **Before sending.** Anonymize transcripts first. The question wording and the weights are a first draft; check them against your gold labels before they go into production.
