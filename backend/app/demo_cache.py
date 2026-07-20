"""Demo-mode output cache (CLAUDE.md §6 "DEMO_MODE + demo_cache/", §16 fallbacks).

When settings.DEMO_MODE is true, the analyze and document pipelines serve pre-generated
outputs from `backend/demo_cache/` and skip the LLM entirely, so a live GPU stall never
breaks the demo. A cache MISS is not an error — callers fall through to the live pipeline.

Cached outputs are plain, indented JSON (ensure_ascii=False) so the machine-translated
Gujarati/Hindi can be hand-corrected before the demo. Keys:
    documents:  demo_cache/documents/{case_id}_{DOC_TYPE}_{lang}.json  -> merged context dict
    analysis:   demo_cache/analysis/{case_id}_{lang}.json              -> {status, sections, rejected}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("crimegpt.demo_cache")

# demo_cache.py -> parents[1] = backend
DEMO_CACHE_DIR = Path(__file__).resolve().parents[1] / "demo_cache"
_DOC_DIR = DEMO_CACHE_DIR / "documents"
_ANALYSIS_DIR = DEMO_CACHE_DIR / "analysis"
_TRANSCRIPT_DIR = DEMO_CACHE_DIR / "transcripts"


def _norm(lang: str | None) -> str:
    return (lang or "en").lower()


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:  # corrupt/edited file -> treat as miss
        logger.warning("demo_cache: could not read %s (%s)", path.name, exc)
        return None


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _doc_path(case_id: int, doc_type: str, lang: str) -> Path:
    return _DOC_DIR / f"{case_id}_{doc_type}_{_norm(lang)}.json"


def _analysis_path(case_id: int, lang: str) -> Path:
    return _ANALYSIS_DIR / f"{case_id}_{_norm(lang)}.json"


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
def load_document(case_id: int, doc_type: str, lang: str) -> dict | None:
    """Return the cached merged context for a document, or None on miss."""
    data = _read(_doc_path(case_id, doc_type, lang))
    logger.info(
        "demo_cache document %s: case=%s type=%s lang=%s",
        "HIT" if data is not None else "MISS", case_id, doc_type, _norm(lang),
    )
    return data


def save_document(case_id: int, doc_type: str, lang: str, context: dict) -> Path:
    path = _doc_path(case_id, doc_type, lang)
    _write(path, context)
    return path


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def load_analysis(case_id: int, lang: str) -> dict | None:
    """Return the cached {status, sections, rejected}, or None on miss."""
    data = _read(_analysis_path(case_id, lang))
    logger.info(
        "demo_cache analysis %s: case=%s lang=%s",
        "HIT" if data is not None else "MISS", case_id, _norm(lang),
    )
    return data


def save_analysis(case_id: int, lang: str, payload: dict) -> Path:
    path = _analysis_path(case_id, lang)
    _write(path, payload)
    return path


# ---------------------------------------------------------------------------
# Transcripts — keyed by the uploaded audio's filename, so the demo has a
# sub-second fallback when the GPU/CPU is busy or Whisper is slow on stage.
# ---------------------------------------------------------------------------
def _transcript_path(audio_filename: str) -> Path:
    # Key on the basename only, so the same clip resolves regardless of upload path.
    return _TRANSCRIPT_DIR / f"{Path(audio_filename).name}.json"


def load_transcript(audio_filename: str) -> dict | None:
    """Return the cached {transcript, language, translation, duration, confidence}, or None."""
    data = _read(_transcript_path(audio_filename))
    logger.info(
        "demo_cache transcript %s: file=%s",
        "HIT" if data is not None else "MISS", Path(audio_filename).name,
    )
    return data


def save_transcript(audio_filename: str, payload: dict) -> Path:
    path = _transcript_path(audio_filename)
    _write(path, payload)
    return path
