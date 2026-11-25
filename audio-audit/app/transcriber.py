from __future__ import annotations

import functools
import gc
import inspect
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any, Callable

# WhisperX passes preloaded audio waveforms in memory to Pyannote, so torchcodec decoding is not used.
warnings.filterwarnings("ignore", message=".*torchcodec.*", category=UserWarning)

logger = logging.getLogger(__name__)


def _configure_windows_cuda_dlls() -> None:
    """Ensure PyTorch and NVIDIA CUDA/cuDNN DLLs inside the venv are discoverable on Windows."""
    if sys.platform != "win32":
        return

    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    candidate_dirs = [
        site_packages / "torch" / "lib",
        site_packages / "ctranslate2",
    ]

    nvidia_root = site_packages / "nvidia"
    if nvidia_root.is_dir():
        for bin_dir in nvidia_root.glob("*/bin"):
            if bin_dir.is_dir():
                candidate_dirs.append(bin_dir)

    existing_path = os.environ.get("PATH", "")
    added: list[str] = []
    for directory in candidate_dirs:
        if directory.is_dir():
            dir_str = str(directory)
            try:
                os.add_dll_directory(dir_str)
            except OSError:
                pass
            if dir_str not in existing_path:
                added.append(dir_str)

    if added:
        os.environ["PATH"] = os.pathsep.join(added) + os.pathsep + existing_path


_configure_windows_cuda_dlls()

import torch  # noqa: E402


def _configure_torch_safe_globals() -> None:
    """Allow safe checkpoint classes used by Pyannote/WhisperX under PyTorch 2.6+."""
    add_safe_globals = getattr(torch.serialization, "add_safe_globals", None)
    if add_safe_globals is None:
        return

    safe_types: list[Any] = [Any, dict, list, tuple, set]
    try:
        import collections

        safe_types.append(collections.defaultdict)
    except Exception:
        pass

    try:
        from torch.torch_version import TorchVersion

        safe_types.append(TorchVersion)
    except Exception:
        pass

    try:
        import omegaconf
        from omegaconf.base import ContainerMetadata, Metadata
        from omegaconf.nodes import AnyNode, ValueNode

        safe_types.extend(
            [
                omegaconf.ListConfig,
                omegaconf.DictConfig,
                ContainerMetadata,
                Metadata,
                AnyNode,
                ValueNode,
            ]
        )
    except Exception:
        pass

    try:
        from pyannote.audio.core.model import Introspection
        from pyannote.audio.core.task import Problem, Resolution, Specifications

        safe_types.extend([Introspection, Specifications, Problem, Resolution])
    except Exception:
        pass

    try:
        add_safe_globals(safe_types)
    except Exception as exc:
        logger.debug("No se pudieron registrar safe globals adicionales: %s", exc)


@functools.lru_cache(maxsize=1)
def get_hardware_status() -> dict[str, Any]:
    cuda_available = torch.cuda.is_available()
    gpu_name = None
    vram_gb = None
    if cuda_available:
        try:
            gpu_name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            vram_gb = round(props.total_memory / (1024**3), 1)
        except Exception:
            gpu_name = "GPU NVIDIA"

    return {
        "cuda_available": cuda_available,
        "gpu_name": gpu_name,
        "vram_gb": vram_gb,
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "ffprobe_available": shutil.which("ffprobe") is not None,
    }


def probe_audio_duration(file_path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except Exception:
        pass
    return None


def preprocess_audio_to_wav(input_path: Path, output_wav: Path, denoise: bool = True) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "No se encontró ffmpeg en el sistema. Instálalo o añádelo al PATH para procesar audios."
        )

    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-vn", "-ac", "1", "-ar", "16000"]
    if denoise:
        # Filtro suave que limpia ruido estacionario y equilibra volúmenes entre hablantes
        cmd.extend(
            [
                "-af",
                "highpass=f=80,lowpass=f=7600,afftdn=nf=-25:tn=1,dynaudnorm=f=150:g=15",
            ]
        )
    cmd.extend(["-c:a", "pcm_s16le", str(output_wav)])

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not output_wav.exists():
        stderr_tail = (proc.stderr or "").strip().splitlines()[-4:]
        detail = " ".join(stderr_tail)
        raise RuntimeError(
            f"No se pudo leer o convertir el archivo de audio con ffmpeg. Verifica que sea un audio válido. ({detail})"
        )


def _free_gpu() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _get_diarization_pipeline_cls():
    import whisperx

    try:
        from whisperx.diarize import DiarizationPipeline

        return DiarizationPipeline
    except ImportError:
        pass

    if hasattr(whisperx, "DiarizationPipeline"):
        return whisperx.DiarizationPipeline

    raise RuntimeError(
        "La versión instalada de WhisperX no expone DiarizationPipeline. Reinstala whisperx."
    )


def _create_diarization_pipeline(hf_token: str, device: str):
    cls = _get_diarization_pipeline_cls()
    sig = inspect.signature(cls.__init__)
    params = sig.parameters

    kwargs: dict[str, Any] = {"device": device}
    if "token" in params:
        kwargs["token"] = hf_token
    elif "use_auth_token" in params:
        kwargs["use_auth_token"] = hf_token
    else:
        kwargs["use_auth_token"] = hf_token

    return cls(**kwargs)


def _extract_overlap_spans(diarize_segments: Any, min_overlap_sec: float = 0.35) -> list[tuple[float, float]]:
    """Detect intervals where at least two distinct speakers overlap."""
    if diarize_segments is None:
        return []

    rows: list[tuple[float, float, str]] = []
    try:
        for _, row in diarize_segments.iterrows():
            start = float(row["start"])
            end = float(row["end"])
            speaker = str(row["speaker"])
            if end > start:
                rows.append((start, end, speaker))
    except Exception:
        return []

    rows.sort(key=lambda r: r[0])
    overlaps: list[tuple[float, float]] = []

    for i in range(len(rows)):
        s1, e1, spk1 = rows[i]
        for j in range(i + 1, len(rows)):
            s2, e2, spk2 = rows[j]
            if s2 >= e1:
                break
            if spk2 == spk1:
                continue
            ov_start = max(s1, s2)
            ov_end = min(e1, e2)
            if (ov_end - ov_start) >= min_overlap_sec:
                overlaps.append((ov_start, ov_end))

    return overlaps


def _turn_has_overlap(start: float, end: float, overlap_spans: list[tuple[float, float]]) -> bool:
    for ov_s, ov_e in overlap_spans:
        if ov_e <= start:
            continue
        if ov_s >= end:
            continue
        if (min(end, ov_e) - max(start, ov_s)) >= 0.35:
            return True
    return False


def _split_segment_by_word_speakers(segment: dict[str, Any], diarize_enabled: bool) -> list[dict[str, Any]]:
    """Split a Whisper segment if word-level diarization reveals a mid-segment speaker switch."""
    seg_text = (segment.get("text") or "").strip()
    if not seg_text:
        return []

    seg_start = float(segment.get("start") or 0.0)
    seg_end = float(segment.get("end") or seg_start)
    seg_speaker = segment.get("speaker")

    words = segment.get("words") or []
    if not diarize_enabled or not words:
        return [
            {
                "raw_speaker": seg_speaker or "SPEAKER_00",
                "start": seg_start,
                "end": seg_end,
                "text": seg_text,
            }
        ]

    # Propagate speaker labels to unaligned punctuation/short words inside the segment
    labeled_words: list[dict[str, Any]] = []
    last_speaker = seg_speaker
    for w in words:
        word_text = (w.get("word") or "").strip()
        if not word_text:
            continue
        spk = w.get("speaker") or last_speaker
        if spk:
            last_speaker = spk
        labeled_words.append(
            {
                "word": word_text,
                "start": w.get("start"),
                "end": w.get("end"),
                "speaker": spk,
            }
        )

    if not labeled_words:
        return [
            {
                "raw_speaker": seg_speaker or "SPEAKER_00",
                "start": seg_start,
                "end": seg_end,
                "text": seg_text,
            }
        ]

    # Backfill leading words whose speaker was None using the first known speaker
    first_known = next((w["speaker"] for w in labeled_words if w["speaker"]), seg_speaker or "SPEAKER_00")
    for w in labeled_words:
        if not w["speaker"]:
            w["speaker"] = first_known

    distinct_speakers = {w["speaker"] for w in labeled_words}
    if len(distinct_speakers) <= 1:
        return [
            {
                "raw_speaker": first_known,
                "start": seg_start,
                "end": seg_end,
                "text": seg_text,
            }
        ]

    # Build sub-turns where speaker changes
    subturns: list[dict[str, Any]] = []
    current_words: list[str] = []
    current_spk = labeled_words[0]["speaker"]
    current_start = labeled_words[0]["start"] if labeled_words[0]["start"] is not None else seg_start
    current_end = labeled_words[0]["end"] if labeled_words[0]["end"] is not None else current_start

    for w in labeled_words:
        w_start = w["start"] if w["start"] is not None else current_end
        w_end = w["end"] if w["end"] is not None else w_start

        if w["speaker"] != current_spk and current_words:
            subturns.append(
                {
                    "raw_speaker": current_spk,
                    "start": float(current_start),
                    "end": float(max(current_end, current_start)),
                    "text": " ".join(current_words).strip(),
                }
            )
            current_spk = w["speaker"]
            current_words = [w["word"]]
            current_start = w_start
            current_end = w_end
        else:
            current_words.append(w["word"])
            current_end = max(current_end, w_end)

    if current_words:
        subturns.append(
            {
                "raw_speaker": current_spk,
                "start": float(current_start),
                "end": float(max(current_end, seg_end if current_end == current_start else current_end)),
                "text": " ".join(current_words).strip(),
            }
        )

    return subturns


def build_turns(
    segments: list[dict[str, Any]],
    diarize_enabled: bool,
    overlap_spans: list[tuple[float, float]],
) -> tuple[list[dict[str, Any]], list[str]]:
    raw_items: list[dict[str, Any]] = []
    for seg in segments:
        raw_items.extend(_split_segment_by_word_speakers(seg, diarize_enabled=diarize_enabled))

    if not raw_items:
        return [], []

    # Map speaker IDs chronologically in order of appearance -> Hablante 1, Hablante 2, ...
    speaker_map: dict[str, str] = {}
    ordered_speakers: list[str] = []

    def to_spanish_speaker(raw_spk: str | None) -> str:
        if not diarize_enabled:
            return "Transcripción"
        key = raw_spk or "UNKNOWN"
        if key not in speaker_map:
            label = f"Hablante {len(speaker_map) + 1}"
            speaker_map[key] = label
            ordered_speakers.append(label)
        return speaker_map[key]

    merged: list[dict[str, Any]] = []
    for item in raw_items:
        text = item["text"].strip()
        if not text:
            continue
        speaker = to_spanish_speaker(item["raw_speaker"])
        start = float(item["start"])
        end = float(item["end"])

        if (
            merged
            and merged[-1]["speaker"] == speaker
            and (start - merged[-1]["end"]) <= 2.0
            and (end - merged[-1]["start"]) <= 60.0
            and (len(merged[-1]["text"]) + len(text) + 1) <= 650
        ):
            merged[-1]["end"] = max(merged[-1]["end"], end)
            merged[-1]["text"] = f"{merged[-1]['text']} {text}".strip()
        else:
            merged.append(
                {
                    "speaker": speaker,
                    "start": round(start, 2),
                    "end": round(max(end, start), 2),
                    "text": text,
                }
            )

    for turn in merged:
        turn["start"] = round(turn["start"], 2)
        turn["end"] = round(turn["end"], 2)
        turn["has_overlap"] = _turn_has_overlap(turn["start"], turn["end"], overlap_spans)

    return merged, ordered_speakers


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_transcript_txt(
    filename: str,
    duration_seconds: float | None,
    turns: list[dict[str, Any]],
    speakers: list[str],
) -> str:
    lines = [
        "TRANSCRIPCIÓN DE ENTREVISTA",
        f"Archivo: {filename}",
    ]
    if duration_seconds is not None:
        lines.append(f"Duración: {format_timestamp(duration_seconds)}")
    if speakers:
        lines.append(f"Hablantes detectados: {', '.join(speakers)}")
    lines.append("=" * 60)
    lines.append("")

    for turn in turns:
        start_val = turn.get("start")
        end_val = turn.get("end")
        if start_val is not None and end_val is not None and end_val != start_val:
            ts = f"[{format_timestamp(start_val)} - {format_timestamp(end_val)}] "
        elif start_val is not None:
            ts = f"[{format_timestamp(start_val)}] "
        else:
            ts = ""
        overlap_tag = " [voces superpuestas]" if turn.get("has_overlap") else ""
        lines.append(f"{ts}{turn['speaker']}{overlap_tag}:")
        lines.append(turn["text"])
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def run_local_transcription(
    audio_path: Path,
    *,
    model_name: str = "large-v3-turbo",
    denoise: bool = True,
    diarize: bool = True,
    hf_token: str | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    progress_cb: Callable[[str, float], None] | None = None,
) -> dict[str, Any]:
    """Run local WhisperX + Spanish wav2vec2 alignment + Pyannote speaker diarization."""

    def report(stage: str, pct: float) -> None:
        if progress_cb:
            progress_cb(stage, pct)

    _configure_torch_safe_globals()
    import whisperx

    device = "cuda" if torch.cuda.is_available() else "cpu"
    env_compute = os.environ.get("WHISPER_COMPUTE_TYPE", "").strip()
    if device == "cuda":
        compute_type = env_compute or "int8"
        batch_size = int(os.environ.get("WHISPER_BATCH_SIZE", "8"))
    else:
        compute_type = "int8"
        batch_size = 4

    warning_messages: list[str] = []
    if device == "cpu":
        warning_messages.append(
            "CUDA no estuvo disponible; se procesó en CPU (más lento que en GPU)."
        )

    with tempfile.TemporaryDirectory(prefix="transcriber_") as tmp_dir:
        wav_path = Path(tmp_dir) / "normalized_16k.wav"

        report(
            "Limpiando ruido y normalizando el audio…" if denoise else "Preparando el audio (16 kHz mono)…",
            10,
        )
        preprocess_audio_to_wav(audio_path, wav_path, denoise=denoise)
        audio = whisperx.load_audio(str(wav_path))

        # 1. Transcripción con WhisperX (faster-whisper)
        report(f"Cargando modelo Whisper ({model_name}) en {device.upper()}…", 18)
        asr_options = {
            "condition_on_previous_text": False,
        }
        try:
            model = whisperx.load_model(
                model_name,
                device,
                compute_type=compute_type,
                language="es",
                asr_options=asr_options,
            )
        except TypeError:
            model = whisperx.load_model(
                model_name,
                device,
                compute_type=compute_type,
                language="es",
            )

        report("Transcribiendo entrevista en español…", 22)

        def on_transcribe_progress(pct: float) -> None:
            mapped = 22.0 + min(max(float(pct), 0.0), 100.0) * 0.38
            report(f"Transcribiendo entrevista en español ({int(pct)} %)…", mapped)

        result = None
        last_oom: Exception | None = None
        for current_batch in (batch_size, max(2, batch_size // 2), 1):
            try:
                try:
                    result = model.transcribe(
                        audio,
                        batch_size=current_batch,
                        language="es",
                        progress_callback=on_transcribe_progress,
                    )
                except TypeError:
                    result = model.transcribe(audio, batch_size=current_batch, language="es")
                last_oom = None
                break
            except torch.cuda.OutOfMemoryError as exc:
                last_oom = exc
                logger.warning("VRAM insuficiente con batch_size=%s; reintentando menor…", current_batch)
                _free_gpu()
        del model
        _free_gpu()

        if last_oom is not None or result is None:
            raise RuntimeError(
                "La memoria de la GPU (6 GB) no fue suficiente con este modelo. "
                "Prueba seleccionando el modelo 'medium' o 'large-v3-turbo'."
            )

        segments = result.get("segments") or []
        if not segments:
            return {
                "turns": [],
                "speakers": [],
                "warning": "No se detectó habla clara en el archivo de audio.",
            }

        # 2. Alineación forzada en español para marcas de tiempo por palabra
        report("Alineando palabras y marcas de tiempo en español…", 61)

        def on_align_progress(pct: float) -> None:
            mapped = 61.0 + min(max(float(pct), 0.0), 100.0) * 0.13
            report(f"Alineando marcas de tiempo ({int(pct)} %)…", mapped)

        try:
            model_a, metadata = whisperx.load_align_model(language_code="es", device=device)
            try:
                result = whisperx.align(
                    segments,
                    model_a,
                    metadata,
                    audio,
                    device,
                    return_char_alignments=False,
                    progress_callback=on_align_progress,
                )
            except TypeError:
                result = whisperx.align(
                    segments,
                    model_a,
                    metadata,
                    audio,
                    device,
                    return_char_alignments=False,
                )
            del model_a
            _free_gpu()
        except Exception as exc:
            logger.exception("Error durante alineación de palabras: %s", exc)
            _free_gpu()
            warning_messages.append(
                "No se pudo completar la alineación fina por palabra; se usan marcas de tiempo por segmento."
            )

        # 3. Diarización de hablantes (Pyannote)
        overlap_spans: list[tuple[float, float]] = []
        diarize_applied = False
        if diarize:
            if not hf_token:
                raise RuntimeError(
                    "Falta el token de Hugging Face (HF_TOKEN) para identificar hablantes."
                )

            report("Cargando modelo de identificación de hablantes (Pyannote)…", 75)
            try:
                diarize_model = _create_diarization_pipeline(hf_token=hf_token, device=device)
            except Exception as exc:
                _free_gpu()
                msg = str(exc)
                if any(k in msg.lower() for k in ("401", "403", "gated", "unauthorized", "token", "access")):
                    raise RuntimeError(
                        "Hugging Face rechazó el acceso al modelo de hablantes (Pyannote).\n"
                        "Verifica que:\n"
                        "1) Tu token sea válido (permiso Read).\n"
                        "2) Hayas aceptado las condiciones de uso en:\n"
                        "   • https://huggingface.co/pyannote/speaker-diarization-community-1"
                    ) from exc
                raise RuntimeError(f"Error al cargar el modelo de diarización: {msg}") from exc

            report("Identificando hablantes en la entrevista…", 78)

            def on_diarize_progress(pct: float) -> None:
                mapped = 78.0 + min(max(float(pct), 0.0), 100.0) * 0.17
                report(f"Identificando hablantes ({int(pct)} %)…", mapped)

            try:
                diarize_kwargs: dict[str, Any] = {}
                if min_speakers is not None and max_speakers is not None and min_speakers == max_speakers:
                    diarize_kwargs["num_speakers"] = min_speakers
                else:
                    if min_speakers is not None:
                        diarize_kwargs["min_speakers"] = min_speakers
                    if max_speakers is not None:
                        diarize_kwargs["max_speakers"] = max_speakers

                try:
                    diarize_segments = diarize_model(
                        audio,
                        progress_callback=on_diarize_progress,
                        **diarize_kwargs,
                    )
                except TypeError:
                    diarize_segments = diarize_model(audio, **diarize_kwargs)

                overlap_spans = _extract_overlap_spans(diarize_segments)
                result = whisperx.assign_word_speakers(diarize_segments, result)
                diarize_applied = True
            finally:
                del diarize_model
                _free_gpu()

        # 4. Construcción de turnos legibles en español
        report("Organizando transcripción por hablante…", 95)
        turns, speakers = build_turns(
            result.get("segments") or [],
            diarize_enabled=diarize_applied,
            overlap_spans=overlap_spans,
        )

        report("¡Transcripción completada!", 100)
        return {
            "turns": turns,
            "speakers": speakers,
            "warning": " ".join(warning_messages) if warning_messages else None,
        }
