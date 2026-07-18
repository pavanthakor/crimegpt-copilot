"""Translation helper (CLAUDE.md §6-F).

translate(text, target) routes through call_llm(). Legal identifiers stay canonical:
section codes, citations, case numbers, personal names and dates are NEVER translated —
they are preserved verbatim so documents remain legally accurate and cross-referable.

Results are cached in-process by (text, target) to avoid repeated LLM latency for the
same string (the same narrative reason or document clause is often re-rendered).
"""
from __future__ import annotations

import logging

from app.ai.llm import call_llm

logger = logging.getLogger("crimegpt.translate")

_LANG_NAME = {"gu": "Gujarati", "hi": "Hindi", "en": "English"}

# (text, target) -> translated string
_CACHE: dict[tuple[str, str], str] = {}

_SYSTEM = (
    "You are a precise translator for Indian police and legal documents. "
    "You preserve legal accuracy above fluency."
)

_PROMPT = """Translate the text below into {target_name}.

STRICT RULES — keep the following VERBATIM, do not translate or transliterate them:
- legal section codes and act abbreviations (e.g. BNS, BNSS, BSA, IPC, CrPC, "Section 305")
- citations and case numbers (e.g. I-CR-0142-2026, FIR No. 0142/2026)
- personal names and place names
- numbers, amounts and dates (e.g. 25,000, 10/07/2026)

Translate only the surrounding prose. Return ONLY the translated text, with no preamble,
quotes, or explanation.

TEXT:
\"\"\"{text}\"\"\""""


def translate(text: str, target: str, source: str | None = None) -> str:
    """Translate `text` into `target` ('gu' | 'hi' | 'en'), preserving legal identifiers.

    Empty/whitespace text is returned unchanged. Results are cached by (text, target).
    """
    target = (target or "").lower()
    if target not in _LANG_NAME:
        raise ValueError(f"Unsupported target language {target!r}; expected gu|hi|en")
    if not text or not text.strip():
        return text

    key = (text, target)
    if key in _CACHE:
        logger.debug("translate cache hit (%s)", target)
        return _CACHE[key]

    prompt = _PROMPT.format(target_name=_LANG_NAME[target], text=text)
    out = call_llm(prompt, system=_SYSTEM, temperature=0.1)
    result = out.strip() if isinstance(out, str) else str(out).strip()
    _CACHE[key] = result
    return result


def clear_cache() -> None:
    """Clear the translation cache (mainly for tests / benchmarking)."""
    _CACHE.clear()
