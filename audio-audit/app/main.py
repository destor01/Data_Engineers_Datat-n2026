from __future__ import annotations

import logging
import os
import re
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.cloud_stt import (
    poll_assemblyai_transcription,
    run_deepgram_transcription,
    submit_assemblyai_transcription,
    upload_local_file_to_assemblyai,
)
from app.jev_auditor import (
    DEFAULT_MODEL as JEV_DEFAULT_MODEL,
    EXAMPLE_TRANSCRIPT_PATH,
    INTERVIEWER,
    apply_instruction_override,
    evaluate_transcript_with_jev,
    is_jev_available,
    load_example_transcript,
    normalize_speaker,
    parse_uploaded_transcript,
    serialize_rules_catalog,
    suggest_speaker_roles,
)
from app.supabase_store import DEFAULT_AUDIO_BUCKET, IS_VERCEL, store
from app.transcriber import (
    format_transcript_txt,
    get_hardware_status,
    is_local_whisper_available,
    probe_audio_duration,
    run_local_transcription,
)

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent
DIST_DIR = BASE_DIR / "dist"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = Path("/tmp/audio_audit_uploads") if IS_VERCEL else (BASE_DIR / "uploads")
ROOT_ENV_PATH = REPO_ROOT / ".env"
LOCAL_ENV_PATH = BASE_DIR / ".env"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("transcriptor")

ALLOWED_MODELS = {"medium", "large-v3-turbo", "large-v3"}
ALLOWED_PROVIDERS = {"auto", "local_whisperx", "assemblyai", "deepgram"}
MAX_LOCAL_UPLOAD_FOLDERS = 10

app = FastAPI(title="Auditoría de Entrevistas ENCOVI — TypeScript + Python + Supabase")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

if (DIST_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Local GPU transcription pool (only used when running local WhisperX on desktop/server)
transcription_executor = ThreadPoolExecutor(max_workers=1)
_runtime_env_overrides: dict[str, str] = {}


def _reload_env() -> None:
    """Reload .env from repo root and audio-audit locally without clobbering runtime overrides."""
    if not IS_VERCEL:
        if ROOT_ENV_PATH.exists():
            load_dotenv(ROOT_ENV_PATH, override=True)
        if LOCAL_ENV_PATH.exists():
            load_dotenv(LOCAL_ENV_PATH, override=True)
    for k, v in _runtime_env_overrides.items():
        os.environ[k] = v


_reload_env()


def _target_env_path() -> Path:
    return ROOT_ENV_PATH if ROOT_ENV_PATH.exists() else LOCAL_ENV_PATH


def _save_env_key(key: str, value: str) -> bool:
    """Persist env var to .env when writable (local dev) and always set in process memory."""
    value = value.strip()
    _runtime_env_overrides[key] = value
    os.environ[key] = value
    if IS_VERCEL:
        return False
    try:
        env_path = _target_env_path()
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        replaced = False
        new_lines: list[str] = []
        for line in lines:
            if line.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                replaced = True
            else:
                new_lines.append(line)
        if not replaced:
            new_lines.append(f"{key}={value}")
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True
    except OSError as exc:
        logger.warning("No se pudo escribir %s en .env (sistema de solo lectura): %s", key, exc)
        return False


def _get_hf_token() -> str:
    _reload_env()
    return (os.environ.get("HF_TOKEN") or os.environ.get("hf") or "").strip()


def _get_openrouter_key() -> str:
    _reload_env()
    return (os.environ.get("OPENROUTER_API_KEY") or "").strip()


def _get_assemblyai_key() -> str:
    _reload_env()
    return (os.environ.get("ASSEMBLYAI_API_KEY") or "").strip()


def _get_deepgram_key() -> str:
    _reload_env()
    return (os.environ.get("DEEPGRAM_API_KEY") or "").strip()


# =====================================================================
# Request Schemas
# =====================================================================

class TokenPayload(BaseModel):
    token: str


class ApiKeysPayload(BaseModel):
    hf_token: str | None = None
    openrouter_key: str | None = None
    assemblyai_key: str | None = None
    deepgram_key: str | None = None
    supabase_url: str | None = None
    supabase_key: str | None = None


class SignedUploadRequest(BaseModel):
    filename: str
    content_type: str = "audio/mpeg"


class CloudTranscribeRequest(BaseModel):
    job_id: str | None = None
    filename: str
    storage_path: str
    content_type: str = "audio/mpeg"
    provider: str = "assemblyai"
    diarize: bool = True
    min_speakers: int | None = None
    max_speakers: int | None = None


class EvaluatePayload(BaseModel):
    speaker_map: dict[str, str] = Field(default_factory=dict)
    first_contact: bool = True
    mock: bool = False


class QuestionOverrideInput(BaseModel):
    instructions: str | None = None
    criteria: dict[str, str] = Field(default_factory=dict)


class RuleDefinitionUpdatePayload(BaseModel):
    custom_text: str | None = None
    weight: int | None = Field(default=None, ge=1, le=3)
    enabled: bool = True
    auditor_guidance: str | None = None
    questions_override: dict[str, QuestionOverrideInput] = Field(default_factory=dict)


class EvaluationRuleEditPayload(BaseModel):
    override_status: str = "keep"  # followed | broken | unknown | custom | keep | reset
    custom_probs: dict[str, float] | None = None
    auditor_comment: str | None = None
    update_future_rule: bool = False
    rule_override: RuleDefinitionUpdatePayload | None = None


# =====================================================================
# Helpers
# =====================================================================

def _sanitize_filename(name: str) -> str:
    base = Path(name or "audio.wav").name
    cleaned = re.sub(r"[^\w.\- ()áéíóúÁÉÍÓÚñÑ]", "_", base).strip()
    return cleaned or "audio.wav"


def _cleanup_local_upload_dirs() -> None:
    if IS_VERCEL or not UPLOADS_DIR.exists():
        return
    try:
        subdirs = [d for d in UPLOADS_DIR.iterdir() if d.is_dir()]
        if len(subdirs) <= MAX_LOCAL_UPLOAD_FOLDERS:
            return
        subdirs.sort(key=lambda p: p.stat().st_mtime)
        for folder in subdirs[:-MAX_LOCAL_UPLOAD_FOLDERS]:
            shutil.rmtree(folder, ignore_errors=True)
    except Exception:
        pass


def _resolve_stt_provider(requested: str) -> str:
    req = (requested or "auto").strip().lower()
    if req not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Proveedor STT no válido: {requested}")
    if req != "auto":
        return req
    if not IS_VERCEL and is_local_whisper_available():
        return "local_whisperx"
    if _get_assemblyai_key():
        return "assemblyai"
    if _get_deepgram_key():
        return "deepgram"
    return "assemblyai" if IS_VERCEL else "local_whisperx"


def _serialize_job(job: dict[str, Any]) -> dict[str, Any]:
    eval_elapsed = float(job.get("eval_elapsed_seconds") or 0.0)
    if job.get("eval_status") == "processing" and job.get("eval_started_at"):
        eval_elapsed = round(time.time() - float(job["eval_started_at"]), 1)

    elapsed = float(job.get("elapsed_seconds") or 0.0)
    if job.get("status") == "processing" and job.get("started_at"):
        elapsed = round(time.time() - float(job["started_at"]), 1)

    has_audio = bool(job.get("has_audio", False))
    job_id = job["job_id"]
    return {
        "job_id": job_id,
        "filename": job.get("filename") or "entrevista",
        "source": job.get("source", "audio"),
        "stt_provider": job.get("stt_provider"),
        "has_audio": has_audio,
        "audio_url": f"/api/jobs/{job_id}/audio" if has_audio else None,
        "status": job.get("status", "completed"),
        "stage": job.get("stage", ""),
        "progress": job.get("progress", 0),
        "duration_seconds": job.get("duration_seconds"),
        "elapsed_seconds": elapsed,
        "created_at_iso": job.get("created_at_iso"),
        "result": job.get("result"),
        "error": job.get("error"),
        "eval_status": job.get("eval_status", "idle"),
        "eval_elapsed_seconds": eval_elapsed,
        "evaluation": job.get("evaluation"),
        "eval_error": job.get("eval_error"),
    }


def _serialize_job_summary(job: dict[str, Any]) -> dict[str, Any]:
    ev = job.get("evaluation") or {}
    overall = ev.get("overall") if isinstance(ev, dict) else None
    return {
        "job_id": job["job_id"],
        "filename": job.get("filename") or "entrevista",
        "source": job.get("source", "audio"),
        "stt_provider": job.get("stt_provider"),
        "has_audio": bool(job.get("has_audio", False)),
        "status": job.get("status", "completed"),
        "duration_seconds": job.get("duration_seconds"),
        "eval_status": job.get("eval_status", "idle"),
        "created_at_iso": job.get("created_at_iso"),
        "compliance_rate_weighted": (overall or {}).get("compliance_rate_weighted"),
        "verdict": (overall or {}).get("verdict"),
        "manual_edit_count": (overall or {}).get("manual_edit_count", 0),
    }


def _process_local_whisper_job(
    job_id: str,
    file_path: Path,
    model_name: str,
    denoise: bool,
    diarize: bool,
    min_speakers: int | None,
    max_speakers: int | None,
) -> None:
    started = time.time()
    store.update_job(
        job_id,
        status="processing",
        started_at=started,
        stage="Analizando archivo de audio…",
        progress=5,
    )

    try:
        duration = probe_audio_duration(file_path)
        store.update_job(job_id, duration_seconds=duration)

        def on_progress(stage: str, pct: float) -> None:
            store.update_job(
                job_id,
                stage=stage,
                progress=pct,
                elapsed_seconds=round(time.time() - started, 1),
            )

        result = run_local_transcription(
            file_path,
            model_name=model_name,
            denoise=denoise,
            diarize=diarize,
            hf_token=_get_hf_token(),
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            progress_cb=on_progress,
        )

        speakers = result.get("speakers") or []
        if not speakers and result.get("turns"):
            speakers = list(dict.fromkeys(t["speaker"] for t in result["turns"]))
            result["speakers"] = speakers
        result["suggested_roles"] = suggest_speaker_roles(speakers)

        elapsed = round(time.time() - started, 1)
        store.update_job(
            job_id,
            status="completed",
            stage="¡Transcripción completada!",
            progress=100,
            elapsed_seconds=elapsed,
            result=result,
        )
    except Exception as exc:
        logger.exception("Error procesando trabajo local %s", job_id)
        elapsed = round(time.time() - started, 1)
        store.update_job(
            job_id,
            status="error",
            stage="Error",
            elapsed_seconds=elapsed,
            error=str(exc),
        )
    finally:
        _cleanup_local_upload_dirs()


def _refresh_cloud_job_if_needed(job: dict[str, Any]) -> dict[str, Any]:
    """Serverless-safe poll: if an AssemblyAI job is in progress, check AssemblyAI and update Supabase."""
    if (
        job.get("status") != "processing"
        or job.get("stt_provider") != "assemblyai"
        or not job.get("external_job_id")
    ):
        return job

    api_key = _get_assemblyai_key()
    if not api_key:
        return job

    try:
        diarize_flag = bool((job.get("result") or {}).get("diarize_requested", True))
        polled = poll_assemblyai_transcription(
            str(job["external_job_id"]),
            api_key,
            diarize=diarize_flag,
        )
        if polled["status"] == "processing":
            updated = store.update_job(
                job["job_id"],
                stage=polled.get("stage", "Procesando en AssemblyAI…"),
                progress=polled.get("progress", 70),
            )
            return updated or job

        if polled["status"] == "error":
            updated = store.update_job(
                job["job_id"],
                status="error",
                stage="Error",
                error=polled.get("error", "Error en AssemblyAI"),
            )
            return updated or job

        turns = polled.get("turns") or []
        speakers = polled.get("speakers") or []
        if not speakers and turns:
            speakers = list(dict.fromkeys(t["speaker"] for t in turns))
        result_payload = {
            "turns": turns,
            "speakers": speakers,
            "suggested_roles": suggest_speaker_roles(speakers),
            "warning": polled.get("warning"),
            "note": polled.get("note"),
        }
        created_at = float(job.get("created_at") or time.time())
        updated = store.update_job(
            job["job_id"],
            status="completed",
            stage="¡Transcripción completada!",
            progress=100,
            duration_seconds=polled.get("duration_seconds") or job.get("duration_seconds"),
            elapsed_seconds=round(max(0.5, time.time() - created_at), 1),
            result=result_payload,
            error=None,
        )
        return updated or job
    except Exception as exc:
        logger.warning("Error consultando avance en AssemblyAI para %s: %s", job["job_id"], exc)
        return job


# =====================================================================
# Routes: Status & Configuration
# =====================================================================

@app.get("/api/status")
def system_status() -> dict[str, Any]:
    hw = get_hardware_status()
    overrides = store.get_rule_overrides()
    catalog = serialize_rules_catalog(overrides)
    customized_count = sum(1 for r in catalog if r.get("is_customized"))

    assemblyai_ok = bool(_get_assemblyai_key())
    deepgram_ok = bool(_get_deepgram_key())
    local_ok = bool(hw.get("local_whisper_available")) and not IS_VERCEL

    if local_ok:
        recommended_provider = "local_whisperx"
    elif assemblyai_ok:
        recommended_provider = "assemblyai"
    elif deepgram_ok:
        recommended_provider = "deepgram"
    else:
        recommended_provider = "assemblyai"

    return {
        **hw,
        "is_vercel": IS_VERCEL,
        "supabase_configured": store.is_supabase_configured(),
        "hf_token_configured": bool(_get_hf_token()),
        "openrouter_configured": bool(_get_openrouter_key()),
        "assemblyai_configured": assemblyai_ok,
        "deepgram_configured": deepgram_ok,
        "recommended_stt_provider": recommended_provider,
        "jev_available": is_jev_available(),
        "jev_model": (os.environ.get("JEV_MODEL") or JEV_DEFAULT_MODEL).strip(),
        "example_available": EXAMPLE_TRANSCRIPT_PATH.exists(),
        "default_model": os.environ.get("WHISPER_MODEL", "large-v3-turbo"),
        "customized_rules_count": customized_count,
    }


@app.post("/api/config/keys")
def save_api_keys(payload: ApiKeysPayload) -> dict[str, Any]:
    saved_to_disk = True
    updated: list[str] = []

    mapping = [
        ("HF_TOKEN", payload.hf_token),
        ("OPENROUTER_API_KEY", payload.openrouter_key),
        ("ASSEMBLYAI_API_KEY", payload.assemblyai_key),
        ("DEEPGRAM_API_KEY", payload.deepgram_key),
        ("SUPABASE_URL", payload.supabase_url),
        ("SUPABASE_SERVICE_ROLE_KEY", payload.supabase_key),
    ]
    for env_name, raw_val in mapping:
        if raw_val is not None and raw_val.strip():
            val = raw_val.strip()
            if len(val) < 8:
                raise HTTPException(
                    status_code=400,
                    detail=f"El valor para {env_name} parece incompleto.",
                )
            wrote = _save_env_key(env_name, val)
            saved_to_disk = saved_to_disk and wrote
            updated.append(env_name)

    if not updated:
        raise HTTPException(status_code=400, detail="No se recibió ninguna clave para guardar.")

    return {
        "ok": True,
        "updated": updated,
        "persisted_to_env_file": saved_to_disk,
        "note": (
            None
            if saved_to_disk
            else "Clave aplicada en memoria para esta instancia. En Vercel, agrégala en Settings → Environment Variables para que sea permanente."
        ),
    }


@app.post("/api/config/hf-token")
def save_hf_token(payload: TokenPayload) -> dict[str, Any]:
    token = payload.token.strip()
    if not token or len(token) < 10:
        raise HTTPException(
            status_code=400,
            detail="El token parece incompleto. Copia el token completo desde Hugging Face.",
        )
    _save_env_key("HF_TOKEN", token)
    return {"ok": True}


@app.post("/api/config/openrouter-key")
def save_openrouter_key(payload: TokenPayload) -> dict[str, Any]:
    token = payload.token.strip()
    if not token or len(token) < 10:
        raise HTTPException(
            status_code=400,
            detail="La clave parece incompleta. Copia tu clave completa de OpenRouter (sk-or-...).",
        )
    _save_env_key("OPENROUTER_API_KEY", token)
    return {"ok": True}


# =====================================================================
# Routes: Supabase Direct Upload + Cloud & Local Transcription
# =====================================================================

@app.post("/api/storage/upload-url")
def create_direct_upload_url(payload: SignedUploadRequest) -> dict[str, Any]:
    if not store.is_supabase_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "Supabase Storage no está configurado (SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY). "
                "Configúralo para subir grabaciones largas sin pasar por el límite de 4.5 MB de Vercel."
            ),
        )
    job_id = uuid.uuid4().hex[:12]
    safe_name = _sanitize_filename(payload.filename)
    object_path = f"jobs/{job_id}/{safe_name}"
    try:
        signed = store.create_signed_upload_url(object_path, bucket=DEFAULT_AUDIO_BUCKET)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "job_id": job_id,
        "filename": safe_name,
        **signed,
    }


@app.post("/api/transcribe/cloud")
def start_cloud_transcription_from_storage(payload: CloudTranscribeRequest) -> dict[str, Any]:
    """Start Spanish transcription + speaker diarization from an audio file already uploaded to Supabase Storage."""
    if not store.is_supabase_configured():
        raise HTTPException(
            status_code=400,
            detail="Supabase no está configurado para leer el archivo subido.",
        )

    provider = _resolve_stt_provider(payload.provider)
    if provider == "local_whisperx":
        provider = "assemblyai" if _get_assemblyai_key() else "deepgram"

    if payload.min_speakers is not None and payload.max_speakers is not None:
        if payload.min_speakers > payload.max_speakers:
            raise HTTPException(
                status_code=400,
                detail="El mínimo de hablantes no puede ser mayor que el máximo.",
            )

    try:
        signed_audio_url = store.create_signed_read_url(
            payload.storage_path,
            expires_in=14400,
            bucket=DEFAULT_AUDIO_BUCKET,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    job_id = (payload.job_id or "").strip() or uuid.uuid4().hex[:12]
    safe_name = _sanitize_filename(payload.filename)
    now_ts = time.time()

    if provider == "assemblyai":
        api_key = _get_assemblyai_key()
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Falta ASSEMBLYAI_API_KEY. Configúrala en Variables de Entorno o en el panel de claves.",
            )
        try:
            transcript_id = submit_assemblyai_transcription(
                audio_url=signed_audio_url,
                api_key=api_key,
                diarize=payload.diarize,
                min_speakers=payload.min_speakers,
                max_speakers=payload.max_speakers,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        job = store.upsert_job(
            {
                "job_id": job_id,
                "filename": safe_name,
                "source": "cloud_audio",
                "stt_provider": "assemblyai",
                "external_job_id": transcript_id,
                "storage_path": payload.storage_path,
                "has_audio": True,
                "status": "processing",
                "stage": "Transcribiendo e identificando hablantes en AssemblyAI…",
                "progress": 25,
                "created_at": now_ts,
                "started_at": now_ts,
                "elapsed_seconds": 0.0,
                "duration_seconds": None,
                "result": {"diarize_requested": payload.diarize},
                "error": None,
                "eval_status": "idle",
                "eval_elapsed_seconds": 0.0,
                "evaluation": None,
                "eval_error": None,
            }
        )
        return _serialize_job(job)

    if provider == "deepgram":
        api_key = _get_deepgram_key()
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Falta DEEPGRAM_API_KEY. Configúrala en Variables de Entorno o en el panel de claves.",
            )
        started = time.time()
        try:
            dg = run_deepgram_transcription(
                api_key=api_key,
                audio_url=signed_audio_url,
                content_type=payload.content_type,
                diarize=payload.diarize,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        turns = dg["turns"]
        speakers = dg["speakers"]
        job = store.upsert_job(
            {
                "job_id": job_id,
                "filename": safe_name,
                "source": "cloud_audio",
                "stt_provider": "deepgram",
                "external_job_id": None,
                "storage_path": payload.storage_path,
                "has_audio": True,
                "status": "completed",
                "stage": "¡Transcripción completada!",
                "progress": 100,
                "created_at": now_ts,
                "started_at": started,
                "elapsed_seconds": round(time.time() - started, 1),
                "duration_seconds": dg.get("duration_seconds"),
                "result": {
                    "turns": turns,
                    "speakers": speakers,
                    "suggested_roles": suggest_speaker_roles(speakers),
                    "warning": dg.get("warning"),
                    "note": dg.get("note"),
                },
                "error": None,
                "eval_status": "idle",
                "eval_elapsed_seconds": 0.0,
                "evaluation": None,
                "eval_error": None,
            }
        )
        return _serialize_job(job)

    raise HTTPException(status_code=400, detail=f"Proveedor en la nube no soportado: {provider}")


@app.post("/api/transcribe")
async def create_transcription_job(
    file: UploadFile = File(...),
    provider: str = Form("auto"),
    model: str = Form("large-v3-turbo"),
    denoise: bool = Form(True),
    diarize: bool = Form(True),
    min_speakers: int | None = Form(None),
    max_speakers: int | None = Form(None),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Debes seleccionar un archivo de audio.")

    resolved_provider = _resolve_stt_provider(provider)

    if min_speakers is not None and max_speakers is not None and min_speakers > max_speakers:
        raise HTTPException(
            status_code=400,
            detail="El mínimo de hablantes no puede ser mayor que el máximo.",
        )

    if resolved_provider == "local_whisperx":
        if IS_VERCEL or not is_local_whisper_available():
            raise HTTPException(
                status_code=400,
                detail=(
                    "WhisperX local requiere GPU/PyTorch en un servidor local. "
                    "En Vercel selecciona AssemblyAI o Deepgram (no requieren GPU ni HF_TOKEN)."
                ),
            )
        if model not in ALLOWED_MODELS:
            raise HTTPException(status_code=400, detail=f"Modelo Whisper no permitido: {model}")
        if diarize and not _get_hf_token():
            raise HTTPException(
                status_code=400,
                detail="Para usar Pyannote local configura HF_TOKEN, o cambia el motor a AssemblyAI / Deepgram (sin HF_TOKEN).",
            )
    elif resolved_provider == "assemblyai" and not _get_assemblyai_key():
        raise HTTPException(
            status_code=400,
            detail="Configura ASSEMBLYAI_API_KEY antes de transcribir con AssemblyAI.",
        )
    elif resolved_provider == "deepgram" and not _get_deepgram_key():
        raise HTTPException(
            status_code=400,
            detail="Configura DEEPGRAM_API_KEY antes de transcribir con Deepgram.",
        )

    job_id = uuid.uuid4().hex[:12]
    safe_name = _sanitize_filename(file.filename)
    job_dir = UPLOADS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    dest_path = job_dir / safe_name

    total_bytes = 0
    try:
        with dest_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                total_bytes += len(chunk)
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Error al guardar el archivo subido: {exc}") from exc
    finally:
        await file.close()

    if total_bytes == 0:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="El archivo de audio está vacío.")

    now_ts = time.time()

    if resolved_provider == "local_whisperx":
        store.upsert_job(
            {
                "job_id": job_id,
                "filename": safe_name,
                "source": "audio",
                "stt_provider": "local_whisperx",
                "has_audio": True,
                "file_path": str(dest_path),
                "upload_dir": str(job_dir),
                "status": "queued",
                "stage": "En cola para procesar en equipo local…",
                "progress": 3,
                "created_at": now_ts,
                "started_at": None,
                "elapsed_seconds": 0.0,
                "duration_seconds": None,
                "result": None,
                "error": None,
                "eval_status": "idle",
                "eval_elapsed_seconds": 0.0,
                "evaluation": None,
                "eval_error": None,
            }
        )
        transcription_executor.submit(
            _process_local_whisper_job,
            job_id,
            dest_path,
            model,
            denoise,
            diarize,
            min_speakers,
            max_speakers,
        )
        return {"job_id": job_id, "status": "queued"}

    if resolved_provider == "assemblyai":
        try:
            upload_url = upload_local_file_to_assemblyai(dest_path, _get_assemblyai_key())
            transcript_id = submit_assemblyai_transcription(
                audio_url=upload_url,
                api_key=_get_assemblyai_key(),
                diarize=diarize,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )
        except Exception as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        store.upsert_job(
            {
                "job_id": job_id,
                "filename": safe_name,
                "source": "cloud_audio",
                "stt_provider": "assemblyai",
                "external_job_id": transcript_id,
                "has_audio": not IS_VERCEL,
                "file_path": str(dest_path) if not IS_VERCEL else None,
                "upload_dir": str(job_dir) if not IS_VERCEL else None,
                "status": "processing",
                "stage": "Transcribiendo e identificando hablantes en AssemblyAI…",
                "progress": 25,
                "created_at": now_ts,
                "started_at": now_ts,
                "elapsed_seconds": 0.0,
                "duration_seconds": probe_audio_duration(dest_path),
                "result": {"diarize_requested": diarize},
                "error": None,
                "eval_status": "idle",
                "eval_elapsed_seconds": 0.0,
                "evaluation": None,
                "eval_error": None,
            }
        )
        if IS_VERCEL:
            shutil.rmtree(job_dir, ignore_errors=True)
        return {"job_id": job_id, "status": "processing"}

    if resolved_provider == "deepgram":
        started = time.time()
        try:
            dg = run_deepgram_transcription(
                api_key=_get_deepgram_key(),
                file_path=dest_path,
                content_type=file.content_type or "audio/mpeg",
                diarize=diarize,
            )
        except Exception as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        turns = dg["turns"]
        speakers = dg["speakers"]
        store.upsert_job(
            {
                "job_id": job_id,
                "filename": safe_name,
                "source": "cloud_audio",
                "stt_provider": "deepgram",
                "has_audio": not IS_VERCEL,
                "file_path": str(dest_path) if not IS_VERCEL else None,
                "upload_dir": str(job_dir) if not IS_VERCEL else None,
                "status": "completed",
                "stage": "¡Transcripción completada!",
                "progress": 100,
                "created_at": now_ts,
                "started_at": started,
                "elapsed_seconds": round(time.time() - started, 1),
                "duration_seconds": dg.get("duration_seconds") or probe_audio_duration(dest_path),
                "result": {
                    "turns": turns,
                    "speakers": speakers,
                    "suggested_roles": suggest_speaker_roles(speakers),
                    "warning": dg.get("warning"),
                    "note": dg.get("note"),
                },
                "error": None,
                "eval_status": "idle",
                "eval_elapsed_seconds": 0.0,
                "evaluation": None,
                "eval_error": None,
            }
        )
        if IS_VERCEL:
            shutil.rmtree(job_dir, ignore_errors=True)
        return {"job_id": job_id, "status": "completed"}

    raise HTTPException(status_code=400, detail=f"Proveedor no soportado: {resolved_provider}")


def _register_transcript_job(filename: str, parsed: dict[str, Any], source: str) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    safe_name = _sanitize_filename(filename)
    job = store.upsert_job(
        {
            "job_id": job_id,
            "filename": safe_name,
            "source": source,
            "stt_provider": None,
            "has_audio": False,
            "file_path": None,
            "upload_dir": None,
            "status": "completed",
            "stage": "Transcripción cargada",
            "progress": 100,
            "created_at": time.time(),
            "started_at": None,
            "elapsed_seconds": 0.0,
            "duration_seconds": parsed.get("duration_seconds"),
            "result": {
                "turns": parsed["turns"],
                "speakers": parsed["speakers"],
                "suggested_roles": parsed["suggested_roles"],
                "note": parsed.get("note"),
                "warning": parsed.get("warning"),
            },
            "error": None,
            "eval_status": "idle",
            "eval_started_at": None,
            "eval_elapsed_seconds": 0.0,
            "evaluation": None,
            "eval_error": None,
        }
    )
    return _serialize_job(job)


@app.post("/api/transcript/upload")
async def upload_existing_transcript(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Debes seleccionar un archivo .json o .txt.")

    content = await file.read()
    await file.close()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo de transcripción está vacío.")

    try:
        parsed = parse_uploaded_transcript(content, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _register_transcript_job(file.filename, parsed, source="transcript_upload")


@app.post("/api/transcript/example")
def load_example_encovi_transcript() -> dict[str, Any]:
    try:
        parsed = load_example_transcript()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _register_transcript_job(parsed["filename"], parsed, source="example")


# =====================================================================
# Routes: Jobs, History, Audio & Downloads
# =====================================================================

@app.get("/api/jobs")
def list_recent_jobs(limit: int = 20) -> dict[str, Any]:
    items = store.list_jobs(limit=max(1, min(limit, 50)))
    return {"jobs": [_serialize_job_summary(j) for j in items]}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> dict[str, Any]:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    job = _refresh_cloud_job_if_needed(job)
    return _serialize_job(job)


@app.get("/api/jobs/{job_id}/audio")
def get_job_audio(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")

    file_path = Path(job["file_path"]) if job.get("file_path") else None
    if file_path and file_path.exists():
        return FileResponse(path=file_path, filename=file_path.name)

    storage_path = job.get("storage_path")
    if storage_path and store.is_supabase_configured():
        try:
            signed_url = store.create_signed_read_url(
                str(storage_path),
                expires_in=14400,
                bucket=DEFAULT_AUDIO_BUCKET,
            )
            return RedirectResponse(url=signed_url, status_code=307)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    raise HTTPException(status_code=404, detail="Archivo de audio no disponible.")


@app.get("/api/jobs/{job_id}/download")
def download_transcript_txt(job_id: str) -> PlainTextResponse:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    if job.get("status") != "completed" or not job.get("result"):
        raise HTTPException(status_code=400, detail="La transcripción aún no está lista.")

    filename = job["filename"]
    duration = job.get("duration_seconds")
    result = job["result"]

    txt_content = format_transcript_txt(
        filename=filename,
        duration_seconds=duration,
        turns=result.get("turns") or [],
        speakers=result.get("speakers") or [],
    )

    stem = Path(filename).stem
    safe_download_name = re.sub(r"[^\w\-]", "_", stem) or "transcripcion"
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_download_name}_transcripcion.txt"'
    }
    return PlainTextResponse(
        content=txt_content,
        headers=headers,
        media_type="text/plain; charset=utf-8",
    )


# =====================================================================
# Routes: JEV Evaluation + Editable Evaluations & Global Rules
# =====================================================================

@app.post("/api/jobs/{job_id}/evaluate")
def run_jev_evaluation_endpoint(job_id: str, payload: EvaluatePayload) -> dict[str, Any]:
    """Run JEV evaluation synchronously in-request so Vercel serverless never freezes background threads."""
    if not is_jev_available():
        raise HTTPException(
            status_code=500,
            detail="El motor encovi_jev no está disponible en el repositorio.",
        )

    if not payload.mock and not _get_openrouter_key():
        raise HTTPException(
            status_code=400,
            detail=(
                "No se encontró OPENROUTER_API_KEY. Agrégala en tus variables de entorno "
                "o activa el «Modo prueba sin conexión»."
            ),
        )

    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    if job.get("status") != "completed" or not job.get("result"):
        raise HTTPException(status_code=400, detail="La transcripción todavía no está lista.")

    turns = list((job.get("result") or {}).get("turns") or [])
    if not turns:
        raise HTTPException(status_code=400, detail="No hay intervenciones para evaluar.")

    speaker_map = dict(payload.speaker_map or {})
    if not any(normalize_speaker(str(t.get("speaker") or ""), speaker_map) == INTERVIEWER for t in turns):
        raise HTTPException(
            status_code=400,
            detail="Debes asignar al menos un hablante como ENCUESTADOR antes de evaluar.",
        )

    started = time.time()
    store.update_job(
        job_id,
        eval_status="processing",
        eval_started_at=started,
        eval_elapsed_seconds=0.0,
        eval_error=None,
    )

    try:
        api_key = _get_openrouter_key()
        jev_model = (os.environ.get("JEV_MODEL") or JEV_DEFAULT_MODEL).strip()
        rule_overrides = store.get_rule_overrides()
        report = evaluate_transcript_with_jev(
            turns,
            speaker_map=speaker_map,
            first_contact=payload.first_contact,
            mock=payload.mock,
            api_key=api_key if not payload.mock else None,
            model=jev_model,
            rule_overrides=rule_overrides,
        )
        updated = store.update_job(
            job_id,
            eval_status="completed",
            eval_elapsed_seconds=round(time.time() - started, 2),
            evaluation=report,
            eval_error=None,
        )
        return _serialize_job(updated or job)
    except Exception as exc:
        logger.exception("Error evaluando trabajo %s con JEV", job_id)
        store.update_job(
            job_id,
            eval_status="error",
            eval_elapsed_seconds=round(time.time() - started, 2),
            eval_error=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}/evaluation/download")
def download_evaluation_json(job_id: str) -> JSONResponse:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    evaluation = job.get("evaluation")
    if job.get("eval_status") != "completed" or not evaluation:
        raise HTTPException(status_code=400, detail="La evaluación JEV aún no está disponible.")
    filename = job["filename"]

    stem = Path(filename).stem
    safe_download_name = re.sub(r"[^\w\-]", "_", stem) or "entrevista"
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_download_name}_evaluacion_jev.json"'
    }
    return JSONResponse(content=evaluation, headers=headers)


@app.get("/api/rules")
def list_jev_rules() -> dict[str, Any]:
    overrides = store.get_rule_overrides()
    rules = serialize_rules_catalog(overrides)
    return {
        "rules": rules,
        "customized_count": sum(1 for r in rules if r.get("is_customized")),
    }


@app.put("/api/rules/{rule_id}")
def update_global_jev_rule(rule_id: str, payload: RuleDefinitionUpdatePayload) -> dict[str, Any]:
    rule_id = rule_id.strip().upper()
    existing_catalog = {r["id"]: r for r in serialize_rules_catalog()}
    if rule_id not in existing_catalog:
        raise HTTPException(status_code=404, detail=f"La regla '{rule_id}' no existe.")

    q_override_dict = {
        qk: {"instructions": qv.instructions, "criteria": dict(qv.criteria)}
        for qk, qv in (payload.questions_override or {}).items()
    }
    store.upsert_rule_override(
        rule_id,
        {
            "section": existing_catalog[rule_id]["section"],
            "custom_text": payload.custom_text,
            "weight": payload.weight,
            "enabled": payload.enabled,
            "auditor_guidance": payload.auditor_guidance,
            "questions_override": q_override_dict,
        },
    )
    overrides = store.get_rule_overrides()
    updated_catalog = serialize_rules_catalog(overrides)
    updated_rule = next((r for r in updated_catalog if r["id"] == rule_id), None)
    return {
        "rule": updated_rule,
        "customized_count": sum(1 for r in updated_catalog if r.get("is_customized")),
    }


@app.delete("/api/rules/{rule_id}/override")
def reset_global_jev_rule(rule_id: str) -> dict[str, Any]:
    rule_id = rule_id.strip().upper()
    store.delete_rule_override(rule_id)
    overrides = store.get_rule_overrides()
    updated_catalog = serialize_rules_catalog(overrides)
    updated_rule = next((r for r in updated_catalog if r["id"] == rule_id), None)
    if not updated_rule:
        raise HTTPException(status_code=404, detail=f"La regla '{rule_id}' no existe.")
    return {
        "rule": updated_rule,
        "customized_count": sum(1 for r in updated_catalog if r.get("is_customized")),
    }


@app.patch("/api/jobs/{job_id}/evaluation/rules/{rule_id}")
def edit_job_evaluation_rule(
    job_id: str,
    rule_id: str,
    payload: EvaluationRuleEditPayload,
) -> dict[str, Any]:
    """Edit an evaluation row on the current interview AND optionally rewrite the global rule for future transcripts."""
    rule_id = rule_id.strip().upper()
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    evaluation = job.get("evaluation")
    if job.get("eval_status") != "completed" or not evaluation:
        raise HTTPException(status_code=400, detail="Primero ejecuta la evaluación JEV en esta entrevista.")

    updated_rule_meta: dict[str, Any] | None = None
    if payload.update_future_rule and payload.rule_override is not None:
        ro = payload.rule_override
        q_override_dict = {
            qk: {"instructions": qv.instructions, "criteria": dict(qv.criteria)}
            for qk, qv in (ro.questions_override or {}).items()
        }
        store.upsert_rule_override(
            rule_id,
            {
                "section": rule_id.split("-")[0],
                "custom_text": ro.custom_text,
                "weight": ro.weight,
                "enabled": ro.enabled,
                "auditor_guidance": ro.auditor_guidance,
                "questions_override": q_override_dict,
            },
        )
        all_rules = serialize_rules_catalog(store.get_rule_overrides())
        updated_rule_meta = next((r for r in all_rules if r["id"] == rule_id), None)

    try:
        new_eval, prev_outcome, new_outcome = apply_instruction_override(
            evaluation,
            rule_id=rule_id,
            override_status=payload.override_status,
            custom_probs=payload.custom_probs,
            auditor_comment=payload.auditor_comment,
            new_weight=updated_rule_meta["weight"] if updated_rule_meta else None,
            new_text=updated_rule_meta["text"] if updated_rule_meta else None,
            is_rule_customized=updated_rule_meta["is_customized"] if updated_rule_meta else None,
            auditor_guidance=updated_rule_meta["auditor_guidance"] if updated_rule_meta else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    updated_job = store.update_job(job_id, evaluation=new_eval)
    store.log_evaluation_edit(
        {
            "job_id": job_id,
            "rule_id": rule_id,
            "previous_outcome": prev_outcome,
            "override_status": payload.override_status,
            "new_outcome": new_outcome,
            "auditor_comment": payload.auditor_comment,
            "propagate_to_future": payload.update_future_rule,
        }
    )

    overrides = store.get_rule_overrides()
    catalog = serialize_rules_catalog(overrides)
    return {
        "job": _serialize_job(updated_job or job),
        "rule": updated_rule_meta or next((r for r in catalog if r["id"] == rule_id), None),
        "customized_rules_count": sum(1 for r in catalog if r.get("is_customized")),
    }


# =====================================================================
# SPA Index Serving (Local Uvicorn fallback)
# =====================================================================

@app.get("/")
def serve_spa_index() -> FileResponse:
    dist_index = DIST_DIR / "index.html"
    if dist_index.exists():
        return FileResponse(dist_index)
    return FileResponse(STATIC_DIR / "index.html")
