"""Grounded weak-charge alerts (CLAUDE.md §6-C, §4 "weak-charge / missing-ingredient").

For each ACCEPTED section on a case, decide whether the offence's ingredients are
actually established by the material on file. Same grounding discipline as section
mapping (app.ai.legal) and judgment suggestion (app.ai.judgments):

    1. Fetch the section's REAL statutory text from the corpus by (act, code) — never
       rely on the model recalling what the section says.
    2. Assemble the case material: narrative + statements + seized items + evidence.
    3. Prompt C, per section: the model may only QUOTE ingredient spans from the
       statute and supporting spans from the material.
    4. HARD-VALIDATE mechanically: drop any ingredient not found verbatim in the
       statutory text; treat any supporting quote not found verbatim in the material
       as unsupported. Every drop is logged and returned in `rejected`.

Only ACCEPTED sections are examined, and only sections whose statutory text we hold —
a charge we cannot ground is reported, never guessed at.

This module is read-only: it computes and returns, it does not persist anything.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.ai import rag
from app.ai.judgments import extract_verbatim
from app.ai.llm import call_llm
from app.ai.prompts import WEAK_CHARGE_PROMPT, WEAK_CHARGE_SCHEMA
from app.models import Case, Evidence, LegalSection, SeizedItem, Statement
from app.models.enums import SectionStatus

logger = logging.getLogger("crimegpt.weak_charge")

_SYSTEM = (
    "You are a meticulous legal reviewer for Indian police. You never invent a legal "
    "element or a piece of evidence; you only quote the texts you are given."
)


# ---------------------------------------------------------------------------
# Case material — the single body of fact every ingredient is checked against
# ---------------------------------------------------------------------------
def build_case_material(db: Session, case: Case) -> str:
    """Concatenate everything on the case file into one quotable block.

    Narrative + recorded statements + seized-item descriptions + evidence
    descriptions. This is the ONLY source a supporting quote may come from, so it
    must contain every fact the charge could rely on.
    """
    parts: list[str] = []
    if case.complaint_narrative:
        parts.append(case.complaint_narrative)

    for st in db.query(Statement).filter(Statement.case_id == case.id).order_by(Statement.id):
        if st.statement_text:
            parts.append(st.statement_text)

    for it in db.query(SeizedItem).filter(SeizedItem.case_id == case.id).order_by(SeizedItem.id):
        if it.description:
            parts.append(f"Seized item: {it.description}")

    for ev in db.query(Evidence).filter(Evidence.case_id == case.id).order_by(Evidence.id):
        if ev.description:
            parts.append(f"Evidence: {ev.description}")

    return "\n\n".join(p for p in parts if p and p.strip())


# ---------------------------------------------------------------------------
# Per-section grounded check — pure given the LLM output, so unit-testable
# ---------------------------------------------------------------------------
def validate_ingredients(
    llm_out: dict, statute_text: str, material: str
) -> tuple[list[dict], list[str], list[dict]]:
    """Split the model's ingredients into (supported, missing, rejected).

    - supported: [{ingredient, evidence_quote}] — ingredient found verbatim in the
      statute AND its supporting quote found verbatim in the material.
    - missing:   [ingredient] — found verbatim in the statute but not supported (no
      quote, or a quote that is not in the material).
    - rejected:  [{ingredient, rejection_reason}] — not found in the statute at all
      (the model invented it); never shown to the officer as a real element.

    Ingredient and evidence text are re-extracted from their SOURCES, so what the
    caller gets is statutory/material text, not the model's transcription of it.
    """
    supported: list[dict] = []
    missing: list[str] = []
    rejected: list[dict] = []
    seen: set[str] = set()

    for item in llm_out.get("ingredients", []):
        raw_ingredient = (item.get("ingredient") or "").strip()
        grounded = extract_verbatim(raw_ingredient, statute_text)

        if not grounded:
            logger.warning(
                "REJECT ungrounded ingredient %r — not in statutory text", raw_ingredient
            )
            rejected.append(
                {
                    "ingredient": raw_ingredient,
                    "rejection_reason": "not found verbatim in the statutory text (invented)",
                }
            )
            continue

        key = grounded.lower()
        if key in seen:
            continue
        seen.add(key)

        quote = extract_verbatim(item.get("evidence_quote", ""), material)
        if item.get("supported") and quote:
            supported.append({"ingredient": grounded, "evidence_quote": quote})
        else:
            # Claimed supported but quote absent/unverifiable -> treat as NOT supported.
            if item.get("supported") and not quote:
                logger.info(
                    "ingredient %r claimed supported but quote not in material -> missing",
                    grounded,
                )
            missing.append(grounded)

    return supported, missing, rejected


def check_section(section: LegalSection, material: str) -> dict | None:
    """Run the grounded weak-charge check for one ACCEPTED section.

    Returns an alert dict if the section has any missing ingredient (or None of its
    ingredients could be grounded), else None. Returns None and logs if the section's
    statutory text is not in the corpus (cannot ground -> do not guess).
    """
    record = rag.get_section(section.act.value, section.section_code)
    if record is None or not record.get("text"):
        logger.warning(
            "no statutory text for %s %s — skipping weak-charge check",
            section.act.value, section.section_code,
        )
        return {
            "section_code": section.section_code,
            "citation": None,
            "missing_ingredients": [],
            "supported_ingredients": [],
            "severity": "low",
            "suggestion": None,
            "note": "statutory text not found in corpus; cannot assess ingredients",
            "rejected": [],
        }

    statute_text = record["text"]
    prompt = WEAK_CHARGE_PROMPT.format(
        act=section.act.value,
        section_code=section.section_code,
        title=record.get("title", ""),
        statute=statute_text,
        material=material,
    )
    llm_out = call_llm(prompt, system=_SYSTEM, json_schema=WEAK_CHARGE_SCHEMA)
    if not isinstance(llm_out, dict):
        raise ValueError(f"expected dict from call_llm, got {type(llm_out)}")

    supported, missing, rejected = validate_ingredients(llm_out, statute_text, material)
    logger.info(
        "%s %s: %d supported, %d missing, %d rejected ingredient(s)",
        section.act.value, section.section_code, len(supported), len(missing), len(rejected),
    )

    if not missing:
        return None  # fully supported (or nothing to flag) -> no alert

    # Severity: a charge with NO supported ingredient is high risk; otherwise low.
    severity = "high" if not supported else "low"
    suggestion = (llm_out.get("suggestion") or "").strip() or None
    return {
        "section_code": section.section_code,
        "citation": record.get("citation") or f"{section.act.value} {section.section_code}",
        "missing_ingredients": missing,
        "supported_ingredients": supported,
        "severity": severity,
        "suggestion": suggestion,
        "rejected": rejected,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def check_weak_charges(db: Session, case: Case) -> dict:
    """Weak-charge review of every ACCEPTED section on `case`.

    Returns:
        {
          "alerts": [ { section_code, citation, missing_ingredients,
                        supported_ingredients: [{ingredient, evidence_quote}],
                        severity, suggestion } ],
          "status": "ok" | "no_issues",
          "rejected": [ { section_code, ingredient, rejection_reason } ],
        }
    `status == "no_issues"` means every accepted charge is fully grounded in the material.
    """
    accepted = (
        db.query(LegalSection)
        .filter(
            LegalSection.case_id == case.id,
            LegalSection.status == SectionStatus.ACCEPTED,
        )
        .order_by(LegalSection.id)
        .all()
    )
    material = build_case_material(db, case)

    alerts: list[dict] = []
    rejected: list[dict] = []
    for section in accepted:
        alert = check_section(section, material)
        if alert is None:
            continue
        for r in alert.pop("rejected", []):
            rejected.append({"section_code": section.section_code, **r})
        alerts.append(alert)

    return {
        "alerts": alerts,
        "status": "ok" if alerts else "no_issues",
        "rejected": rejected,
    }
