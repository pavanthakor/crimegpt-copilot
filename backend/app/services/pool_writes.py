"""Non-committing core writers for the Unified Case Data Pool (CLAUDE.md §5).

Every pool create used to be inseparable from its own `db.commit()`, which made it
impossible to build a case out of several creates ATOMICALLY — a failure halfway
through left a half-registered case behind. These functions do exactly what the
existing endpoints did (build the row, flush it, write the audit_log row and the
auto case_diary_entry) and then STOP, leaving the commit to the caller.

  * The existing single-entity endpoints call one of these, then commit — behaviour
    is byte-for-byte what it was.
  * Conversational intake (`app.api.intake`) calls several inside ONE transaction and
    commits once, so a case + its persons + its seized items either all land or none do.

This module is the single definition of "what writing a pool row means". It must not
import from `app.api` (the API layer imports IT), so request-body types are accepted
duck-typed as pydantic models and only `.model_dump()` is relied upon.
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import AuditLog, Case, CaseDiaryEntry, Person, SeizedItem, User
from app.models.enums import ActivityType, AuditAction, PersonRole
from app.schemas.case import CaseCreate


def json_safe(value):
    """Convert ORM/enum/temporal values into JSON-serializable form for JSONB."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def audit(db: Session, case_id, entity_type, entity_id, action, changes, user: User) -> None:
    """Queue an audit_log row (no commit)."""
    db.add(
        AuditLog(
            case_id=case_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            field_changes=changes,
            performed_by=user.id,
        )
    )


def diary(
    db: Session,
    case_id,
    activity_type,
    description,
    user: User,
    related_person_id=None,
    related_evidence_id=None,
    event_time=None,
) -> None:
    """Queue an auto diary entry (no commit).

    `event_time` is when the thing actually happened (seizure time, collection time),
    which is what the diary should read chronologically by. It falls back to now for
    events whose occurrence *is* the act of recording them (e.g. adding a person).
    """
    db.add(
        CaseDiaryEntry(
            case_id=case_id,
            entry_datetime=event_time or datetime.now(timezone.utc),
            activity_type=activity_type,
            description=description,
            related_person_id=related_person_id,
            related_evidence_id=related_evidence_id,
            auto_generated=True,
            created_by=user.id,
        )
    )


# ---------------------------------------------------------------------------
# Core creates — build + flush + audit + diary, but NEVER commit.
#
# They raise HTTPException for domain conflicts (mirroring what the endpoints did
# inline) so both the single-entity endpoints and the transactional intake commit
# surface the same status code and message. An exception leaves the transaction
# uncommitted; `get_db` closes the session, which rolls it back.
# ---------------------------------------------------------------------------
def create_case_row(db: Session, body: CaseCreate, user: User) -> Case:
    """Register a case + its audit row + the opening COMPLAINT diary entry."""
    if db.query(Case).filter(Case.case_number == body.case_number).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "case_number already exists")

    case = Case(**body.model_dump(), created_by=user.id)
    db.add(case)
    db.flush()  # assign case.id

    audit(db, case.id, "case", case.id, AuditAction.CREATE, body.model_dump(mode="json"), user)
    diary(
        db,
        case.id,
        ActivityType.COMPLAINT,
        f"Case {case.case_number} registered from FIR complaint.",
        user,
    )
    return case


def create_person_row(db: Session, case_id: int, body: BaseModel, user: User) -> Person:
    """Add a person to the pool + audit row + diary entry."""
    person = Person(case_id=case_id, **body.model_dump())
    db.add(person)
    db.flush()

    audit(db, case_id, "person", person.id, AuditAction.CREATE, body.model_dump(mode="json"), user)
    activity = ActivityType.WITNESS_EXAM if body.role == PersonRole.WITNESS else ActivityType.OTHER
    label = body.full_name or "person"
    diary(
        db,
        case_id,
        activity,
        f"{body.role.value.title()} {label} added to the case.",
        user,
        related_person_id=person.id,
    )
    return person


def create_seized_item_row(db: Session, case_id: int, body: BaseModel, user: User) -> SeizedItem:
    """Record a seized item + audit row + EVIDENCE_SEIZURE diary entry."""
    item = SeizedItem(case_id=case_id, **body.model_dump())
    db.add(item)
    db.flush()

    audit(
        db, case_id, "seized_item", item.id, AuditAction.CREATE,
        body.model_dump(mode="json"), user,
    )
    diary(
        db,
        case_id,
        ActivityType.EVIDENCE_SEIZURE,
        f"Seized item recorded: {body.description or 'item'}.",
        user,
        event_time=item.seizure_datetime,
    )
    return item
