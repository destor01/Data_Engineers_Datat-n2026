from __future__ import annotations

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
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.transcriber import (
    format_transcript_txt,
    get_hardware_status,
    probe_audio_duration,
    run_local_transcription,
)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "uploads"
ENV_PATH = BASE_DIR / ".env"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(ENV_PATH, override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("transcriptor")

ALLOWED_MODELS = {"medium", "large-v3-turbo", "large-v3"}
MAX_STORED_JOBS = 5

app = FastAPI(title="Transcriptor Local de Entrevistas (ES)")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

executor = ThreadPoolExecutor(max_workers=1)
jobs_lock = threading.Lock()
jobs: dict[str, dict[str, Any]] = {}


class TokenPayload(BaseModel):
    token: str


def _get_hf_token() -> str:
    return (os.environ.get("HF_TOKEN") or "").strip()


def _save_hf_token_to_env(token: str) -> None:
    token = token.strip()
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    replaced = False
    new_lines: list[str] = []
    for line in lines:
        if line.strip().startswith("HF_TOKEN="):
            new_lines.append(f"HF_TOKEN={token}")
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        new_lines.append(f"HF_TOKEN={token}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    os.environ["HF_TOKEN"] = token


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


def _process_job(
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


@app.get("/")
def serve_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def system_status() -> dict[str, Any]:
    hw = get_hardware_status()
    return {
        **hw,
        "hf_token_configured": bool(_get_hf_token()),
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
    _save_hf_token_to_env(token)
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
        }

    executor.submit(
        _process_job,
        job_id,
        dest_path,
        model,
        denoise,
        diarize,
        min_speakers,
        max_speakers,
    )

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Trabajo de transcripción no encontrado.")

        payload = {
            "job_id": job["job_id"],
            "filename": job["filename"],
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
        }
    return payload


@app.get("/api/jobs/{job_id}/audio")
def get_job_audio(job_id: str) -> FileResponse:
    with jobs_lock:
        job = jobs.get(job_id)
        file_path = Path(job["file_path"]) if job else None

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
