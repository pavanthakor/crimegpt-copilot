"""call_llm() — the single choke point for every LLM call in CrimeGPT (CLAUDE.md §6).

Routes to Ollama by default; falls back to an API provider on Ollama failure or when
FORCE_API is set. In json mode it appends a strict "JSON only" instruction, strips
markdown fences, parses the result, and retries once on bad JSON. Every call logs its
elapsed wall-clock time so we can plan demo latency.

Feature code must NEVER call Ollama / an API directly — always go through call_llm().
"""
from __future__ import annotations

import json
import logging
import re
import time

import requests

from app.core.config import settings

logger = logging.getLogger("crimegpt.llm")

# Ollama can be slow to first-token on an 8GB card; give it room.
_OLLAMA_TIMEOUT = 180
_JSON_INSTRUCTION = "Return ONLY valid JSON matching this schema, no prose."

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _strip_fences(text: str) -> str:
    """Remove a leading/trailing ```json ... ``` markdown fence if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # drop opening fence line and trailing fence
        stripped = _FENCE_RE.sub("", stripped)
        # a trailing fence on its own line may remain after the opener sub
        stripped = re.sub(r"\s*```\s*$", "", stripped).strip()
    return stripped


def _parse_json(text: str) -> dict:
    """Strip fences and parse. Raises json.JSONDecodeError on failure."""
    return json.loads(_strip_fences(text))


def _build_prompt(prompt: str, system: str, json_schema: dict | None) -> str:
    """Assemble the final prompt string, appending schema + JSON instruction in json mode."""
    parts = []
    if system:
        parts.append(system.strip())
    parts.append(prompt.strip())
    if json_schema is not None:
        parts.append(
            f"{_JSON_INSTRUCTION}\nSchema:\n{json.dumps(json_schema, indent=2, ensure_ascii=False)}"
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
def _ollama_generate(full_prompt: str, temperature: float, max_tokens: int | None = None) -> str:
    """POST to Ollama /api/generate (non-streaming). Returns the raw response text."""
    options = {"temperature": temperature}
    if max_tokens is not None:
        options["num_predict"] = max_tokens
    resp = requests.post(
        f"{settings.OLLAMA_HOST}/api/generate",
        json={
            "model": settings.LLM_MODEL,
            "prompt": full_prompt,
            "stream": False,
            "options": options,
        },
        timeout=_OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["response"]


def _api_generate(full_prompt: str, temperature: float, max_tokens: int | None = None) -> str:
    """Fallback API provider. Stubbed cleanly: routing is intact, but with no key
    configured it raises a clear error instead of pretending to work."""
    if not settings.FALLBACK_API_KEY:
        raise RuntimeError(
            "API fallback requested but FALLBACK_API_KEY is not set. "
            "Configure a key in backend/.env or run against Ollama."
        )
    # Real API wiring goes here (e.g. an OpenAI-compatible endpoint). Kept as a stub
    # so no feature code depends on an unfinished provider during the hackathon.
    raise NotImplementedError(
        "API fallback provider is stubbed. Add the HTTP call here when a key is available."
    )


def _generate(full_prompt: str, temperature: float, provider: str, max_tokens: int | None = None) -> str:
    if provider == "api":
        return _api_generate(full_prompt, temperature, max_tokens)
    return _ollama_generate(full_prompt, temperature, max_tokens)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def call_llm(
    prompt: str,
    system: str = "",
    json_schema: dict | None = None,
    temperature: float = 0.2,
    provider: str = "ollama",
    max_tokens: int | None = None,
) -> dict | str:
    """Single entrypoint for all LLM use.

    Args:
        prompt: the user prompt (already formatted with case data).
        system: optional system framing prepended to the prompt.
        json_schema: if set, response MUST parse as JSON; returns a dict.
        temperature: sampling temperature.
        provider: "ollama" (default) or "api" (fallback).
        max_tokens: hard ceiling on generated tokens. A RUNAWAY GUARD, not a tuning
            knob — size it well above the largest legitimate response. Cutting a JSON
            reply short makes it unparseable, which costs a whole extra fix-up round
            trip and is slower than not capping at all. Default None = uncapped, so
            every existing caller is unaffected.

    Returns:
        dict when json_schema is set, otherwise the raw string.
    """
    # FORCE_API overrides the requested provider entirely.
    active = "api" if settings.FORCE_API else provider

    full_prompt = _build_prompt(prompt, system, json_schema)

    started = time.perf_counter()
    try:
        raw = _generate(full_prompt, temperature, active, max_tokens)
    except Exception as exc:  # noqa: BLE001 — deliberately broad; we want a clean fallback
        elapsed = time.perf_counter() - started
        if active == "ollama":
            logger.warning(
                "call_llm ollama failed after %.2fs (%s); falling back to api", elapsed, exc
            )
            fb_started = time.perf_counter()
            raw = _generate(full_prompt, temperature, "api", max_tokens)
            active = "api"
            logger.info("call_llm[api-fallback] %.2fs", time.perf_counter() - fb_started)
        else:
            logger.error("call_llm api failed after %.2fs (%s)", elapsed, exc)
            raise

    elapsed = time.perf_counter() - started
    logger.info("call_llm[%s] %.2fs (json=%s)", active, elapsed, json_schema is not None)

    if json_schema is None:
        return raw

    # JSON mode: parse, retry once on failure with a "fix the JSON" reprompt.
    try:
        return _parse_json(raw)
    except json.JSONDecodeError:
        logger.warning("call_llm[%s] bad JSON; retrying once with fix reprompt", active)
        fix_prompt = (
            "The following text was supposed to be valid JSON but is not. "
            "Fix it into valid JSON only, matching this schema. Output JSON only, no prose.\n\n"
            f"Schema:\n{json.dumps(json_schema, indent=2, ensure_ascii=False)}\n\n"
            f"Broken output:\n{raw}"
        )
        retry_started = time.perf_counter()
        raw2 = _generate(fix_prompt, temperature, active, max_tokens)
        logger.info("call_llm[%s] json-fix retry %.2fs", active, time.perf_counter() - retry_started)
        try:
            return _parse_json(raw2)
        except json.JSONDecodeError as exc:
            logger.error("call_llm[%s] JSON still invalid after retry", active)
            raise ValueError(f"LLM did not return valid JSON after retry: {exc}") from exc
