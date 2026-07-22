"""Runtime-mutable application state that overrides startup env defaults.

DEMO_MODE starts from `settings.DEMO_MODE` (the env var, the startup default) but can be
toggled at runtime via the system API (SHO only) with no backend restart. The value is
held in module state so every reader — analyze, document generation, transcription — sees
one authoritative value on the very next request.

Single-process assumption: fine for the on-prem demo box (one uvicorn worker). With
multiple workers the toggle would only affect the worker that served the PATCH; run a
single worker for the demo.
"""
from app.core.config import settings

_demo_mode: bool = settings.DEMO_MODE


def get_demo_mode() -> bool:
    """The effective DEMO_MODE right now (runtime override, else the startup default)."""
    return _demo_mode


def set_demo_mode(value: bool) -> bool:
    """Set DEMO_MODE for all subsequent requests; returns the new value."""
    global _demo_mode
    _demo_mode = bool(value)
    return _demo_mode
