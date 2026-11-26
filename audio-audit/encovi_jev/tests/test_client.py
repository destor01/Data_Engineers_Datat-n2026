"""HTTP client behavior against a stub session: request shape, retries, errors, cache, validation."""
import json

import pytest

from jev_client import DECISIONS_URL, JevClient, JevError

QUESTIONS = {"q1": {"type": "noul", "instructions": "x", "criteria": {"true": "a", "false": "b"}},
             "q2": {"type": "choice", "instructions": "y", "criteria": {"uno": "1", "dos": "2"}}}
GOOD = {"model": "typesafe/jev-1.14-20261014",
        "answers": {"q1": {"type": "noul", "noul": 0.8},
                    "q2": {"type": "choice", "choice": "uno", "probabilities": {"uno": 0.7, "dos": 0.3},
                           "confidence": 0.7}},
        "usage": {"input_tokens": 1000, "output_tokens": 20, "cost": 0.000042}}


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        return self._body


class Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, headers, data, timeout):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(data.decode("utf-8"))})
        return self.responses.pop(0)


def _client(session, tmp_path, **kw):
    kw.setdefault("cache_dir", tmp_path)
    return JevClient(api_key="test-key", session=session, sleep=lambda s: None, **kw)


def test_request_shape_and_usage(tmp_path):
    s = Session(Resp(200, GOOD))
    c = _client(s, tmp_path)
    out = c.decide({"transcripcion": "ENCUESTADOR: hola"}, QUESTIONS)
    call = s.calls[0]
    assert call["url"] == DECISIONS_URL
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["body"] == {"model": "typesafe/jev-1.14", "state": {"transcripcion": "ENCUESTADOR: hola"},
                            "questions": QUESTIONS}
    assert out["answers"]["q1"]["noul"] == 0.8
    assert c.usage.as_dict() == {"requests": 1, "cache_hits": 0, "input_tokens": 1000, "cost_usd": 0.000042}


def test_retries_retryable_status_then_succeeds(tmp_path):
    s = Session(Resp(429, {"error": "rate"}, {"Retry-After": "0"}), Resp(529, {}), Resp(200, GOOD))
    _client(s, tmp_path).decide("estado", QUESTIONS)
    assert len(s.calls) == 3


def test_non_retryable_status_raises_immediately(tmp_path):
    s = Session(Resp(402, {"error": "insufficient credits"}))
    with pytest.raises(JevError) as err:
        _client(s, tmp_path).decide("estado", QUESTIONS)
    assert err.value.status == 402 and len(s.calls) == 1


def test_gives_up_after_max_retries(tmp_path):
    s = Session(*[Resp(503, {})] * 3)
    with pytest.raises(JevError):
        _client(s, tmp_path, max_retries=2).decide("estado", QUESTIONS)
    assert len(s.calls) == 3


def test_cache_avoids_paying_twice(tmp_path):
    s = Session(Resp(200, GOOD))
    c = _client(s, tmp_path)
    c.decide("estado", QUESTIONS)
    c.decide("estado", QUESTIONS)
    assert len(s.calls) == 1 and c.usage.cache_hits == 1


def test_validation_rejects_missing_or_mistyped_answers(tmp_path):
    missing = {**GOOD, "answers": {"q1": GOOD["answers"]["q1"]}}
    with pytest.raises(JevError):
        _client(Session(Resp(200, missing)), tmp_path, cache_dir=None).decide("e", QUESTIONS)
    wrong = {**GOOD, "answers": {**GOOD["answers"], "q1": {"type": "noul", "noul": 1.7}}}
    with pytest.raises(JevError):
        _client(Session(Resp(200, wrong)), tmp_path, cache_dir=None).decide("e", QUESTIONS)


def test_refusal_is_accepted(tmp_path):
    refused = {**GOOD, "answers": {**GOOD["answers"], "q2": {"type": "refusal"}}}
    out = _client(Session(Resp(200, refused)), tmp_path).decide("e", QUESTIONS)
    assert out["answers"]["q2"]["type"] == "refusal"


def test_missing_key_is_an_error(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(JevError):
        JevClient()
