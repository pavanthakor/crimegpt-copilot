"""Gujarati/Hindi/English speech-to-text (CLAUDE.md §4 Tier-2 "Gujarati voice-to-document").

An officer dictates the complaint; we transcribe it and (elsewhere) translate it to
English for the case narrative.

HARD RULE — WHISPER STAYS ON THE CPU. Qwen owns the RTX 4060 (8 GB); a Whisper model
sharing that memory risks an out-of-memory kill mid-demo, which is unrecoverable on
stage. We pin device="cpu", compute_type="int8" and never touch CUDA. `_load()` asserts
the CPU placement so a future edit cannot silently move it onto the GPU.

MODEL IS CONFIGURABLE via settings.WHISPER_MODEL (CLAUDE.md §12):
    - a faster-whisper size/hub name ("small", "medium", "large-v3") -> downloaded
      from the Systran hub into storage/whisper/, OR
    - a path to a local CTranslate2 model directory (e.g. a Gujarati-tuned checkpoint
      converted with ct2-transformers-converter).
Switching models is a config change only; no code change. The model is loaded lazily
and cached in a module-level singleton keyed by the spec, so switching in a fresh
process picks up the new model and the first call pays the load cost.

QUALITY LEVERS for Indian-language audio:
    - language is PINNED (never auto-detected) so the decoder commits to the right script.
    - a short Gujarati `initial_prompt` biases the decoder toward Gujarati (U+0A80-U+0AFF)
      rather than transcribing phonetically into Devanagari.
    - task="translate" uses Whisper's own speech->English path, as an alternative to
      transcribe-then-LLM-translate.
"""
from __future__ import annotations

import logging
import math
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("crimegpt.transcribe")

# app/ai/transcribe.py -> parents[1] = app
_APP_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = _APP_DIR / "storage" / "whisper"
SUPPORTED_LANGS = ("gu", "hi", "en")
TASKS = ("transcribe", "translate")

# A short, realistic complaint sentence in Gujarati script. Whisper conditions on the
# initial_prompt's script/vocabulary, so this nudges it to emit Gujarati rather than the
# Devanagari it otherwise drifts to for Gujarati speech. ("My complaint is that a theft
# occurred at my house at night.")
GUJARATI_PROMPT = "મારી ફરિયાદ છે કે રાત્રે મારા ઘરમાં ચોરી થઈ છે."
_INITIAL_PROMPT = {"gu": GUJARATI_PROMPT}


class TranscriptionError(RuntimeError):
    """Raised when transcription cannot produce text — never returned silently."""


def _model_spec() -> str:
    """The configured model reference (a size/hub name or a local CT2 path)."""
    return settings.WHISPER_MODEL or "small"


def _is_local_path(spec: str) -> bool:
    return Path(spec).exists()


@lru_cache(maxsize=2)
def _load(spec: str):
    """Load a faster-whisper model on CPU (int8), cached per spec for the process life.

    `spec` is a size/hub name (downloaded into MODEL_DIR) or a local CT2 directory.
    Kept in its own function so the singleton is warm across requests and the CPU-only
    guarantee lives in exactly one place.
    """
    from faster_whisper import WhisperModel

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    local = _is_local_path(spec)
    logger.info("loading faster-whisper %r on CPU (int8)%s", spec,
                "" if local else f" (hub -> {MODEL_DIR})")
    kwargs = dict(device="cpu", compute_type="int8")  # NEVER "cuda" — Qwen owns the GPU
    if not local:
        kwargs["download_root"] = str(MODEL_DIR)
    model = WhisperModel(spec, **kwargs)

    # Fail loudly if a future edit moves this onto the GPU. faster-whisper exposes the
    # real placement on the inner CTranslate2 model (WhisperModel has no .device).
    device = getattr(getattr(model, "model", None), "device", "cpu")
    if device != "cpu":
        raise RuntimeError(
            f"Whisper must stay on CPU; got device={device!r}. The GPU is reserved for Qwen."
        )
    logger.info("faster-whisper %r ready on %s", spec, device)
    return model


def _model():
    """The active model for the current settings.WHISPER_MODEL."""
    return _load(_model_spec())


def warm_up() -> None:
    """Force the singleton to load now (e.g. at startup) rather than on first request."""
    _model()


def model_present() -> tuple[bool, str]:
    """Are the configured model's weights on disk? Checked WITHOUT a network call.

    Handles both a local CT2 path and a hub name (whose model.bin lands under MODEL_DIR).
    Returns (present, detail) for preflight.
    """
    try:
        import faster_whisper  # noqa: F401
    except ImportError as exc:
        return False, f"faster-whisper not importable: {exc}"

    spec = _model_spec()
    if _is_local_path(spec):
        bins = list(Path(spec).glob("**/model.bin"))
        search = spec
    else:
        # Hub name -> the HF cache dir is models--<org>--faster-whisper-<spec>. Scope the
        # search to that subtree so a different model.bin under MODEL_DIR (e.g. medium
        # sitting next to small) is not mistaken for this one.
        matches = [p for p in MODEL_DIR.glob(f"models--*{spec}*") if p.is_dir()]
        base = matches[0] if matches else MODEL_DIR
        bins = list(base.glob("**/model.bin"))
        search = str(base)

    for b in bins:
        try:
            size_mb = b.stat().st_size // (1024 * 1024)  # follows the HF symlink
        except OSError:
            continue
        if size_mb > 50:  # a real Whisper model.bin is hundreds of MB; guards against a stub
            return True, f"{spec!r} model.bin present ({size_mb} MB) at {search}"
    return False, (
        f"{spec!r} weights missing under {search} — "
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


def transcribe(audio_path: str, language: str = "gu", task: str = "transcribe") -> dict:
    """Transcribe (or directly translate) an audio file.

    Args:
        audio_path: path to an audio file (wav/mp3/m4a/ogg/… — decoded via PyAV).
        language: SOURCE language of the speech, one of 'gu' | 'hi' | 'en'. Pinned —
            never auto-detected.
        task: 'transcribe' -> text in the source script; 'translate' -> Whisper's own
            speech-to-English (only meaningful for non-English source).

    Returns:
        {text, language, task, duration, confidence, model}

    Raises:
        ValueError: unsupported language/task or missing file.
        TranscriptionError: decoding failed, or no speech was recognised. Never
            returns a silent empty string — an empty result is an error the caller
            must surface so the officer knows to re-record.
    """
    language = (language or "gu").lower()
    if language not in SUPPORTED_LANGS:
        raise ValueError(
            f"Unsupported language {language!r}; expected one of {SUPPORTED_LANGS}"
        )
    task = (task or "transcribe").lower()
    if task not in TASKS:
        raise ValueError(f"Unsupported task {task!r}; expected one of {TASKS}")
    path = Path(audio_path)
    if not path.exists():
        raise ValueError(f"Audio file not found: {audio_path}")

    # Bias the decoder toward the source script (only for transcribe; a Gujarati prompt
    # would not help an English translation target).
    initial_prompt = _INITIAL_PROMPT.get(language) if task == "transcribe" else None

    try:
        segments_gen, info = _model().transcribe(
            str(path),
            language=language,        # PINNED, no auto-detect
            task=task,
            initial_prompt=initial_prompt,
            beam_size=5,
            vad_filter=True,          # drop leading/trailing silence -> steadier confidence
            # Anti-runaway guards. An initial_prompt on poor audio can send the decoder
            # into a repetition loop (observed: 48s+ of "છે છે છે…"). These bound it
            # without changing behaviour on clean audio.
            no_repeat_ngram_size=3,
            condition_on_previous_text=False,
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
        "task": task,
        "duration": round(float(getattr(info, "duration", 0.0) or 0.0), 2),
        "confidence": _confidence(segments),
        "model": _model_spec(),
    }
