from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

logger = logging.getLogger("transcriptor.store")

IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_DATA_DIR = Path("/tmp/audio_audit_data") if IS_VERCEL else (BASE_DIR / ".local_data")
LOCAL_STORE_PATH = LOCAL_DATA_DIR / "store.json"
DEFAULT_AUDIO_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "audio-interviews").strip() or "audio-interviews"

JOBS_TABLE = "audio_audit_jobs"
RULE_OVERRIDES_TABLE = "audio_audit_rule_overrides"
EVAL_EDITS_TABLE = "audio_audit_evaluation_edits"
CALIBRATION_TABLE = "audio_audit_calibration"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_supabase_credentials() -> tuple[str, str]:
    url = (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or os.environ.get("VITE_SUPABASE_URL")
        or ""
    ).strip().rstrip("/")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or os.environ.get("VITE_SUPABASE_ANON_KEY")
        or ""
    ).strip()
    return url, key


class AuditStore:
    """Persistence layer backed by Supabase (PostgREST + Storage) with automatic local JSON fallback."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._bucket_checked: set[str] = set()
        self._memory_jobs: dict[str, dict[str, Any]] = {}
        self._memory_overrides: dict[str, dict[str, Any]] = {}
        self._memory_edits: list[dict[str, Any]] = []
        self._memory_calibrations: dict[str, dict[str, Any]] = {}
        self._loaded_local = False

    def is_supabase_configured(self) -> bool:
        url, key = get_supabase_credentials()
        return bool(url and key)

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        _, key = get_supabase_credentials()
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _rest_url(self, table: str) -> str:
        url, _ = get_supabase_credentials()
        return f"{url}/rest/v1/{table}"

    def _storage_url(self, path: str) -> str:
        url, _ = get_supabase_credentials()
        return f"{url}/storage/v1/{path.lstrip('/')}"

    # ------------------------------------------------------------------
    # Local fallback helpers (for offline / local dev without Supabase)
    # ------------------------------------------------------------------
    def _ensure_local_loaded(self) -> None:
        if self._loaded_local:
            return
        self._loaded_local = True
        if not LOCAL_STORE_PATH.exists():
            return
        try:
            raw = json.loads(LOCAL_STORE_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._memory_jobs = dict(raw.get("jobs") or {})
                self._memory_overrides = dict(raw.get("rule_overrides") or {})
                self._memory_edits = list(raw.get("evaluation_edits") or [])
                self._memory_calibrations = dict(raw.get("calibrations") or {})
        except Exception as exc:
            logger.warning("No se pudo leer almacenamiento local %s: %s", LOCAL_STORE_PATH, exc)

    def _flush_local(self) -> None:
        try:
            LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "jobs": self._memory_jobs,
                "rule_overrides": self._memory_overrides,
                "evaluation_edits": self._memory_edits[-5000:],
                "calibrations": self._memory_calibrations,
            }
            tmp = LOCAL_STORE_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(LOCAL_STORE_PATH)
        except Exception as exc:
            logger.warning("No se pudo guardar almacenamiento local: %s", exc)

    # ------------------------------------------------------------------
    # Supabase Storage (direct signed upload & signed playback/STT URLs)
    # ------------------------------------------------------------------
    def ensure_storage_bucket(self, bucket: str = DEFAULT_AUDIO_BUCKET) -> None:
        if not self.is_supabase_configured() or bucket in self._bucket_checked:
            return
        try:
            resp = self._session.get(
                self._storage_url(f"bucket/{quote(bucket, safe='')}"),
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                self._bucket_checked.add(bucket)
                return
            create_resp = self._session.post(
                self._storage_url("bucket"),
                headers=self._headers(),
                json={"id": bucket, "name": bucket, "public": False},
                timeout=10,
            )
            if create_resp.status_code in (200, 201, 409):
                self._bucket_checked.add(bucket)
            else:
                logger.warning(
                    "No se pudo crear automáticamente el bucket '%s' (%s): %s",
                    bucket,
                    create_resp.status_code,
                    create_resp.text[:250],
                )
        except Exception as exc:
            logger.warning("Error verificando bucket de Supabase Storage: %s", exc)

    def create_signed_upload_url(
        self, object_path: str, bucket: str = DEFAULT_AUDIO_BUCKET
    ) -> dict[str, str]:
        if not self.is_supabase_configured():
            raise RuntimeError(
                "Supabase no está configurado (SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY)."
            )
        self.ensure_storage_bucket(bucket)
        clean_path = "/".join(quote(part, safe="") for part in object_path.strip("/").split("/"))
        endpoint = self._storage_url(f"object/upload/sign/{quote(bucket, safe='')}/{clean_path}")
        resp = self._session.post(endpoint, headers=self._headers(), json={}, timeout=15)
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Supabase Storage rechazó crear URL de carga ({resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        rel_url = str(data.get("url") or "")
        base_url, _ = get_supabase_credentials()
        if rel_url.startswith("http"):
            signed_url = rel_url
        elif rel_url.startswith("/storage/v1"):
            signed_url = f"{base_url}{rel_url}"
        else:
            signed_url = f"{base_url}/storage/v1/{rel_url.lstrip('/')}"
        return {
            "signed_upload_url": signed_url,
            "token": str(data.get("token") or ""),
            "bucket": bucket,
            "storage_path": object_path.strip("/"),
        }

    def create_signed_read_url(
        self,
        object_path: str,
        *,
        expires_in: int = 14400,
        bucket: str = DEFAULT_AUDIO_BUCKET,
    ) -> str:
        if not self.is_supabase_configured():
            raise RuntimeError("Supabase no está configurado.")
        clean_path = "/".join(quote(part, safe="") for part in object_path.strip("/").split("/"))
        endpoint = self._storage_url(f"object/sign/{quote(bucket, safe='')}/{clean_path}")
        resp = self._session.post(
            endpoint,
            headers=self._headers(),
            json={"expiresIn": expires_in},
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"No se pudo obtener URL firmada de lectura en Supabase ({resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        rel_url = str(data.get("signedURL") or data.get("signedUrl") or "")
        base_url, _ = get_supabase_credentials()
        if rel_url.startswith("http"):
            return rel_url
        if rel_url.startswith("/storage/v1"):
            return f"{base_url}{rel_url}"
        return f"{base_url}/storage/v1/{rel_url.lstrip('/')}"

    # ------------------------------------------------------------------
    # Jobs CRUD (Supabase Postgres + in-memory/local JSON fallback)
    # ------------------------------------------------------------------
    @staticmethod
    def _job_to_db_row(job: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": job["job_id"],
            "filename": job.get("filename") or "entrevista",
            "source": job.get("source") or "audio",
            "stt_provider": job.get("stt_provider"),
            "external_job_id": job.get("external_job_id"),
            "storage_path": job.get("storage_path"),
            "has_audio": bool(job.get("has_audio", False)),
            "status": job.get("status") or "queued",
            "stage": job.get("stage") or "",
            "progress": float(job.get("progress") or 0.0),
            "duration_seconds": job.get("duration_seconds"),
            "elapsed_seconds": float(job.get("elapsed_seconds") or 0.0),
            "result": job.get("result"),
            "error": job.get("error"),
            "eval_status": job.get("eval_status") or "idle",
            "eval_elapsed_seconds": float(job.get("eval_elapsed_seconds") or 0.0),
            "evaluation": job.get("evaluation"),
            "eval_error": job.get("eval_error"),
            "updated_at": _now_iso(),
        }

    @staticmethod
    def _db_row_to_job(row: dict[str, Any], local_extra: dict[str, Any] | None = None) -> dict[str, Any]:
        created_ts = time.time()
        raw_created = row.get("created_at")
        if isinstance(raw_created, str):
            try:
                created_ts = datetime.fromisoformat(raw_created.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
        return {
            "job_id": row["id"],
            "filename": row.get("filename") or "entrevista",
            "source": row.get("source") or "audio",
            "stt_provider": row.get("stt_provider"),
            "external_job_id": row.get("external_job_id"),
            "storage_path": row.get("storage_path"),
            "has_audio": bool(row.get("has_audio", False)),
            "file_path": (local_extra or {}).get("file_path"),
            "upload_dir": (local_extra or {}).get("upload_dir"),
            "status": row.get("status") or "completed",
            "stage": row.get("stage") or "",
            "progress": float(row.get("progress") or 0.0),
            "created_at": (local_extra or {}).get("created_at", created_ts),
            "created_at_iso": raw_created or _now_iso(),
            "started_at": (local_extra or {}).get("started_at"),
            "elapsed_seconds": float(row.get("elapsed_seconds") or 0.0),
            "duration_seconds": row.get("duration_seconds"),
            "result": row.get("result"),
            "error": row.get("error"),
            "eval_status": row.get("eval_status") or "idle",
            "eval_started_at": (local_extra or {}).get("eval_started_at"),
            "eval_elapsed_seconds": float(row.get("eval_elapsed_seconds") or 0.0),
            "evaluation": row.get("evaluation"),
            "eval_error": row.get("eval_error"),
        }

    def upsert_job(self, job: dict[str, Any]) -> dict[str, Any]:
        job = dict(job)
        job.setdefault("created_at", time.time())
        job.setdefault("created_at_iso", _now_iso())

        with self._lock:
            self._ensure_local_loaded()
            self._memory_jobs[job["job_id"]] = job
            self._flush_local()

        if self.is_supabase_configured():
            try:
                row = self._job_to_db_row(job)
                resp = self._session.post(
                    self._rest_url(JOBS_TABLE),
                    headers=self._headers(prefer="resolution=merge-duplicates,return=representation"),
                    params={"on_conflict": "id"},
                    json=row,
                    timeout=12,
                )
                if resp.status_code not in (200, 201):
                    logger.warning(
                        "Supabase upsert_job devolvió HTTP %s (usando respaldo local): %s",
                        resp.status_code,
                        resp.text[:250],
                    )
            except Exception as exc:
                logger.warning("Error sincronizando trabajo con Supabase: %s", exc)
        return job

    def update_job(self, job_id: str, **updates: Any) -> dict[str, Any] | None:
        current: dict[str, Any] | None = None
        with self._lock:
            self._ensure_local_loaded()
            if job_id in self._memory_jobs:
                self._memory_jobs[job_id].update(updates)
                current = dict(self._memory_jobs[job_id])
                self._flush_local()

        if current is None and self.is_supabase_configured():
            fetched = self.get_job(job_id)
            if fetched is not None:
                fetched.update(updates)
                return self.upsert_job(fetched)
            return None

        if current is not None and self.is_supabase_configured():
            should_sync_remote = (
                IS_VERCEL
                or "status" in updates
                or "eval_status" in updates
                or "evaluation" in updates
                or "result" in updates
                or "external_job_id" in updates
            )
            if should_sync_remote:
                try:
                    row = self._job_to_db_row(current)
                    resp = self._session.patch(
                        self._rest_url(JOBS_TABLE),
                        headers=self._headers(prefer="return=minimal"),
                        params={"id": f"eq.{job_id}"},
                        json=row,
                        timeout=12,
                    )
                    if resp.status_code not in (200, 204):
                        logger.warning(
                            "Supabase update_job HTTP %s: %s", resp.status_code, resp.text[:200]
                        )
                except Exception as exc:
                    logger.warning("Error actualizando trabajo en Supabase: %s", exc)
        return current

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        local_copy: dict[str, Any] | None = None
        with self._lock:
            self._ensure_local_loaded()
            if job_id in self._memory_jobs:
                local_copy = dict(self._memory_jobs[job_id])

        if (
            local_copy
            and not IS_VERCEL
            and (
                local_copy.get("status") == "processing"
                or local_copy.get("eval_status") == "processing"
            )
            and local_copy.get("stt_provider") in (None, "local_whisperx")
        ):
            return local_copy

        if self.is_supabase_configured():
            try:
                resp = self._session.get(
                    self._rest_url(JOBS_TABLE),
                    headers=self._headers(),
                    params={"id": f"eq.{job_id}", "select": "*", "limit": "1"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    rows = resp.json()
                    if isinstance(rows, list) and rows:
                        merged = self._db_row_to_job(rows[0], local_extra=local_copy)
                        with self._lock:
                            self._memory_jobs[job_id] = merged
                        return merged
            except Exception as exc:
                logger.warning("Error consultando trabajo en Supabase: %s", exc)

        return local_copy

    def list_jobs(self, limit: int = 25) -> list[dict[str, Any]]:
        if self.is_supabase_configured():
            try:
                resp = self._session.get(
                    self._rest_url(JOBS_TABLE),
                    headers=self._headers(),
                    params={
                        "select": "id,filename,source,stt_provider,has_audio,status,stage,progress,duration_seconds,eval_status,evaluation,created_at,updated_at",
                        "order": "created_at.desc",
                        "limit": str(limit),
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    rows = resp.json()
                    if isinstance(rows, list):
                        return [self._db_row_to_job(r, self._memory_jobs.get(r["id"])) for r in rows]
            except Exception as exc:
                logger.warning("Error listando trabajos desde Supabase: %s", exc)

        with self._lock:
            self._ensure_local_loaded()
            items = list(self._memory_jobs.values())
        items.sort(key=lambda j: float(j.get("created_at") or 0.0), reverse=True)
        return items[:limit]

    # ------------------------------------------------------------------
    # Global Rule Overrides (Rewritten JEV criteria for future transcripts)
    # ------------------------------------------------------------------
    def get_rule_overrides(self) -> dict[str, dict[str, Any]]:
        if self.is_supabase_configured():
            try:
                resp = self._session.get(
                    self._rest_url(RULE_OVERRIDES_TABLE),
                    headers=self._headers(),
                    params={"select": "*"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    rows = resp.json()
                    if isinstance(rows, list):
                        out = {str(r["rule_id"]): dict(r) for r in rows if r.get("rule_id")}
                        with self._lock:
                            self._ensure_local_loaded()
                            self._memory_overrides = out
                        return out
            except Exception as exc:
                logger.warning("Error leyendo reglas editadas de Supabase: %s", exc)

        with self._lock:
            self._ensure_local_loaded()
            return {k: dict(v) for k, v in self._memory_overrides.items()}

    def upsert_rule_override(self, rule_id: str, data: dict[str, Any]) -> dict[str, Any]:
        record = {
            "rule_id": rule_id,
            "section": data.get("section") or rule_id.split("-")[0],
            "custom_text": data.get("custom_text"),
            "weight": data.get("weight"),
            "enabled": bool(data.get("enabled", True)),
            "auditor_guidance": data.get("auditor_guidance"),
            "questions_override": data.get("questions_override") or {},
            "updated_at": _now_iso(),
        }
        with self._lock:
            self._ensure_local_loaded()
            self._memory_overrides[rule_id] = record
            self._flush_local()

        if self.is_supabase_configured():
            try:
                resp = self._session.post(
                    self._rest_url(RULE_OVERRIDES_TABLE),
                    headers=self._headers(prefer="resolution=merge-duplicates,return=representation"),
                    params={"on_conflict": "rule_id"},
                    json=record,
                    timeout=12,
                )
                if resp.status_code not in (200, 201):
                    logger.warning(
                        "Supabase upsert_rule_override HTTP %s: %s",
                        resp.status_code,
                        resp.text[:250],
                    )
            except Exception as exc:
                logger.warning("Error guardando regla editada en Supabase: %s", exc)

        return record

    def delete_rule_override(self, rule_id: str) -> None:
        with self._lock:
            self._ensure_local_loaded()
            self._memory_overrides.pop(rule_id, None)
            self._flush_local()

        if self.is_supabase_configured():
            try:
                self._session.delete(
                    self._rest_url(RULE_OVERRIDES_TABLE),
                    headers=self._headers(),
                    params={"rule_id": f"eq.{rule_id}"},
                    timeout=10,
                )
            except Exception as exc:
                logger.warning("Error eliminando override de regla en Supabase: %s", exc)

    # ------------------------------------------------------------------
    # Audit Trail of Human Evaluation Edits (with raw JEV probs for calibration)
    # ------------------------------------------------------------------
    def log_evaluation_edit(self, entry: dict[str, Any]) -> dict[str, Any]:
        record = {
            "job_id": entry["job_id"],
            "rule_id": entry["rule_id"],
            "previous_outcome": entry.get("previous_outcome"),
            "override_status": entry.get("override_status") or "custom",
            "new_outcome": entry.get("new_outcome"),
            "auditor_comment": entry.get("auditor_comment"),
            "propagate_to_future": bool(entry.get("propagate_to_future", False)),
            "window_index": entry.get("window_index"),
            "question_key": entry.get("question_key"),
            "question_type": entry.get("question_type"),
            "calibration_group": entry.get("calibration_group"),
            "raw_probability": entry.get("raw_probability"),
            "raw_probabilities": entry.get("raw_probabilities"),
            "gold_label": entry.get("gold_label"),
            "model_version": entry.get("model_version"),
            "is_mock": bool(entry.get("is_mock", False)),
            "created_at": entry.get("created_at") or _now_iso(),
        }
        with self._lock:
            self._ensure_local_loaded()
            self._memory_edits.append(record)
            self._flush_local()

        if self.is_supabase_configured():
            try:
                resp = self._session.post(
                    self._rest_url(EVAL_EDITS_TABLE),
                    headers=self._headers(prefer="return=minimal"),
                    json=record,
                    timeout=10,
                )
                if resp.status_code not in (200, 201, 204):
                    logger.warning(
                        "Supabase log_evaluation_edit HTTP %s (verifica haber ejecutado schema.sql actualizado): %s",
                        resp.status_code,
                        resp.text[:250],
                    )
            except Exception as exc:
                logger.warning("Error registrando bitácora de edición en Supabase: %s", exc)
        return record

    def list_evaluation_edits(
        self,
        *,
        model_version: str | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        if self.is_supabase_configured():
            try:
                params: dict[str, str] = {
                    "select": "*",
                    "order": "created_at.asc",
                    "limit": str(limit),
                }
                if model_version:
                    params["model_version"] = f"eq.{model_version}"
                resp = self._session.get(
                    self._rest_url(EVAL_EDITS_TABLE),
                    headers=self._headers(),
                    params=params,
                    timeout=12,
                )
                if resp.status_code == 200:
                    rows = resp.json()
                    if isinstance(rows, list):
                        return rows
            except Exception as exc:
                logger.warning("Error leyendo ediciones para calibración desde Supabase: %s", exc)

        with self._lock:
            self._ensure_local_loaded()
            items = [dict(e) for e in self._memory_edits]
        if model_version:
            items = [e for e in items if e.get("model_version") == model_version]
        return items[-limit:]

    # ------------------------------------------------------------------
    # Fitted Calibration Persistence (Platt + Temperature per model version)
    # ------------------------------------------------------------------
    def get_calibration(self, model_version: str) -> dict[str, Any] | None:
        if self.is_supabase_configured():
            try:
                resp = self._session.get(
                    self._rest_url(CALIBRATION_TABLE),
                    headers=self._headers(),
                    params={"model_version": f"eq.{model_version}", "select": "*", "limit": "1"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    rows = resp.json()
                    if isinstance(rows, list) and rows:
                        row = dict(rows[0])
                        with self._lock:
                            self._ensure_local_loaded()
                            self._memory_calibrations[model_version] = row
                        return row
            except Exception as exc:
                logger.warning("Error leyendo calibración desde Supabase: %s", exc)

        with self._lock:
            self._ensure_local_loaded()
            item = self._memory_calibrations.get(model_version)
            return dict(item) if item else None

    def save_calibration(self, model_version: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "model_version": model_version,
            "min_labels": int(payload.get("min_labels") or 30),
            "total_labels": int(payload.get("total_labels") or 0),
            "is_calibrated": bool(payload.get("is_calibrated", False)),
            "calibrator": payload.get("calibrator") or {"noul_platt": {}, "choice_temperature": {}},
            "groups": payload.get("groups") or {},
            "updated_at": _now_iso(),
        }
        with self._lock:
            self._ensure_local_loaded()
            self._memory_calibrations[model_version] = record
            self._flush_local()

        if self.is_supabase_configured():
            try:
                resp = self._session.post(
                    self._rest_url(CALIBRATION_TABLE),
                    headers=self._headers(prefer="resolution=merge-duplicates,return=representation"),
                    params={"on_conflict": "model_version"},
                    json=record,
                    timeout=12,
                )
                if resp.status_code not in (200, 201):
                    logger.warning(
                        "Supabase save_calibration HTTP %s: %s",
                        resp.status_code,
                        resp.text[:250],
                    )
            except Exception as exc:
                logger.warning("Error guardando calibración en Supabase: %s", exc)
        return record


store = AuditStore()
