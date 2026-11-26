from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("transcriptor.cloud_stt")

ASSEMBLYAI_BASE_URL = "https://api.assemblyai.com/v2"
DEEPGRAM_LISTEN_URL = "https://api.deepgram.com/v1/listen"


def _normalize_speaker_turns(
    raw_utterances: list[dict[str, Any]],
    *,
    diarize: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Convert provider utterances into Spanish chronological turns (`Hablante 1`, `Hablante 2`, …)."""
    speaker_map: dict[str, str] = {}
    ordered_speakers: list[str] = []

    def to_spanish_speaker(raw_spk: Any) -> str:
        if not diarize:
            return "Transcripción"
        key = str(raw_spk if raw_spk is not None and raw_spk != "" else "UNKNOWN")
        if key not in speaker_map:
            label = f"Hablante {len(speaker_map) + 1}"
            speaker_map[key] = label
            ordered_speakers.append(label)
        return speaker_map[key]

    merged: list[dict[str, Any]] = []
    for utt in raw_utterances:
        text = str(utt.get("text") or "").strip()
        if not text:
            continue
        speaker = to_spanish_speaker(utt.get("speaker"))
        start = float(utt.get("start") or 0.0)
        end = float(utt.get("end") if utt.get("end") is not None else start)
        if end < start:
            end = start

        if (
            merged
            and merged[-1]["speaker"] == speaker
            and (start - merged[-1]["end"]) <= 2.0
            and (end - merged[-1]["start"]) <= 60.0
            and (len(merged[-1]["text"]) + len(text) + 1) <= 650
        ):
            merged[-1]["end"] = round(max(merged[-1]["end"], end), 2)
            merged[-1]["text"] = f"{merged[-1]['text']} {text}".strip()
        else:
            merged.append(
                {
                    "speaker": speaker,
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "text": text,
                    "has_overlap": False,
                }
            )

    # Mark turns whose timestamps overlap another speaker by >= 0.35s
    for i in range(len(merged)):
        for j in range(i + 1, len(merged)):
            if merged[j]["start"] >= merged[i]["end"]:
                break
            if merged[j]["speaker"] != merged[i]["speaker"]:
                ov = min(merged[i]["end"], merged[j]["end"]) - max(
                    merged[i]["start"], merged[j]["start"]
                )
                if ov >= 0.35:
                    merged[i]["has_overlap"] = True
                    merged[j]["has_overlap"] = True

    if not diarize and merged:
        ordered_speakers = ["Transcripción"]

    return merged, ordered_speakers


# =====================================================================
# AssemblyAI (Universal-2 + Speaker Diarization, ~$0.17/hr, $50 free)
# =====================================================================

def upload_local_file_to_assemblyai(file_path: Path, api_key: str) -> str:
    """Stream a local audio file to AssemblyAI's temporary upload endpoint."""
    headers = {"authorization": api_key}

    def _read_chunks():
        with file_path.open("rb") as fh:
            while True:
                chunk = fh.read(5 * 1024 * 1024)
                if not chunk:
                    break
                yield chunk

    resp = requests.post(
        f"{ASSEMBLYAI_BASE_URL}/upload",
        headers=headers,
        data=_read_chunks(),
        timeout=300,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"AssemblyAI rechazó la subida del audio (HTTP {resp.status_code}): {resp.text[:300]}"
        )
    upload_url = resp.json().get("upload_url")
    if not upload_url:
        raise RuntimeError("AssemblyAI no devolvió 'upload_url'.")
    return str(upload_url)


def submit_assemblyai_transcription(
    *,
    audio_url: str,
    api_key: str,
    diarize: bool = True,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> str:
    """Create an async Spanish transcription + speaker diarization job on AssemblyAI."""
    payload: dict[str, Any] = {
        "audio_url": audio_url,
        "language_code": "es",
        "punctuate": True,
        "format_text": True,
        "speaker_labels": bool(diarize),
    }
    if diarize:
        if min_speakers is not None and max_speakers is not None and min_speakers == max_speakers:
            payload["speakers_expected"] = int(min_speakers)
        elif min_speakers is not None or max_speakers is not None:
            opts: dict[str, int] = {}
            if min_speakers is not None:
                opts["min_speakers_expected"] = int(min_speakers)
            if max_speakers is not None:
                opts["max_speakers_expected"] = int(max_speakers)
            payload["speaker_options"] = opts

    resp = requests.post(
        f"{ASSEMBLYAI_BASE_URL}/transcript",
        headers={"authorization": api_key, "content-type": "application/json"},
        json=payload,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        detail = resp.text[:300]
        if resp.status_code == 401:
            raise RuntimeError(
                "AssemblyAI rechazó tu ASSEMBLYAI_API_KEY (HTTP 401). Verifica la clave."
            )
        raise RuntimeError(f"Error al crear transcripción en AssemblyAI (HTTP {resp.status_code}): {detail}")

    transcript_id = resp.json().get("id")
    if not transcript_id:
        raise RuntimeError("AssemblyAI no devolvió un ID de transcripción.")
    return str(transcript_id)


def poll_assemblyai_transcription(
    transcript_id: str,
    api_key: str,
    *,
    diarize: bool = True,
) -> dict[str, Any]:
    """Check the status of an AssemblyAI transcription job (<300ms serverless-safe call)."""
    resp = requests.get(
        f"{ASSEMBLYAI_BASE_URL}/transcript/{transcript_id}",
        headers={"authorization": api_key},
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"No se pudo consultar AssemblyAI (HTTP {resp.status_code}): {resp.text[:250]}"
        )
    data = resp.json()
    status = str(data.get("status") or "processing").lower()

    if status in ("queued", "processing"):
        return {
            "status": "processing",
            "stage": (
                "En cola en AssemblyAI…"
                if status == "queued"
                else "Transcribiendo e identificando hablantes en AssemblyAI…"
            ),
            "progress": 35 if status == "queued" else 72,
        }

    if status == "error":
        err = data.get("error") or "AssemblyAI reportó un error procesando el audio."
        return {"status": "error", "error": str(err)}

    # Completed: parse utterances (timestamps in ms -> seconds)
    raw_utts: list[dict[str, Any]] = []
    utterances = data.get("utterances") or []
    if utterances:
        for u in utterances:
            raw_utts.append(
                {
                    "speaker": u.get("speaker"),
                    "start": float(u.get("start") or 0.0) / 1000.0,
                    "end": float(u.get("end") or 0.0) / 1000.0,
                    "text": u.get("text") or "",
                }
            )
    elif data.get("text"):
        dur = float(data.get("audio_duration") or 0.0)
        raw_utts.append(
            {
                "speaker": "A",
                "start": 0.0,
                "end": dur,
                "text": str(data.get("text") or ""),
            }
        )

    turns, speakers = _normalize_speaker_turns(raw_utts, diarize=diarize)
    duration = data.get("audio_duration")
    return {
        "status": "completed",
        "duration_seconds": float(duration) if isinstance(duration, (int, float)) else None,
        "turns": turns,
        "speakers": speakers,
        "warning": None if turns else "No se detectó habla clara en el archivo de audio.",
        "note": "Transcrito en la nube con AssemblyAI Universal-2 (sin requerir token de Hugging Face ni GPU local).",
    }


# =====================================================================
# Deepgram (Nova-3 + Speaker Diarization, $200 free credits)
# =====================================================================

def run_deepgram_transcription(
    *,
    api_key: str,
    audio_url: str | None = None,
    file_path: Path | None = None,
    content_type: str = "audio/mpeg",
    diarize: bool = True,
) -> dict[str, Any]:
    """Run synchronous batch Spanish transcription + diarization via Deepgram Nova-3."""
    params: dict[str, str] = {
        "model": "nova-3",
        "language": "es",
        "smart_format": "true",
        "punctuate": "true",
        "utterances": "true",
    }
    if diarize:
        params["diarize"] = "true"

    headers: dict[str, str] = {"Authorization": f"Token {api_key}"}

    if audio_url:
        headers["Content-Type"] = "application/json"
        resp = requests.post(
            DEEPGRAM_LISTEN_URL,
            headers=headers,
            params=params,
            json={"url": audio_url},
            timeout=58,
        )
    elif file_path and file_path.exists():
        headers["Content-Type"] = content_type or "application/octet-stream"
        with file_path.open("rb") as fh:
            resp = requests.post(
                DEEPGRAM_LISTEN_URL,
                headers=headers,
                params=params,
                data=fh,
                timeout=180,
            )
    else:
        raise ValueError("Se requiere 'audio_url' o 'file_path' para Deepgram.")

    if resp.status_code != 200:
        if resp.status_code in (401, 403):
            raise RuntimeError(
                "Deepgram rechazó tu DEEPGRAM_API_KEY (HTTP 401/403). Verifica la clave."
            )
        raise RuntimeError(
            f"Error al transcribir con Deepgram (HTTP {resp.status_code}): {resp.text[:300]}"
        )

    payload = resp.json()
    results = payload.get("results") or {}
    metadata = payload.get("metadata") or {}
    duration = metadata.get("duration")

    raw_utts: list[dict[str, Any]] = []
    utterances = results.get("utterances") or []
    if utterances:
        for u in utterances:
            raw_utts.append(
                {
                    "speaker": u.get("speaker"),
                    "start": float(u.get("start") or 0.0),
                    "end": float(u.get("end") or 0.0),
                    "text": u.get("transcript") or "",
                }
            )
    else:
        channels = results.get("channels") or []
        alts = (channels[0].get("alternatives") or []) if channels else []
        transcript_txt = (alts[0].get("transcript") or "").strip() if alts else ""
        if transcript_txt:
            raw_utts.append(
                {
                    "speaker": 0,
                    "start": 0.0,
                    "end": float(duration or 0.0),
                    "text": transcript_txt,
                }
            )

    turns, speakers = _normalize_speaker_turns(raw_utts, diarize=diarize)
    return {
        "duration_seconds": float(duration) if isinstance(duration, (int, float)) else None,
        "turns": turns,
        "speakers": speakers,
        "warning": None if turns else "No se detectó habla clara en el archivo de audio.",
        "note": "Transcrito en la nube con Deepgram Nova-3 (sin requerir token de Hugging Face ni GPU local).",
    }
