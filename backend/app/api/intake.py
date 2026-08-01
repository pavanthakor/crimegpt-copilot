"""Conversational intake (CLAUDE.md §7).

    POST /api/intake/extract   officer's chat turns -> a structured pool DRAFT
    POST /api/intake/commit    the officer-confirmed draft -> a registered case

This router is an ORCHESTRATION LAYER. It re-implements nothing:

  * extraction goes through the existing `call_llm()` choke point (`app.ai.intake`);
  * creation goes through the existing pool create logic (`app.services.pool_writes`),
    the same code path `POST /api/cases`, `POST /cases/{id}/persons` and
    `POST /cases/{id}/seized-items` use — audit rows and auto diary entries included.

Two invariants the feature depends on:

  NOTHING IS WRITTEN BEFORE CONFIRMATION. /extract is a pure function: it reads the
  conversation and returns a draft. It opens no transaction and touches no table, so an
  abandoned intake leaves no draft rows and no orphans. The half-finished case lives in
  the officer's browser until they confirm it.

  CONFIRMATION IS ATOMIC. /commit builds the case, its persons and its seized items in
  ONE transaction and commits once. A failure anywhere — a duplicate case number, a bad
  person row — rolls the whole thing back, so an officer never lands on a case that is
  half-registered.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.intake import extract_draft
from app.api.auth import require_role
from app.api.pool import PersonCreate, PersonOut, SeizedItemCreate, SeizedItemOut
from app.core.db import get_db
from app.models import User
from app.models.enums import AuditAction, CaseType, Language, PersonRole, UserRole
from app.schemas.case import CaseCreate, CaseOut
from app.services import pool_writes

router = APIRouter(prefix="/api/intake", tags=["intake"])
logger = logging.getLogger("crimegpt.intake")

_WRITE_ROLES = (UserRole.IO, UserRole.SHO)
_LANG_FROM_CODE = {"en": Language.EN, "hi": Language.HI, "gu": Language.GU}


# ---------------------------------------------------------------------------
# Draft shapes. These mirror the pool schema (§5) and are the ONLY structure the
# chat can produce — there is deliberately no field for a section, charge or legal
# conclusion, so intake cannot carry one even if the model tries to emit it.
# ---------------------------------------------------------------------------
class DraftCase(BaseModel):
    # Officer-controlled (never extracted — absent from the extraction whitelist).
    case_number: str | None = None
    case_type: CaseType = CaseType.CONVENTIONAL
    complaint_language: Language | None = None
    # Extracted from the conversation, all editable before confirm.
    title: str | None = None
    fir_number: str | None = None
    fir_date: date | None = None
    police_station: str | None = None
    district: str | None = None
    incident_datetime: datetime | None = None
    incident_location: str | None = None
    complaint_narrative: str | None = None


class DraftPerson(BaseModel):
    role: PersonRole
    full_name: str | None = None
    alias: str | None = None
    father_name: str | None = None
    age: int | None = None
    gender: str | None = None
    address: str | None = None
    phone: str | None = None
    occupation: str | None = None


class DraftItem(BaseModel):
    description: str | None = None
    quantity: int | None = None
    estimated_value: float | None = None
    # A NAME, not an id — the person it was seized from does not exist yet at draft
    # time. Resolved to persons.seized_from on commit, inside the transaction.
    seized_from_name: str | None = None
    seizure_datetime: datetime | None = None
    seizure_location: str | None = None


class IntakeDraft(BaseModel):
    case: DraftCase = Field(default_factory=DraftCase)
    persons: list[DraftPerson] = []
    seized_items: list[DraftItem] = []


class ChatMessage(BaseModel):
    role: str = "officer"  # "officer" | "assistant"
    content: str


class ExtractRequest(BaseModel):
    messages: list[ChatMessage]
    lang: str = "en"


class ExtractResponse(BaseModel):
    draft: IntakeDraft
    reply: str


class CommitRequest(IntakeDraft):
    """The officer-reviewed draft, exactly as shown in the confirmation panel."""


class CommitResult(BaseModel):
    case: CaseOut
    persons: list[PersonOut]
    seized_items: list[SeizedItemOut]


# ---------------------------------------------------------------------------
# 1. Extract — pure. No DB access, no writes, no transaction.
# ---------------------------------------------------------------------------
@router.post("/extract", response_model=ExtractResponse)
def intake_extract(
    body: ExtractRequest,
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    """Read the conversation, return a structured draft for the officer to review.

    Deliberately takes no `db` dependency: the absence of a session is the mechanical
    proof that this endpoint cannot persist anything.
    """
    # An empty send is not an error the officer needs to see as a red banner — it gets
    # the same "describe the incident" answer as any other input with nothing in it.
    if not body.messages:
        empty = extract_draft([], lang=body.lang)
        return ExtractResponse(draft=IntakeDraft(), reply=empty["reply"])

    try:
        raw = extract_draft(
            [m.model_dump() for m in body.messages],
            lang=body.lang,
        )
    except ValueError as exc:
        # Bad/empty model output — the officer should retry or type it manually,
        # which is a 422, not a server fault.
        logger.warning("intake extraction failed: %s", exc)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except Exception as exc:  # noqa: BLE001 — Ollama down must be a clean message
        logger.exception("intake extraction error")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"The language model is unavailable: {exc}",
        )

    draft = IntakeDraft(
        case=DraftCase(
            complaint_language=_LANG_FROM_CODE.get((body.lang or "en").lower()),
            **raw["case"],
        ),
        persons=[DraftPerson(**p) for p in raw["persons"]],
        seized_items=[DraftItem(**i) for i in raw["seized_items"]],
    )
    return ExtractResponse(draft=draft, reply=raw["reply"])


# ---------------------------------------------------------------------------
# 2. Commit — the confirmation gate. One transaction, existing pool logic.
# ---------------------------------------------------------------------------
def _resolve_seized_from(name: str | None, by_name: dict[str, int]) -> int | None:
    """Match a seized-from NAME against the persons just created (case-insensitive)."""
    if not name:
        return None
    return by_name.get(name.strip().lower())


@router.post("/commit", response_model=CommitResult, status_code=status.HTTP_201_CREATED)
def intake_commit(
    body: CommitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    """Register the confirmed draft: case + persons + seized items, atomically."""
    if not body.case.case_number or not body.case.case_number.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A case number is required")

    case_body = CaseCreate(
        case_number=body.case.case_number.strip(),
        title=body.case.title,
        case_type=body.case.case_type,
        fir_number=body.case.fir_number,
        fir_date=body.case.fir_date,
        police_station=body.case.police_station,
        district=body.case.district,
        incident_datetime=body.case.incident_datetime,
        incident_location=body.case.incident_location,
        complaint_narrative=body.case.complaint_narrative,
        complaint_language=body.case.complaint_language,
    )

    try:
        # --- one transaction: every create below shares this session and none commits ---
        case = pool_writes.create_case_row(db, case_body, user)

        persons = []
        by_name: dict[str, int] = {}
        for draft_person in body.persons:
            person = pool_writes.create_person_row(
                db, case.id, PersonCreate(**draft_person.model_dump()), user
            )
            persons.append(person)
            for key in (draft_person.full_name, draft_person.alias):
                if key and key.strip():
                    by_name.setdefault(key.strip().lower(), person.id)

        items = []
        for draft_item in body.seized_items:
            fields = draft_item.model_dump()
            fields.pop("seized_from_name", None)
            items.append(
                pool_writes.create_seized_item_row(
                    db,
                    case.id,
                    SeizedItemCreate(
                        **fields,
                        seized_from=_resolve_seized_from(draft_item.seized_from_name, by_name),
                    ),
                    user,
                )
            )

        # Provenance: the audit trail should say this case came from conversational
        # intake rather than the manual form (§5 — audit every mutation).
        pool_writes.audit(
            db, case.id, "intake", case.id, AuditAction.CREATE,
            {
                "source": "conversational_intake",
                "persons_created": len(persons),
                "seized_items_created": len(items),
            },
            user,
        )

        db.commit()
    except HTTPException:
        db.rollback()  # e.g. duplicate case_number — leave nothing behind
        raise
    except Exception:
        db.rollback()
        logger.exception("intake commit failed; transaction rolled back")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Could not register the case from this draft. No data was saved.",
        )

    db.refresh(case)
    for row in (*persons, *items):
        db.refresh(row)

    return CommitResult(
        case=CaseOut.model_validate(case),
        persons=[PersonOut.model_validate(p) for p in persons],
        seized_items=[SeizedItemOut.model_validate(i) for i in items],
    )
