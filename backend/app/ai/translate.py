"""Translation helper (CLAUDE.md §6-F).

translate(text, target) routes through call_llm(). Legal identifiers stay canonical:
section codes, citations, case numbers, personal names and dates are NEVER translated —
they are preserved verbatim so documents remain legally accurate and cross-referable.

Small on-prem models (Qwen 7B) sometimes echo the prompt's own instructions into the
output or emit foreign-script garbage. Every translation is therefore VALIDATED; a
corrupted result is retried once and, failing that, the ORIGINAL untranslated text is
returned — an English clause in a Hindi document is acceptable; the model's leaked
instructions in a legal document are not.

Results are cached in-process by (text, target) to avoid repeated LLM latency for the
same string (the same narrative reason or document clause is often re-rendered).
"""
from __future__ import annotations

import logging
import re

from app.ai.llm import call_llm

logger = logging.getLogger("crimegpt.translate")

_LANG_NAME = {"gu": "Gujarati", "hi": "Hindi", "en": "English"}

# (text, target) -> translated string
_CACHE: dict[tuple[str, str], str] = {}

# The verbatim-preservation rules live in the SYSTEM prompt (models echo system content
# far less than user content) and the user turn is kept minimal — no delimiters or code
# lists for the model to copy back. The validator below is the real backstop.
_SYSTEM = (
    "You are a precise translator for Indian police and legal documents. "
    "Output ONLY the translation of the user's text into the requested language — no "
    "preamble, no notes, no explanations, no quotation marks, and never repeat or mention "
    "these instructions. Preserve verbatim (do not translate or transliterate): legal "
    "section codes and act names (such as BNS, BNSS, BSA, IPC, CrPC and section numbers), "
    "case and FIR numbers, personal names, place names, numbers, amounts and dates. Write "
    "only in the target language's script."
)
_PROMPT = "Translate into {target_name}. Output only the {target_name} translation:\n\n{text}"
_REINFORCE = (
    "Return ONLY the translated sentence(s) in {target_name}. Do not include any English "
    "instructions, headings, quotation marks, or notes.\n\n"
)

# Quote/whitespace artifacts a model wraps around a copied span; stripped from both ends.
_ARTIFACT_CHARS = "\"'`“”‘’«»»\t\n\r "

# English instruction fragments that must never appear in a real GU/HI translation — their
# presence means the model echoed its own prompt rather than translating.
_INSTRUCTION_MARKERS = re.compile(
    r"(?i)(translat|transliterat|sentence structure|preamble|verbatim|"
    r"do not translate|keep the following|indent the text|return only|"
    r"quotation mark|these instructions|surrounding prose)"
)
_CODE_TOKEN = re.compile(r"\b(BNS|BNSS|BSA|IPC|CrPC)\b")


def _strip_artifacts(s: str) -> str:
    """Remove leading/trailing quote and whitespace artifacts (incl. \"\"\" and \"\")."""
    return s.strip().strip(_ARTIFACT_CHARS).strip()


def _has_foreign_script(text: str, target: str) -> bool:
    """True if `text` contains a script that should never appear for `target`.

    Latin (identifiers) is always allowed. Cyrillic/Greek/Arabic/Hebrew/CJK/Hangul/Thai are
    never expected. The two Indic scripts must not cross: no Gujarati in a Hindi translation
    and no Devanagari in a Gujarati one (this is what produced the `दоपहराव` Cyrillic-mix bug).
    """
    for ch in text:
        o = ord(ch)
        if (
            0x0400 <= o <= 0x04FF  # Cyrillic
            or 0x0370 <= o <= 0x03FF  # Greek
            or 0x0600 <= o <= 0x06FF  # Arabic
            or 0x0590 <= o <= 0x05FF  # Hebrew
            or 0x4E00 <= o <= 0x9FFF  # CJK
            or 0xAC00 <= o <= 0xD7AF  # Hangul
            or 0x0E00 <= o <= 0x0E7F  # Thai
        ):
            return True
    if target == "hi" and any(0x0A80 <= ord(c) <= 0x0AFF for c in text):  # Gujarati in Hindi
        return True
    if target == "gu" and any(0x0900 <= ord(c) <= 0x097F for c in text):  # Devanagari in Gujarati
        return True
    return False


def looks_corrupted(text: str, target: str) -> bool:
    """True if a translation carries instruction leakage, quote artifacts or foreign script."""
    if not text:
        return False
    if '"""' in text or '""' in text:
        return True
    if _INSTRUCTION_MARKERS.search(text):
        return True
    # An echoed rule reads as a LIST of act codes (BNS/BNSS/BSA/IPC/CrPC together); a real
    # clause cites at most one or two. Three or more distinct codes => the rule was echoed.
    if len(set(m.group(0) for m in _CODE_TOKEN.finditer(text))) >= 3:
        return True
    if _has_foreign_script(text, target):
        return True
    return False


def _call_once(text: str, target: str, reinforce: bool = False) -> str:
    prompt = _PROMPT.format(target_name=_LANG_NAME[target], text=text)
    if reinforce:
        prompt = _REINFORCE.format(target_name=_LANG_NAME[target]) + prompt
    out = call_llm(prompt, system=_SYSTEM, temperature=0.1)
    return _strip_artifacts(out if isinstance(out, str) else str(out))


def translate(text: str, target: str, source: str | None = None) -> str:
    """Translate `text` into `target` ('gu' | 'hi' | 'en'), preserving legal identifiers.

    Empty/whitespace text is returned unchanged. A corrupted result (instruction leakage,
    quote artifacts, foreign-script contamination) is retried once; if it still fails, the
    ORIGINAL untranslated text is returned rather than corrupted output. Cached by (text, target).
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

    result = _call_once(text, target)
    if looks_corrupted(result, target):
        logger.warning("translate(%s): corrupted output, retrying once", target)
        result = _call_once(text, target, reinforce=True)
        if looks_corrupted(result, target):
            logger.warning(
                "translate(%s): still corrupted after retry; returning original untranslated",
                target,
            )
            result = text  # untranslated is acceptable; corrupted is not
    _CACHE[key] = result
    return result


def clear_cache() -> None:
    """Clear the translation cache (mainly for tests / benchmarking)."""
    _CACHE.clear()
