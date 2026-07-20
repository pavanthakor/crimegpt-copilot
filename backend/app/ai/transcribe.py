"""Gujarati/Hindi/English speech-to-text (CLAUDE.md §4 Tier-2 "Gujarati voice-to-document").

An officer dictates the complaint; we transcribe it and (elsewhere) translate it to
English for the case narrative.

HARD RULE — WHISPER STAYS ON THE CPU. Qwen owns the RTX 4060 (8 GB); a Whisper model
sharing that memory risks an out-of-memory kill mid-demo, which is unrecoverable on
stage. faster-whisper "small" at int8 runs comfortably on CPU in a few seconds, so we
pin device="cpu", compute_type="int8" and never touch CUDA. `_model()` asserts the CPU
placement so a future edit cannot silently move it onto the GPU.

The model is loaded lazily and cached in a module-level singleton (first call pays the
load cost, ~1-2 s; later calls reuse it). Weights live under storage/whisper/ so the set
is self-contained and preflight can verify their presence without a network call.
"""
from __future__ import annotations

import logging
import math
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("crimegpt.transcribe")

# app/ai/transcribe.py -> parents[1] = app
_APP_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = _APP_DIR / "storage" / "whisper"
MODEL_SIZE = "small"
SUPPORTED_LANGS = ("gu", "hi", "en")


class TranscriptionError(RuntimeError):
    """Raised when transcription cannot produce text — never returned silently."""


@lru_cache(maxsize=1)
def _model():
    """Load faster-whisper `small` on CPU (int8), cached for the process lifetime.

    Kept in its own function so the singleton is warm across requests and so the
    CPU-only guarantee lives in exactly one place.
    """
    from faster_whisper import WhisperModel

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("loading faster-whisper %r on CPU (int8) from %s", MODEL_SIZE, MODEL_DIR)
    model = WhisperModel(
        MODEL_SIZE,
        device="cpu",            # NEVER "cuda" — Qwen owns the GPU (see module docstring)
        compute_type="int8",
        download_root=str(MODEL_DIR),
    )
    # Fail loudly if a future edit moves this onto the GPU. faster-whisper exposes the
    # real placement on the inner CTranslate2 model (WhisperModel has no .device).
    device = getattr(getattr(model, "model", None), "device", "cpu")
    if device != "cpu":
        raise RuntimeError(
            f"Whisper must stay on CPU; got device={device!r}. The GPU is reserved for Qwen."
        )
    logger.info("faster-whisper %r ready on %s (%s)", MODEL_SIZE, device,
                getattr(model.model, "compute_type", "int8"))
    return model


def warm_up() -> None:
    """Force the singleton to load now (e.g. at startup) rather than on first request."""
    _model()


def model_present() -> tuple[bool, str]:
    """Are the `small` model weights on disk? Checked WITHOUT a network call.

    Returns (present, detail) for preflight. Looks for a materialised model.bin under
    MODEL_DIR (the HF cache layout is models--Systran--faster-whisper-small/…/model.bin).
    """
    try:
        import faster_whisper  # noqa: F401
    except ImportError as exc:
        return False, f"faster-whisper not importable: {exc}"

    bins = list(MODEL_DIR.glob("**/model.bin"))
    for b in bins:
        try:
            size_mb = b.stat().st_size // (1024 * 1024)  # follows the HF symlink
        except OSError:
            continue
        if size_mb > 50:  # the small model.bin is ~460 MB; guards against a stub
            return True, f"{MODEL_SIZE} model.bin present ({size_mb} MB) at {MODEL_DIR}"
    return False, (
        f"{MODEL_SIZE} weights missing under {MODEL_DIR} — "
        "run: python -c \"from app.ai.transcribe import warm_up; warm_up()\""
    )


def _confidence(segments: list) -> float | None:
    """A 0-1 confidence proxy from segment average log-probabilities.

    Whisper reports avg_logprob per segment; exp() maps it to a probability-like
    value. We average across segments, duration-weighted so a long confident stretch
    is not outweighed by a short uncertain one. None if no usable segments.
    """
    weighted, total = 0.0, 0.0
    for s in segments:
        lp = getattr(s, "avg_logprob", None)
        if lp is None:
            continue
        dur = max((getattr(s, "end", 0.0) or 0.0) - (getattr(s, "start", 0.0) or 0.0), 0.01)
        weighted += math.exp(lp) * dur
        total += dur
    if total == 0.0:
        return None
    return round(min(max(weighted / total, 0.0), 1.0), 3)


def transcribe(audio_path: str, language: str = "gu") -> dict:
    """Transcribe an audio file.

    Args:
        audio_path: path to an audio file (wav/mp3/m4a/ogg/… — decoded via PyAV).
        language: one of 'gu' | 'hi' | 'en'.

    Returns:
        {text, language, duration, confidence}

    Raises:
        ValueError: unsupported language or missing file.
        TranscriptionError: decoding failed, or no speech was recognised. Never
            returns a silent empty string — an empty result is an error the caller
            must surface so the officer knows to re-record.
    """
    language = (language or "gu").lower()
    if language not in SUPPORTED_LANGS:
        raise ValueError(
            f"Unsupported language {language!r}; expected one of {SUPPORTED_LANGS}"
        )
    path = Path(audio_path)
    if not path.exists():
        raise ValueError(f"Audio file not found: {audio_path}")

    try:
        segments_gen, info = _model().transcribe(
            str(path),
            language=language,
            beam_size=5,
            vad_filter=True,  # drop leading/trailing silence -> steadier confidence
        )
        segments = list(segments_gen)  # generator -> materialise (also surfaces decode errors)
    except TranscriptionError:
        raise
    except Exception as exc:  # noqa: BLE001 — decode/model failure -> clear error, never silent
        logger.exception("transcription failed for %s", path.name)
        raise TranscriptionError(f"Could not transcribe {path.name}: {exc}") from exc

    text = " ".join(s.text.strip() for s in segments if s.text and s.text.strip()).strip()
    if not text:
        raise TranscriptionError(
            f"No speech recognised in {path.name}. Re-record with clearer audio."
        )

    return {
        "text": text,
        "language": getattr(info, "language", language) or language,
        "duration": round(float(getattr(info, "duration", 0.0) or 0.0), 2),
        "confidence": _confidence(segments),
    }
