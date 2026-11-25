from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.jev_auditor import (
    DEFAULT_MODEL as JEV_DEFAULT_MODEL,
    EXAMPLE_TRANSCRIPT_PATH,
    evaluate_transcript_with_jev,
    is_jev_available,
    load_example_transcript,
    parse_uploaded_transcript,
    suggest_speaker_roles,
)
from app.transcriber import (
    format_transcript_txt,
    get_hardware_status,
    probe_audio_duration,
    run_local_transcription,
)

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "uploads"
ROOT_ENV_PATH = REPO_ROOT / ".env"
LOCAL_ENV_PATH = BASE_DIR / ".env"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("transcriptor")

ALLOWED_MODELS = {"medium", "large-v3-turbo", "large-v3"}
MAX_STORED_JOBS = 10

app = FastAPI(title="Auditoría de Entrevistas ENCOVI — Local + JEV")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Separate pools so JEV API calls never block GPU audio transcription
transcription_executor = ThreadPoolExecutor(max_workers=1)
jev_executor = ThreadPoolExecutor(max_workers=2)
jobs_lock = threading.Lock()
jobs: dict[str, dict[str, Any]] = {}


def _reload_env() -> None:
    """Reload .env from repo root and audio-audit so manual edits take effect without restart."""
    if ROOT_ENV_PATH.exists():
        load_dotenv(ROOT_ENV_PATH, override=True)
    if LOCAL_ENV_PATH.exists():
        load_dotenv(LOCAL_ENV_PATH, override=True)


_reload_env()


def _target_env_path() -> Path:
    return ROOT_ENV_PATH if ROOT_ENV_PATH.exists() else LOCAL_ENV_PATH


def _save_env_key(key: str, value: str) -> None:
    env_path = _target_env_path()
    value = value.strip()
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

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
    os.environ[key] = value


def _get_hf_token() -> str:
    _reload_env()
    return (os.environ.get("HF_TOKEN") or os.environ.get("hf") or "").strip()


def _get_openrouter_key() -> str:
    _reload_env()
    return (os.environ.get("OPENROUTER_API_KEY") or "").strip()


class TokenPayload(BaseModel):
    token: str


class EvaluatePayload(BaseModel):
    speaker_map: dict[str, str] = Field(default_factory=dict)
    first_contact: bool = True
    mock: bool = False


def _sanitize_filename(name: str) -> str:
    base = Path(name or "audio.wav").name
    cleaned = re.sub(r"[^\w.\- ()áéíóúÁÉÍÓÚñÑ]", "_", base).strip()
    return cleaned or "audio.wav"


def _cleanup_old_jobs() -> None:
    """Keep disk usage bounded by removing older completed/errored upload folders."""
    with jobs_lock:
        finished = [
            (jid, job.get("created_at", 0.0))
            for jid, job in jobs.items()
            if job.get("status") in {"completed", "error"}
            and job.get("eval_status") != "processing"
        ]
        if len(finished) <= MAX_STORED_JOBS:
            return
        finished.sort(key=lambda item: item[1])
        to_remove = [jid for jid, _ in finished[:-MAX_STORED_JOBS]]
        removed_paths: list[Path] = []
        for jid in to_remove:
            job = jobs.pop(jid, None)
            if job and job.get("upload_dir"):
                removed_paths.append(Path(job["upload_dir"]))

    for folder in removed_paths:
        shutil.rmtree(folder, ignore_errors=True)


def _update_job(job_id: str, **updates: Any) -> None:
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(updates)


def _serialize_job(job: dict[str, Any]) -> dict[str, Any]:
    eval_elapsed = job.get("eval_elapsed_seconds", 0.0)
    if job.get("eval_status") == "processing" and job.get("eval_started_at"):
        eval_elapsed = round(time.time() - job["eval_started_at"], 1)

    return {
        "job_id": job["job_id"],
        "filename": job["filename"],
        "source": job.get("source", "audio"),
        "has_audio": bool(job.get("has_audio", False)),
        "status": job["status"],
        "stage": job["stage"],
        "progress": job["progress"],
        "duration_seconds": job["duration_seconds"],
        "elapsed_seconds": (
            round(time.time() - job["started_at"], 1)
            if job["status"] == "processing" and job["started_at"]
            else job["elapsed_seconds"]
        ),
        "result": job["result"],
        "error": job["error"],
        "eval_status": job.get("eval_status", "idle"),
        "eval_elapsed_seconds": eval_elapsed,
        "evaluation": job.get("evaluation"),
        "eval_error": job.get("eval_error"),
    }


def _process_transcription_job(
    job_id: str,
    file_path: Path,
    model_name: str,
    denoise: bool,
    diarize: bool,
    min_speakers: int | None,
    max_speakers: int | None,
) -> None:
    started = time.time()
    _update_job(job_id, status="processing", started_at=started, stage="Analizando archivo de audio…", progress=5)

    try:
        duration = probe_audio_duration(file_path)
        _update_job(job_id, duration_seconds=duration)

        def on_progress(stage: str, pct: float) -> None:
            _update_job(
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
        _update_job(
            job_id,
            status="completed",
            stage="¡Transcripción completada!",
            progress=100,
            elapsed_seconds=elapsed,
            result=result,
        )
    except Exception as exc:
        logger.exception("Error procesando trabajo %s", job_id)
        elapsed = round(time.time() - started, 1)
        _update_job(
            job_id,
            status="error",
            stage="Error",
            elapsed_seconds=elapsed,
            error=str(exc),
        )
    finally:
        _cleanup_old_jobs()


def _process_evaluation_job(
    job_id: str,
    turns: list[dict[str, Any]],
    speaker_map: dict[str, str],
    first_contact: bool,
    mock: bool,
) -> None:
    started = time.time()
    _update_job(
        job_id,
        eval_status="processing",
        eval_started_at=started,
        eval_elapsed_seconds=0.0,
        eval_error=None,
    )
    try:
        api_key = _get_openrouter_key()
        jev_model = (os.environ.get("JEV_MODEL") or JEV_DEFAULT_MODEL).strip()
        report = evaluate_transcript_with_jev(
            turns,
            speaker_map=speaker_map,
            first_contact=first_contact,
            mock=mock,
            api_key=api_key if not mock else None,
            model=jev_model,
        )
        _update_job(
            job_id,
            eval_status="completed",
            eval_elapsed_seconds=round(time.time() - started, 1),
            evaluation=report,
            eval_error=None,
        )
    except Exception as exc:
        logger.exception("Error evaluando trabajo %s con JEV", job_id)
        _update_job(
            job_id,
            eval_status="error",
            eval_elapsed_seconds=round(time.time() - started, 1),
            eval_error=str(exc),
        )


@app.get("/")
def serve_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def system_status() -> dict[str, Any]:
    hw = get_hardware_status()
    return {
        **hw,
        "hf_token_configured": bool(_get_hf_token()),
        "openrouter_configured": bool(_get_openrouter_key()),
        "jev_available": is_jev_available(),
        "jev_model": (os.environ.get("JEV_MODEL") or JEV_DEFAULT_MODEL).strip(),
        "example_available": EXAMPLE_TRANSCRIPT_PATH.exists(),
        "default_model": os.environ.get("WHISPER_MODEL", "large-v3-turbo"),
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


@app.post("/api/transcribe")
async def create_transcription_job(
    file: UploadFile = File(...),
    model: str = Form("large-v3-turbo"),
    denoise: bool = Form(True),
    diarize: bool = Form(True),
    min_speakers: int | None = Form(None),
    max_speakers: int | None = Form(None),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Debes seleccionar un archivo de audio.")

    if model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"Modelo no permitido: {model}")

    if diarize and not _get_hf_token():
        raise HTTPException(
            status_code=400,
            detail="Configura tu token gratuito de Hugging Face antes de activar la identificación de hablantes.",
        )

    if min_speakers is not None and max_speakers is not None and min_speakers > max_speakers:
        raise HTTPException(status_code=400, detail="El mínimo de hablantes no puede ser mayor que el máximo.")

    job_id = uuid.uuid4().hex[:12]
    safe_name = _sanitize_filename(file.filename)
    job_dir = UPLOADS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    dest_path = job_dir / safe_name

    # Guardar el archivo en bloques para soportar grabaciones largas (1-2 horas) sin saturar RAM
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

    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "filename": safe_name,
            "source": "audio",
            "has_audio": True,
            "file_path": str(dest_path),
            "upload_dir": str(job_dir),
            "status": "queued",
            "stage": "En cola para procesar…",
            "progress": 3,
            "created_at": time.time(),
            "started_at": None,
            "elapsed_seconds": 0.0,
            "duration_seconds": None,
            "result": None,
            "error": None,
            "eval_status": "idle",
            "eval_started_at": None,
            "eval_elapsed_seconds": 0.0,
            "evaluation": None,
            "eval_error": None,
        }

    transcription_executor.submit(
        _process_transcription_job,
        job_id,
        dest_path,
        model,
        denoise,
        diarize,
        min_speakers,
        max_speakers,
    )

    return {"job_id": job_id}


def _register_transcript_job(filename: str, parsed: dict[str, Any], source: str) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    safe_name = _sanitize_filename(filename)
    job = {
        "job_id": job_id,
        "filename": safe_name,
        "source": source,
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
    with jobs_lock:
        jobs[job_id] = job
    _cleanup_old_jobs()
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
def load_example_enovi_transcript() -> dict[str, Any]:
    try:
        parsed = load_example_transcript()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _register_transcript_job(parsed["filename"], parsed, source="example")


@app.post("/api/jobs/{job_id}/evaluate")
def start_jev_evaluation(job_id: str, payload: EvaluatePayload) -> dict[str, Any]:
    if not is_jev_available():
        raise HTTPException(
            status_code=500,
            detail="El motor encovi_jev no está disponible en el repositorio.",
        )

    if not payload.mock and not _get_openrouter_key():
        raise HTTPException(
            status_code=400,
            detail=(
                "No se encontró OPENROUTER_API_KEY en el archivo .env. "
                "Agrega OPENROUTER_API_KEY=sk-or-... en tu .env (o usa el modo prueba sin conexión)."
            ),
        )

    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
        if job["status"] != "completed" or not job.get("result"):
            raise HTTPException(status_code=400, detail="La transcripción todavía no está lista.")
        if job.get("eval_status") == "processing":
            raise HTTPException(status_code=409, detail="Ya hay una evaluación JEV en curso para esta entrevista.")
        turns = list(job["result"].get("turns") or [])

    if not turns:
        raise HTTPException(status_code=400, detail="No hay intervenciones para evaluar.")

    speaker_map = dict(payload.speaker_map or {})
    from app.jev_auditor import INTERVIEWER, normalize_speaker

    if not any(normalize_speaker(str(t.get("speaker") or ""), speaker_map) == INTERVIEWER for t in turns):
        raise HTTPException(
            status_code=400,
            detail="Debes asignar al menos un hablante como ENCUESTADOR antes de evaluar.",
        )

    _update_job(
        job_id,
        eval_status="processing",
        eval_started_at=time.time(),
        eval_elapsed_seconds=0.0,
        eval_error=None,
    )

    jev_executor.submit(
        _process_evaluation_job,
        job_id,
        turns,
        speaker_map,
        payload.first_contact,
        payload.mock,
    )

    return {"job_id": job_id, "eval_status": "processing"}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Trabajo de transcripción no encontrado.")
        return _serialize_job(job)


@app.get("/api/jobs/{job_id}/audio")
def get_job_audio(job_id: str) -> FileResponse:
    with jobs_lock:
        job = jobs.get(job_id)
        file_path = Path(job["file_path"]) if job and job.get("file_path") else None

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo de audio no disponible.")

    return FileResponse(path=file_path, filename=file_path.name)


@app.get("/api/jobs/{job_id}/download")
def download_transcript_txt(job_id: str) -> PlainTextResponse:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
        if job["status"] != "completed" or not job.get("result"):
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
    return PlainTextResponse(content=txt_content, headers=headers, media_type="text/plain; charset=utf-8")


@app.get("/api/jobs/{job_id}/evaluation/download")
def download_evaluation_json(job_id: str) -> JSONResponse:
    with jobs_lock:
        job = jobs.get(job_id)
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
