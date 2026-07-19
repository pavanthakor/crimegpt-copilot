"""Cross-document consistency + staleness check (CLAUDE.md §6 schema E, §7 documents).

Pure comparison over ``documents.generated_data`` — the exact context that was merged
into each document at generation time. **No LLM call.** Two independent checks:

  STALENESS  — a document's snapshot vs the CURRENT pool state (accused renamed, item
               added/removed, sections accepted/rejected since the document was generated).
  DIVERGENCE — the same field holding different values across two or more documents.

Severity: ``high`` for identity / section / date mismatches, ``low`` for formatting-only
differences (same value modulo whitespace/case).

The current pool snapshot is produced by the very same ``_build_context`` the generator
uses, so a "match" is an exact, format-for-format match rather than an approximation.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Case, Document, User
from app.services.documents import _build_context

# (field, base severity, kind).  kind: "scalar" | "sections" | "items".
_STALENESS_FIELDS = [
    ("accused_name", "high", "scalar"),
    ("fir_number", "high", "scalar"),
    ("fir_date", "high", "scalar"),
    ("police_station", "high", "scalar"),
    ("incident_datetime", "high", "scalar"),
    ("sections_applied", "high", "sections"),
    ("seized_items", "high", "items"),
]
_DIVERGENCE_FIELDS = [
    ("accused_name", "high", "scalar"),
    ("case_number", "high", "scalar"),
    ("fir_number", "high", "scalar"),
    ("police_station", "high", "scalar"),
    ("fir_date", "high", "scalar"),
    ("incident_datetime", "high", "scalar"),
    ("seizure_datetime", "high", "scalar"),
    ("sections_applied", "high", "sections"),
]

_POOL_KEY = "current_pool"


def _norm(value):
    """Formatting-insensitive form of a scalar (collapsed whitespace, case-folded)."""
    return " ".join(str(value).split()).casefold() if value is not None else None


def _key(value, kind):
    """Comparison key: identity for lists, formatting-insensitive for scalars."""
    if kind == "sections":
        return frozenset((s.get("act"), str(s.get("section_code"))) for s in (value or []))
    if kind == "items":
        return frozenset((s.get("description"), s.get("quantity")) for s in (value or []))
    return _norm(value)


def _display(value, kind):
    """Human-readable value for the ``values`` map."""
    if kind == "sections":
        return ", ".join(f"{s.get('act')} {s.get('section_code')}" for s in value) if value else "(none)"
    if kind == "items":
        return ", ".join(f"{s.get('description')} (x{s.get('quantity')})" for s in value) if value else "(none)"
    return value


def _doc_type(doc: Document) -> str:
    return doc.doc_type.value if hasattr(doc.doc_type, "value") else str(doc.doc_type)


def _label(doc: Document, existing: dict) -> str:
    """Key for a document in a ``values`` map; disambiguate duplicate doc types by id."""
    base = _doc_type(doc)
    return base if base not in existing else f"{base}#{doc.id}"


def _differs(a, b, kind) -> bool:
    if kind in ("sections", "items"):
        return _key(a, kind) != _key(b, kind)
    return a != b  # scalar: exact, so formatting differences are surfaced (as low)


def _scalar_severity(a, b, base) -> str:
    """Downgrade to 'low' when two scalars differ only by formatting."""
    if a is not None and b is not None and _norm(a) == _norm(b):
        return "low"
    return base


def _staleness(docs: list[Document], current: dict, out: list[dict]) -> None:
    for field, base, kind in _STALENESS_FIELDS:
        cur = current.get(field)
        stale = [d for d in docs if _differs(d.generated_data.get(field), cur, kind)]
        if not stale:
            continue
        values: dict = {}
        severity = "low"
        for d in stale:
            snap = d.generated_data.get(field)
            values[_label(d, values)] = _display(snap, kind)
            sev = _scalar_severity(snap, cur, base) if kind == "scalar" else base
            if sev == "high":
                severity = "high"
        values[_POOL_KEY] = _display(cur, kind)
        out.append(
            {
                "field": field,
                "severity": severity,
                "values": values,
                "note": (
                    f"{len(stale)} document(s) generated before the pool changed; the "
                    f"snapshot no longer matches the current pool value."
                ),
            }
        )


def _divergence(docs: list[Document], out: list[dict]) -> None:
    for field, base, kind in _DIVERGENCE_FIELDS:
        present = [(d, d.generated_data.get(field)) for d in docs]
        if kind == "scalar":
            present = [(d, v) for d, v in present if v is not None and v != ""]
            if len({v for _, v in present}) < 2:
                continue  # all agree (or <2 docs carry the field)
            severity = base if len({_norm(v) for _, v in present}) > 1 else "low"
        else:
            if len({_key(v, kind) for _, v in present}) < 2:
                continue
            severity = base
        values: dict = {}
        for d, v in present:
            values[_label(d, values)] = _display(v, kind)
        out.append(
            {
                "field": field,
                "severity": severity,
                "values": values,
                "note": "The same field holds different values across documents.",
            }
        )


def check_consistency(db: Session, case: Case, user: User) -> dict:
    """Compare every generated document of ``case`` against the pool and each other.

    Returns ``{inconsistencies, checked_documents, status}`` where status is
    ``"issues_found"`` if any inconsistency was detected, else ``"ok"``. High-severity
    findings are listed first.
    """
    docs = [
        d
        for d in db.query(Document)
        .filter(Document.case_id == case.id)
        .order_by(Document.id)
        .all()
        if d.generated_data
    ]

    inconsistencies: list[dict] = []
    if docs:
        current = _build_context(db, case, user)
        _staleness(docs, current, inconsistencies)
        _divergence(docs, inconsistencies)
    inconsistencies.sort(key=lambda i: 0 if i["severity"] == "high" else 1)

    return {
        "inconsistencies": inconsistencies,
        "checked_documents": len(docs),
        "status": "issues_found" if inconsistencies else "ok",
    }
