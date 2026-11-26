"""Calibration recovers known distortions on simulated data."""
import csv
import json
import math
import random

import pytest

from calibration import Calibrator, _logit, _sigmoid, fit_from_csv, fit_from_records, fit_platt, fit_temperature


def test_identity_without_parameters():
    cal = Calibrator()
    assert cal.noul(0.37, "prohibition") == 0.37
    assert cal.choice({"a": 2.0, "b": 2.0}, "conditional") == {"a": 0.5, "b": 0.5}


def test_platt_recovers_known_parameters():
    rng = random.Random(7)
    a_true, b_true = 0.6, -1.0
    ps = [rng.uniform(0.01, 0.99) for _ in range(5000)]
    ys = [int(rng.random() < _sigmoid(a_true * _logit(p) + b_true)) for p in ps]
    a, b = fit_platt(ps, ys)
    assert a == pytest.approx(a_true, abs=0.1) and b == pytest.approx(b_true, abs=0.1)


def test_temperature_recovers_overconfidence():
    rng = random.Random(8)
    t_true, probs, labels = 2.0, [], []
    for _ in range(4000):
        z = [rng.gauss(0, 2.5) for _ in range(3)]
        raw = [math.exp(x) for x in z]
        raw = {k: v / sum(raw) for k, v in zip("xyz", raw)}
        true = [math.exp(x / t_true) for x in z]
        labels.append(rng.choices("xyz", weights=true)[0])
        probs.append(raw)
    assert fit_temperature(probs, labels) == pytest.approx(t_true, rel=0.12)


def test_fit_from_csv_round_trip(tmp_path):
    rng = random.Random(9)
    path = tmp_path / "labels.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["window", "question_key", "group", "question_type", "instructions", "options", "raw", "label"])
        for i in range(200):
            p = rng.uniform(0.01, 0.99)
            y = int(rng.random() < _sigmoid(0.5 * _logit(p) - 1.5))     # Jev over-reports violations
            wr.writerow([i, "A2_10_promesas", "prohibition", "noul", "", "", p, "sí" if y else "no"])
        for i in range(60):
            probs = {"sin_x": 0.8, "maneja_bien": 0.15, "maneja_mal": 0.05}
            wr.writerow([i, "A1_19_renuencia", "conditional", "choice", "", "", json.dumps(probs),
                         rng.choices(list(probs), weights=[0.6, 0.3, 0.1])[0]])
        wr.writerow([0, "A1_01_saludo", "obligation", "noul", "", "", 0.9, ""])   # unlabeled: skipped
    cal, report = fit_from_csv(path)
    assert "a" in report["noul/prohibition"] and "temperature" in report["choice/conditional"]
    assert report["noul/prohibition"]["brier_cal_in_sample"] <= report["noul/prohibition"]["brier_raw"]
    assert cal.noul(0.10, "prohibition") < 0.10            # spurious low probabilities shrink
    assert "obligation" not in cal.noul_params              # no labels -> stays identity
    cal.save(tmp_path / "c.json")
    assert Calibrator.load(tmp_path / "c.json").to_dict() == cal.to_dict()


def test_fit_from_records_supports_in_memory_supervisor_edits():
    rng = random.Random(11)
    records = []
    for _ in range(40):
        p = rng.uniform(0.05, 0.95)
        y = int(rng.random() < _sigmoid(0.5 * _logit(p) - 1.2))
        records.append({"group": "prohibition", "question_type": "noul", "raw": p, "label": "1" if y else "0"})
    cal, report = fit_from_records(records, min_labels=30)
    assert cal.is_fitted
    assert report["noul/prohibition"]["fitted"] is True
    assert cal.noul(0.2, "prohibition") < 0.2
