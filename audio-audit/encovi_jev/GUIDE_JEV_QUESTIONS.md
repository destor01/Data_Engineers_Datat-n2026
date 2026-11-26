# Turning ENCOVI instructions into Jev questions and scoring them by section

**What you get per interview**
- **Per instruction:** P(followed), P(broken), P(can't tell).
- **Per section:**
  - the expected share of applicable instructions followed
  - P(he broke none)
  - P(he followed at least 90%)
  - the instructions most likely broken, with the time they happened

**Scope**
- **Source.** The final manual (`.md`) is the same text as the PDF the rules file was built from: 99.4% of its text matches, and the differences are tables, formulas and figure captions. Rule IDs and page numbers stand.
- **"First two sections"** means sections A1 and A2 of the rules file:
  - A1, *Apertura y contacto inicial*: 24 instructions
  - A2, *Conducta y actitud*: 27 instructions

  Every interview is judged on both. The code is in `rules_a1_a2.py`.
- **Jev on OpenRouter:**
  - Call `POST https://openrouter.ai/api/alpha/decisions` with `model: typesafe/jev-1.14`.
  - Price: $0.042 per million input tokens; output is free.
  - Jev is not served on `/chat/completions`.
  - The endpoint is alpha, so its shape may change.

---

## 1. Pipeline

```
transcript with speaker labels
  → windows of ≤ 12,000 bytes, 2 turns of overlap
  → Jev questions per window: opening window / closing window / every window
  → calibration (per kind of instruction)
  → per instruction: (c, v, u) = P(followed), P(broken), P(can't tell)
  → per section: compliance rate, P(all followed), distribution of the number broken
```

## 2. Step 1: classify the instruction

| The manual says | Kind | Jev question | Asked on | In A1+A2 |
|---|---|---|---|---|
| "Do X" at a known moment, and X must be spoken (greet, say your name, confidentiality) | `OBLIGATION` | Noul; true = X happened | opening or closing window, plus a gate | 13 |
| "Do X", but X can be silent (hand over the letter, review the form) | `EVIDENCE` | Choice: *done / sign it wasn't done / no mention* | opening or closing window, plus a gate | 2 |
| "NO …" or continuous conduct (*mantener, mostrar, evitar*) | `PROHIBITION` | Noul; true = **the violation** happened | every window | 21 |
| "Si / Ante / Cuando T: do X" | `CONDITIONAL` | Choice: *T absent / T and X / T and not X* | every window (2 rules: opening only) | 15 |
| Not audible (uniform, forms, pen colors) | none | don't ask; section F of the rules file | — | — |

## 3. Step 2: write the question

TypeSafe's own guidance is behind rules 1, 2, 4, 5, 7 and 9.

1. **One judgment per question.** Split "y" or "o" into parts and combine them in code:
   - Obligations: AND, as a product.
   - Prohibitions: OR, as 1 − ∏(1 − p).
   - Examples: A1-02 becomes *name* + *INE*; A2-03 becomes *acts important* + *authoritarian*.
   - A1-09 reuses A1-04's question instead of asking the same thing twice.
2. **True means it happened.** For prohibitions, describe the violation:
   - Write *"El ENCUESTADOR ofrece o promete algo…"*, not *"…no promete nada"*.
   - Avoid double negatives.
3. **Name speakers exactly as the state labels them:** `ENCUESTADOR`, `INFORMANTE`, `OTRA_PERSONA`.
4. **`false` is a concrete situation, not "no hace X".** For example, *"Empieza a preguntar sin pedir colaboración ni permiso."*
5. **Put the line between look-alikes in the criteria:**
   - insisting (A1-23) vs. pressuring (A2-11)
   - neutral probing vs. pressure
   - re-asking a question the manual tells you to re-ask (p.43) vs. not listening (A2-14)
6. **Anchor the timing when it matters.** Use *"Al presentar la encuesta, antes de las preguntas del cuestionario…"* (A1-04 to A1-12), so a mention only at the goodbye doesn't count.
7. **Choice options must be exhaustive, exclusive and descriptively named.** Jev reads the option names but never sees question IDs.
   - A Choice always picks some option. Because "trigger absent" is one of the options, that is safe here.
   - When the trigger happens twice in one window, the criteria say a single failure counts as *broken*.
8. **Don't make the manual's example wording mandatory.** The p.39 presentation is *"una forma… podría ser"*. Use *"por ejemplo"*.
9. **No preambles or output instructions.** Page numbers and notes go in the rule spec, not in the question.

**Templates, taken from the code:**

```json
"A1_10_confidencial": {"type": "noul",
  "instructions": "Al presentar la encuesta, antes de las preguntas del cuestionario, el ENCUESTADOR dice que la información que dé el hogar es confidencial.",
  "criteria": {"true": "Dice que los datos son confidenciales o que no se publican de forma individual; citar la Ley Orgánica del INE o el Decreto 3-85 cuenta, pero no es necesario.",
               "false": "Presenta la encuesta sin hablar de confidencialidad, o solo lo hace más tarde, cuando el INFORMANTE lo pregunta."}}

"A2_10_promesas": {"type": "noul",
  "instructions": "El ENCUESTADOR ofrece o promete algo al INFORMANTE para conseguir que colabore.",
  "criteria": {"true": "Promete o insinúa ayudas, programas, regalos, dinero o mejoras para la comunidad a cambio de responder…",
               "false": "Pide la colaboración explicando la importancia y la confidencialidad de la encuesta, sin ofrecer nada a cambio."}}

"A1_19_renuencia": {"type": "choice",
  "instructions": "Si el INFORMANTE se muestra renuente a dar la entrevista, ¿el ENCUESTADOR le lee algunas preguntas como ejemplo para darle confianza?",
  "criteria": {"sin_renuencia": "El INFORMANTE acepta la entrevista sin resistirse.",
               "lee_preguntas_de_ejemplo": "El INFORMANTE duda o se resiste y el ENCUESTADOR le lee algunas preguntas del cuestionario como ejemplo.",
               "no_lee_ejemplos": "El INFORMANTE duda o se resiste y el ENCUESTADOR no le lee ninguna pregunta de ejemplo."}}
```

`EVIDENCE` uses the same three-option shape as `CONDITIONAL`, with *no mention* in place of *trigger absent*. See A1-03 (the letter) and A2-26.

## 4. Step 3: state, windows and requests

- **State object:** `{"descripcion": "<what the labels mean>", "posicion": "Fragmento 3 de 9.", "transcripcion": "ENCUESTADOR: …\nINFORMANTE: …"}`.
  - Timestamps stay out of the state; the report keeps them so supervisors can find the moment.
  - Speaker labels are required. Map diarization labels with `--speaker-map SPEAKER_00=ENCUESTADOR,SPEAKER_01=INFORMANTE`.
- **Why 12,000 bytes per window:**
  - In default mode, Jev limits the state plus any one question to 32k tokens.
  - OpenRouter switches to long-context mode above about 32,000 bytes. That mode is slower and less accurate.
  - The code caps each whole request body at 30,000 bytes and packs the questions into as many requests as that needs.
  - At 12,000 bytes, a middle window's 36 questions (17,177 bytes) fit in one request.

| Window | Questions | Typical requests |
|---|---|---|
| first (opening + every-window) | 54, including gate `G_APERTURA` | 2 |
| middle | 36 | 1 |
| last (closing + every-window) | 40, including gate `G_CIERRE` | 1–2 |

- **Gates** ask whether the opening or the closing is in the recording at all. Without them, a recording that starts late would read as "didn't greet".
- **Cost:** Jev bills the state once per request.
  - These figures are my estimate. They assume about 865 bytes of transcript per minute of speech (the synthetic example) and 3.5–4.5 bytes per token.
  - A one-hour recording comes to about 5 windows, 6 requests and roughly 38–48k tokens, about **$0.002**.
  - A three-hour household comes to about $0.005.
  - `usage.cost` in the report gives the real figure.

## 5. Step 4: from Jev answers to "did he follow this instruction?"

**Window level:**

| Kind | c (followed) | v (broken) | u (can't tell) |
|---|---|---|---|
| OBLIGATION (parts p₁…pₖ) | ∏ pᵢ | 1 − ∏ pᵢ | 0 |
| PROHIBITION (parts p₁…pₖ) | ∏ (1 − pᵢ) | 1 − ∏ (1 − pᵢ) | 0 |
| CONDITIONAL / EVIDENCE | p(handled / done) | p(mishandled / sign not done) | p(trigger absent / no mention) |

**Interview level:**
- **Opening or closing (one window), with gate g = P(the moment is in the recording):**
  c = g·c_w, v = g·v_w, u = (1 − g) + g·u_w.
- **Every window (prohibitions and conditionals).** A violation in any window breaks the instruction:
  u = ∏ u_w, v = 1 − ∏ (1 − v_w), c = 1 − u − v.

**Fields per instruction in the report:**
- `p_followed_if_applicable` = c / (c + v)
- `p_broken`
- `p_unknown`
- `worst_window`, with its time range
- for every-window rules:
  - `expected_broken_windows` = Σ v_w
  - `windows_flagged` (v_w ≥ 0.7)
  - `windows_review` (0.3 ≤ v_w < 0.7). These are TypeSafe's starting thresholds for a Noul.

## 6. Step 5: section score

| Field | Formula | Answers | Assumes |
|---|---|---|---|
| `compliance_rate` | Σc / Σ(c + v) | expected share of the applicable instructions he followed | nothing |
| `compliance_rate_weighted` | Σw·c / Σw·(c + v) | the same, by severity (w = 1–3) | weights agreed before looking at results |
| `p_all_followed` | ∏(1 − vᵢ) | probability he broke none | independence. Violations by one interviewer tend to cluster, and then this is a lower bound |
| `p_all_followed_bounds` | [max(0, 1 − Σv), 1 − max v] | the same, under any dependence | nothing |
| `p_at_most_1_broken`, `broken_count_pmf` | Poisson-binomial over vᵢ | tolerance ("at most one slip") | independence |
| `p_rate_at_least_80/90`, `rate_quantiles` | exact distribution of followed ÷ applicable | "P(he followed ≥ 90%)" | independence |
| `coverage` | Σ(c + v) / n | how much of the section could be judged at all | nothing |

**Worked example.** These numbers are asserted in `tests/test_scoring.py`.

| Instruction | c | v | u |
|---|---|---|---|
| 1 | 0.90 | 0.10 | 0 |
| 2 | 0.60 | 0.20 | 0.20 |
| 3 | 0 | 0 | 1 (didn't apply) |
| 4 | 0.95 | 0.05 | 0 |

- compliance rate = 2.45 / 2.80 = **0.875**
- P(all followed) = 0.9 × 0.8 × 1 × 0.95 = **0.684**, bounds [0.65, 0.80]
- coverage = 0.70

**What to show:**
- **Per interview:** `compliance_rate` and `top_risks` with their times, so the supervisor knows which minute to play. Show `p_all_followed` only after calibration (see §7).
- **Per interviewer:** use the interview as the unit. Average the per-interview `compliance_rate` with shrinkage, as in the earlier plan. Don't pool instructions across interviews.

## 7. Two traps and how the code handles them

1. **Noise compounds over windows.**
   - A spurious 0.02 violation probability in each of 11 windows becomes 1 − 0.98¹¹ = 0.20 for the interview.
   - With the same fake noise, the mock run's A2 rate fell from 96% with one window to 86% with three. Longer interviews look worse.
   - **Fix:**
     - Calibrate per kind before combining (§8).
     - Compare interviewers on conduct with flagged windows per hour, or Σ v_w per hour, not with `p_all_followed`.
2. **Absence of evidence.**
   - Silence counts as "not done" only when the act must be spoken and the gate says the moment was recorded.
   - Acts that can be silent are `EVIDENCE` rules, and *no mention* goes to u, never to v.

## 8. Calibrate and validate before trusting any number

1. Run `python audit.py t.json --export-labels labels/`. It writes `labels_template.csv`, one row per window and question, plus `windows.md` with the window texts.
2. Label about 300 rows.
   - Oversample rows with raw ≥ 0.3. Calibration models P(label | raw), so sampling on raw does not bias it.
   - Calibration needs at least 30 labels per kind, with both outcomes present.
3. Run `python calibration.py fit labels.csv --out calibration.json`.
   - Nouls get Platt scaling and Choices get temperature scaling, each fitted per kind.
   - It prints Brier score and ECE before and after. These are in-sample, so keep a holdout set.
4. Run `python audit.py t.json --calibration calibration.json`.
5. Keep the model pinned to `typesafe/jev-1.14`, not `~typesafe/jev-latest`. Refit when you change versions.

**Checks:**
- **Precision@k:** of the k instructions flagged most strongly, how many does a human confirm by listening?
- **AUPRC** for *broken*.

**Run-to-run noise:** identical calls can differ by a few hundredths. Use `--repeats 3` to average them.

**Testing wordings:** send two versions of a question as separate questions in the same request. Keep the one that agrees better with your labels.

## 9. Extending to the other 455 instructions

- **A3–A5 (asking technique: verbatim reading, no leading, reading options only for ":" questions).** These are judged per exchange, not per window.
  - Split windows into question→answer exchanges in code.
  - Ask per exchange: a Score for *exacta / cambio leve / cambio mayor*, and a Noul for *induce la respuesta*.
  - Report rates per 100 questions.
- **Part B (chapter rules).**
  - First tag each window with one Noul per chapter: *"En este fragmento se aplican preguntas del Capítulo V (Salud)"*. Several can be true at once.
  - Use that tag as the gate g_w for the chapter's rules:
    - Prohibitions: v = 1 − ∏(1 − g_w·v_w).
    - "Do X once in the chapter": c = 1 − ∏(1 − g_w·c_w). This rises with noise, so calibrate first.
- **T (word-for-word scripts):** fuzzy string matching in code. No Jev needed.
- **D (dates and metadata) and F (not audible):** these don't go through Jev.

## 10. Open decisions for your team

- **Severity weights.** Current values are a proposal: 3 protects the informant or the data, 2 is an explicit procedure, 1 is an example or courtesy detail.
- **A1-09 sponsors.** The manual names none besides the INE; currently, naming the INE counts.
- **A1-05 and A1-07** come only from the example presentation ("podría ser"). They have weight 1 for now; you could drop them.
- **A1-18 (INE phone number)** is modeled as conditional, because the manual puts it in the same paragraph as *"si el informante le solicita ampliar la información"*.
- **Second-round visits:** run with `--not-first-contact`, which skips the opening rules.
- **Language.** Questions are in Spanish to match the transcripts, and Jev's docs list no supported languages, so measure accuracy on the gold set. Interviews in a Mayan language need their own gold set.
- **Privacy.** Anonymize transcripts before sending them. Check TypeSafe's and OpenRouter's data terms for household data.
