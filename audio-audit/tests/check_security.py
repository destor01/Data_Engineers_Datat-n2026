"""Security self-check for the access guard and input limits (stdlib only, no server needed).

    cd audio-audit && ..\\.venv\\Scripts\\python.exe tests\\check_security.py

Every request here is rejected (or read-only) before any handler writes, so it never touches .env or data.
"""
import asyncio
import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app.main as main  # noqa: E402


def call(method, path, headers=None, body=None):
    hdrs = {"host": "127.0.0.1:8000", **(headers or {})}
    raw = json.dumps(body).encode() if body is not None else b""
    if body is not None:
        hdrs["content-type"] = "application/json"
    scope = {"type": "http", "method": method, "path": path, "raw_path": path.encode(), "query_string": b"",
             "headers": [(k.lower().encode(), v.encode()) for k, v in hdrs.items()], "scheme": "http",
             "server": ("127.0.0.1", 8000), "client": ("127.0.0.1", 5000), "root_path": "", "http_version": "1.1"}
    inbox = [{"type": "http.request", "body": raw, "more_body": False}]
    sent = []

    async def receive():
        return inbox.pop(0) if inbox else {"type": "http.disconnect"}

    async def send(msg):
        sent.append(msg)

    asyncio.run(main.app(scope, receive, send))
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def basic(pw):
    return {"authorization": "Basic " + base64.b64encode(f"auditor:{pw}".encode()).decode()}


os.environ.pop("APP_PASSWORD", None)
assert call("GET", "/api/rules") == 200, "localhost works without password"
assert call("GET", "/api/rules", {"host": "attacker-rebind.example"}) == 403, "DNS rebinding blocked"
assert call("POST", "/api/transcript/example", {"origin": "https://evil.example"}) == 403, "CSRF blocked"
assert call("POST", "/api/config/keys", body={"hf_token": "hf_abcdefghij\nJEV_MODEL=x"}) == 400, ".env injection blocked"
assert call("PUT", "/api/rules/A1-01", body={"auditor_guidance": "x" * 3000}) == 422, "oversized rule rejected"

os.environ["APP_PASSWORD"] = "correct horse battery"
assert call("GET", "/api/jobs") == 401, "password required"
assert call("GET", "/api/jobs", basic("wrong")) == 401, "wrong password rejected"
assert call("GET", "/api/rules", basic("correct horse battery")) == 200, "right password accepted"
assert call("POST", "/api/transcript/example", {**basic("correct horse battery"), "origin": "https://evil.example"}) == 403, \
    "CSRF blocked even with cached Basic credentials"

os.environ.pop("APP_PASSWORD")
main.IS_VERCEL = True
assert call("GET", "/api/jobs", {"host": "my-app.vercel.app"}) == 503, "Vercel without APP_PASSWORD fails closed"
os.environ["APP_PASSWORD"] = "pw-for-vercel"
assert call("POST", "/api/config/keys", {**basic("pw-for-vercel"), "host": "my-app.vercel.app"},
            body={"supabase_url": "https://attacker.example"}) == 403, "no key swapping on Vercel"
print("security checks passed")
