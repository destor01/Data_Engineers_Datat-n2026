"""Calibrate Jev's probabilities on your own gold labels before combining them.

Why: section scores multiply many probabilities, so a small systematic error per window grows
(0.02 of spurious violation probability in each of 11 windows becomes 1 - 0.98**11 = 0.20).

Fitted per group (gate, obligation, prohibition, conditional, evidence), pooled across questions:
  Noul   -> Platt scaling        p' = sigmoid(a * logit(p) + b)
  Choice -> temperature scaling  p'_k proportional to p_k ** (1 / T)
Groups without enough labels stay uncalibrated (identity).

Labels CSV (the template comes from `audit.py --export-labels`): columns group, question_type,
raw, label. Noul rows: raw = probability, label = 1/0 (si/no, true/false). Choice rows: raw = JSON
{option: probability}, label = the correct option name. Empty labels are skipped.

    python calibration.py fit labels.csv --out calibration.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

EPS = 1e-4
MIN_LABELS = 30


def _logit(p: float) -> float:
    p = min(1 - EPS, max(EPS, float(p)))
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


def _normalize(probs: Mapping[str, float]) -> dict:
    total = sum(max(0.0, float(v)) for v in probs.values())
    if total <= 0:
        return {k: 1.0 / len(probs) for k in probs}
    return {k: max(0.0, float(v)) / total for k, v in probs.items()}


class Calibrator:
    """Identity until parameters are loaded; groups without parameters pass through unchanged."""

    def __init__(self, noul: Mapping[str, Sequence[float]] | None = None,
                 choice: Mapping[str, float] | None = None):
        self.noul_params = {g: tuple(ab) for g, ab in (noul or {}).items()}
        self.choice_params = dict(choice or {})

    def noul(self, p: float, group: str) -> float:
        if group not in self.noul_params:
            return float(p)
        a, b = self.noul_params[group]
        return _sigmoid(a * _logit(p) + b)

    def choice(self, probs: Mapping[str, float], group: str) -> dict:
        probs = _normalize(probs)
        temp = self.choice_params.get(group)
        if temp is None:
            return probs
        return _normalize({k: max(EPS, v) ** (1.0 / temp) for k, v in probs.items()})

    def to_dict(self) -> dict:
        return {"noul_platt": {g: list(ab) for g, ab in self.noul_params.items()},
                "choice_temperature": self.choice_params}

    @classmethod
    def load(cls, path: str | Path) -> "Calibrator":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(d.get("noul_platt"), d.get("choice_temperature"))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def fit_platt(ps: Sequence[float], ys: Sequence[int], l2: float = 1e-2, iters: int = 100) -> tuple[float, float]:
    """Logistic regression of y on logit(p) by Newton-Raphson, shrunk toward identity (a=1, b=0)."""
    xs = [_logit(p) for p in ps]
    a, b = 1.0, 0.0
    for _ in range(iters):
        ga, gb = l2 * (a - 1.0), l2 * b
        haa, hab, hbb = l2, 0.0, l2
        for x, y in zip(xs, ys):
            s = _sigmoid(a * x + b)
            ga += (s - y) * x
            gb += s - y
            w = s * (1 - s)
            haa += w * x * x
            hab += w * x
            hbb += w
        det = haa * hbb - hab * hab
        if det <= 1e-12:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) < 1e-8 and abs(db) < 1e-8:
            break
    return a, b


def fit_temperature(prob_dicts: Sequence[Mapping[str, float]], labels: Sequence[str]) -> float:
    """Temperature minimizing negative log-likelihood (golden-section search over log T)."""
    def nll(log_t: float) -> float:
        cal = Calibrator(choice={"g": math.exp(log_t)})
        return -sum(math.log(max(EPS, cal.choice(p, "g")[y])) for p, y in zip(prob_dicts, labels))

    lo, hi = -3.0, 3.0
    phi = (math.sqrt(5) - 1) / 2
    c, d = hi - phi * (hi - lo), lo + phi * (hi - lo)
    for _ in range(80):
        if nll(c) < nll(d):
            hi = d
        else:
            lo = c
        c, d = hi - phi * (hi - lo), lo + phi * (hi - lo)
    return math.exp((lo + hi) / 2)


def brier(ps: Sequence[float], ys: Sequence[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)


def ece(ps: Sequence[float], ys: Sequence[int], bins: int = 10) -> float:
    """Expected calibration error with equal-width bins."""
    total, err = len(ps), 0.0
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        idx = [j for j, p in enumerate(ps) if lo <= p < hi or (i == bins - 1 and p == 1.0)]
        if idx:
            err += len(idx) / total * abs(sum(ps[j] for j in idx) / len(idx) - sum(ys[j] for j in idx) / len(idx))
    return err


def _parse_label(s: str) -> int | None:
    s = s.strip().lower()
    if s in {"1", "si", "sí", "true", "yes", "y"}:
        return 1
    if s in {"0", "no", "false", "n"}:
        return 0
    return None


def fit_from_csv(path: str | Path, min_labels: int = MIN_LABELS) -> tuple[Calibrator, dict]:
    nouls: dict[str, tuple[list, list]] = {}
    choices: dict[str, tuple[list, list]] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            label = (row.get("label") or "").strip()
            if not label:
                continue
            group = row["group"]
            if row["question_type"] == "noul":
                y = _parse_label(label)
                if y is not None:
                    nouls.setdefault(group, ([], []))[0].append(float(row["raw"]))
                    nouls[group][1].append(y)
            else:
                probs = json.loads(row["raw"])
                if label in probs:
                    choices.setdefault(group, ([], []))[0].append(probs)
                    choices[group][1].append(label)
    report, noul_params, temps = {}, {}, {}
    for g, (ps, ys) in nouls.items():
        entry = {"n": len(ps), "brier_raw": round(brier(ps, ys), 4), "ece_raw": round(ece(ps, ys), 4)}
        if len(ps) >= min_labels and 0 < sum(ys) < len(ys):
            a, b = fit_platt(ps, ys)
            cal = [_sigmoid(a * _logit(p) + b) for p in ps]
            noul_params[g] = (a, b)
            entry.update(a=round(a, 4), b=round(b, 4), brier_cal_in_sample=round(brier(cal, ys), 4),
                         ece_cal_in_sample=round(ece(cal, ys), 4))
        else:
            entry["note"] = f"not fitted: needs >= {min_labels} labels with both outcomes"
        report[f"noul/{g}"] = entry
    for g, (pds, ys) in choices.items():
        acc = sum(max(p, key=p.get) == y for p, y in zip(pds, ys)) / len(ys)
        entry = {"n": len(ys), "accuracy": round(acc, 4)}
        if len(ys) >= min_labels:
            temps[g] = fit_temperature(pds, ys)
            entry["temperature"] = round(temps[g], 4)
        else:
            entry["note"] = f"not fitted: needs >= {min_labels} labels"
        report[f"choice/{g}"] = entry
    return Calibrator(noul_params, temps), report


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit", help="fit calibration parameters from a labeled CSV")
    f.add_argument("labels")
    f.add_argument("--out", default="calibration.json")
    f.add_argument("--min-labels", type=int, default=MIN_LABELS)
    args = ap.parse_args(argv)
    cal, report = fit_from_csv(args.labels, args.min_labels)
    cal.save(args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
