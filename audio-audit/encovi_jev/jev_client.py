"""Client for TypeSafe Jev through OpenRouter's Decisions API, plus an offline fake for tests.

Request (POST https://openrouter.ai/api/alpha/decisions, Authorization: Bearer $OPENROUTER_API_KEY):
    {"model": "typesafe/jev-1.14", "state": <str|object|array>,
     "questions": {"<id>": {"type": "noul"|"choice"|"score", "instructions": "...", "criteria": ...}}}
Response:
    {"id", "model", "provider", "answers": {"<id>": {"type": "noul", "noul": 0.93} |
       {"type": "choice", "choice": "...", "probabilities": {...}, "confidence": ...} | {"type": "refusal"}},
     "usage": {"input_tokens", "output_tokens", "cost"}}
Jev is not served on /chat/completions. The Decisions endpoint is alpha, so its shape may change.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

import requests

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.14"      # pin a version: calibration is only valid for the model it was fit on
PRICE_PER_INPUT_TOKEN = 0.042e-6         # USD, OpenRouter list price for Jev; output tokens are free
RETRYABLE = frozenset({429, 500, 502, 503, 524, 529})


class JevError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def body_bytes(body: Mapping[str, Any]) -> int:
    """UTF-8 size of a request body as this client serializes it."""
    return len(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def validate_response(resp: Any, questions: Mapping[str, Mapping[str, Any]]) -> None:
    """Fail loudly on anything the scoring code could misread. Refusals are allowed."""
    answers = resp.get("answers") if isinstance(resp, dict) else None
    if not isinstance(answers, dict):
        raise JevError("response has no 'answers' object")
    for key, q in questions.items():
        a = answers.get(key)
        if not isinstance(a, dict):
            raise JevError(f"missing answer for question {key!r}")
        kind = a.get("type")
        if kind == "refusal":
            continue
        if kind != q["type"]:
            raise JevError(f"{key!r}: expected a {q['type']} answer, got {kind!r}")
        if kind == "noul":
            p = a.get("noul")
            if not isinstance(p, (int, float)) or not 0.0 <= p <= 1.0:
                raise JevError(f"{key!r}: noul value {p!r} outside [0, 1]")
        elif kind == "choice":
            probs = a.get("probabilities")
            if not isinstance(probs, dict) or not probs:
                raise JevError(f"{key!r}: choice answer without probabilities")
            unknown = set(probs) - set(q["criteria"])
            if unknown:
                raise JevError(f"{key!r}: probabilities for unknown options {sorted(unknown)}")
            if any(not isinstance(v, (int, float)) or v < 0 for v in probs.values()):
                raise JevError(f"{key!r}: invalid probability values")


@dataclass
class Usage:
    requests: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    cost_usd: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, resp: Mapping[str, Any], cached: bool) -> None:
        with self._lock:
            if cached:
                self.cache_hits += 1
                return
            u = resp.get("usage") or {}
            tokens = int(u.get("input_tokens") or 0)
            self.requests += 1
            self.input_tokens += tokens
            cost = u.get("cost")
            self.cost_usd += float(cost) if isinstance(cost, (int, float)) else tokens * PRICE_PER_INPUT_TOKEN

    def as_dict(self) -> dict:
        return {"requests": self.requests, "cache_hits": self.cache_hits,
                "input_tokens": self.input_tokens, "cost_usd": round(self.cost_usd, 6)}


class JevClient:
    """Thread-safe Decisions API client with retries and an on-disk response cache.

    The cache key is a hash of the exact request body, so re-running an audit costs nothing and
    reproduces the same probabilities; delete the cache directory to force fresh calls.
    """

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL, url: str = DECISIONS_URL,
                 timeout: float = 60.0, max_retries: int = 5, cache_dir: str | Path | None = ".jev_cache",
                 app_title: str = "encovi-jev-audit", session: Any = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise JevError("no API key: set OPENROUTER_API_KEY or pass api_key")
        self.model, self.url, self.timeout, self.max_retries = model, url, timeout, max_retries
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                        "X-Title": app_title}
        self.usage = Usage()
        self._sleep = sleep

    def decide(self, state: Any, questions: Mapping[str, Mapping[str, Any]], repeat_index: int = 0) -> dict:
        body = {"model": self.model, "state": state, "questions": dict(questions)}
        path = self._cache_path(body, repeat_index)
        if path and path.exists():
            resp = json.loads(path.read_text(encoding="utf-8"))
            self.usage.add(resp, cached=True)
            return resp
        resp = self._post(body)
        validate_response(resp, questions)
        if path:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(resp, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        self.usage.add(resp, cached=False)
        return resp

    def _cache_path(self, body: Mapping[str, Any], repeat_index: int) -> Path | None:
        if not self.cache_dir:
            return None
        digest = hashlib.sha256((json.dumps(body, ensure_ascii=False, sort_keys=True)
                                 + f"#repeat={repeat_index}").encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _post(self, body: Mapping[str, Any]) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        for attempt in range(self.max_retries + 1):
            try:
                r = self.session.post(self.url, headers=self.headers, data=data, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == self.max_retries:
                    raise JevError(f"network error after {attempt + 1} attempts: {exc}") from exc
                self._sleep(self._backoff(attempt, None))
                continue
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError as exc:
                    raise JevError("HTTP 200 with a non-JSON body") from exc
            if r.status_code in RETRYABLE and attempt < self.max_retries:
                self._sleep(self._backoff(attempt, r.headers.get("Retry-After")))
                continue
            raise JevError(f"HTTP {r.status_code}: {r.text[:500]}", r.status_code)
        raise JevError("unreachable")  # pragma: no cover

    @staticmethod
    def _backoff(attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(60.0, float(retry_after))
            except ValueError:
                pass
        return min(60.0, 2.0 ** attempt) * (0.5 + random.random())


class FakeJev:
    """Offline stand-in used by tests and `--mock`. Its probabilities are FAKE (seeded noise skewed
    toward compliance); they only exercise the plumbing and say nothing about the transcript."""

    def __init__(self, kind_by_key: Mapping[str, str], roles_by_key: Mapping[str, Mapping[str, str]],
                 model: str = "fake/jev"):
        self.kind_by_key, self.roles_by_key, self.model = kind_by_key, roles_by_key, model
        self.usage = Usage()
        self.bodies: list[dict] = []   # every request body, for tests

    def decide(self, state: Any, questions: Mapping[str, Mapping[str, Any]], repeat_index: int = 0) -> dict:
        body = {"model": self.model, "state": state, "questions": dict(questions)}
        self.bodies.append(body)
        seed_text = json.dumps(state, ensure_ascii=False, sort_keys=True)
        answers = {}
        for key, q in questions.items():
            rng = random.Random(hashlib.sha256(f"{key}|{seed_text}|{repeat_index}".encode("utf-8")).digest())
            if q["type"] == "noul":
                x = rng.random()
                good = self.kind_by_key[key] in ("obligation", "gate")
                answers[key] = {"type": "noul", "noul": round(0.70 + 0.29 * x if good else 0.15 * x ** 3, 4)}
            else:
                roles = self.roles_by_key[key]
                p_na = 0.75 + 0.2 * rng.random()
                p_ok = (1 - p_na) * (0.6 + 0.35 * rng.random())
                probs = {roles["unknown"]: p_na, roles["followed"]: p_ok, roles["broken"]: 1 - p_na - p_ok}
                top = max(probs, key=probs.get)
                answers[key] = {"type": "choice", "choice": top, "probabilities": probs, "confidence": probs[top]}
        tokens = body_bytes(body) // 4
        resp = {"model": self.model, "answers": answers,
                "usage": {"input_tokens": tokens, "output_tokens": 0, "cost": tokens * PRICE_PER_INPUT_TOKEN}}
        validate_response(resp, questions)
        self.usage.add(resp, cached=False)
        return resp
