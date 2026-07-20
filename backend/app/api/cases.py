"""Case endpoints: create (from FIR), list, detail, update, search.

All routes require a valid JWT. Mutations write an audit_log row, and case
creation also writes an auto-generated case_diary_entry (CLAUDE.md Section 5/7).
"""
import enum
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_role
from app.core.db import get_db
from app.models import (
    AuditLog,
    Case,
    CaseDiaryEntry,
    Document,
    Person,
    SeizedItem,
    Statement,
    User,
)
from app.models.enums import ActivityType, AuditAction, CaseStatus, UserRole

# Status transitions that warrant an auto-generated case-diary entry.
_STATUS_TO_ACTIVITY = {
    CaseStatus.ARREST: ActivityType.ARREST,
    CaseStatus.REMAND: ActivityType.REMAND,
}
from app.schemas.case import (
    CaseCreate,
    CaseDetailOut,
    CaseOut,
    CaseUpdate,
    DiaryEntryOut,
    DocumentOut,
    PersonOut,
    SeizedItemOut,
    StatementOut,
)

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _json_safe(value):
    """Convert ORM/enum/temporal values into JSON-serializable form for JSONB."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _get_visible_case(db: Session, user: User, case_id: int) -> Case:
    """Fetch a case, enforcing that an IO can only see cases they created."""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    if user.role == UserRole.IO and case.created_by != user.id:
        # Hide existence from IOs who don't own it.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    body: CaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.IO, UserRole.SHO)),
):
    if db.query(Case).filter(Case.case_number == body.case_number).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "case_number already exists"
        )

    case = Case(**body.model_dump(), created_by=user.id)
    db.add(case)
    db.flush()  # assign case.id

    db.add(
        AuditLog(
            case_id=case.id,
            entity_type="case",
            entity_id=case.id,
            action=AuditAction.CREATE,
            field_changes=body.model_dump(mode="json"),
            performed_by=user.id,
        )
    )
    db.add(
        CaseDiaryEntry(
            case_id=case.id,
            entry_datetime=datetime.now(timezone.utc),
            activity_type=ActivityType.COMPLAINT,
            description=f"Case {case.case_number} registered from FIR complaint.",
            auto_generated=True,
            created_by=user.id,
        )
    )

    db.commit()
    db.refresh(case)
    return case


@router.get("", response_model=list[CaseOut])
def list_cases(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Case)
    if user.role == UserRole.IO:
        query = query.filter(Case.created_by == user.id)
    cases = query.order_by(Case.created_at.desc()).all()

    # Resolve creator names in one query so the SHO case list can show an Officer column
    # (the row itself only carries created_by id).
    creator_ids = {c.created_by for c in cases if c.created_by is not None}
    names: dict[int, str | None] = {}
    if creator_ids:
        for u in db.query(User).filter(User.id.in_(creator_ids)).all():
            names[u.id] = u.full_name

    out: list[CaseOut] = []
    for c in cases:
        row = CaseOut.model_validate(c)
        row.created_by_name = names.get(c.created_by)
        out.append(row)
    return out


class SearchHit(BaseModel):
    """A matched case plus which field matched, so the UI can show context."""

    case: CaseOut
    matched_field: str  # case_number | title | complaint_narrative | person_name | seized_item
    matched_value: str | None = None


# Which field wins when a case matches on several sources (lower index = stronger).
_MATCH_PRIORITY = [
    "case_number",
    "title",
    "complaint_narrative",
    "person_name",
    "seized_item",
]


def _snippet(text: str | None, q: str, width: int = 60) -> str | None:
    """A short context window around the first match of `q` inside `text`."""
    if not text:
        return text
    idx = text.lower().find(q.lower())
    if idx < 0:
        return text[:width]
    start = max(0, idx - width // 3)
    end = min(len(text), idx + len(q) + width // 2)
    return ("…" if start > 0 else "") + text[start:end].strip() + ("…" if end < len(text) else "")


@router.get("/search", response_model=list[SearchHit])
def search_cases(
    q: str = Query(..., min_length=1, description="case_number, keyword, person or item"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search cases by case_number/title/narrative, person names and seized-item text.

    Returns one hit per case with the matched field + a context snippet. Respects IO
    visibility (an IO only searches cases they created).
    """
    like = f"%{q}%"
    ql = q.lower()
    io_only = user.role == UserRole.IO
    hits: dict[int, tuple[int, str, str | None, Case]] = {}

    def consider(case: Case, field: str, value: str | None) -> None:
        priority = _MATCH_PRIORITY.index(field)
        current = hits.get(case.id)
        if current is None or priority < current[0]:
            hits[case.id] = (priority, field, value, case)

    # 1. Direct case fields.
    case_q = db.query(Case).filter(
        or_(
            Case.case_number.ilike(like),
            Case.title.ilike(like),
            Case.complaint_narrative.ilike(like),
        )
    )
    if io_only:
        case_q = case_q.filter(Case.created_by == user.id)
    for c in case_q.all():
        if c.case_number and ql in c.case_number.lower():
            consider(c, "case_number", c.case_number)
        elif c.title and ql in c.title.lower():
            consider(c, "title", c.title)
        elif c.complaint_narrative and ql in c.complaint_narrative.lower():
            consider(c, "complaint_narrative", _snippet(c.complaint_narrative, q))

    # 2. Person names (full_name / alias).
    person_q = db.query(Person, Case).join(Case, Person.case_id == Case.id).filter(
        or_(Person.full_name.ilike(like), Person.alias.ilike(like))
    )
    if io_only:
        person_q = person_q.filter(Case.created_by == user.id)
    for person, c in person_q.all():
        name = person.full_name if (person.full_name and ql in person.full_name.lower()) else person.alias
        consider(c, "person_name", f"{name} ({person.role.value.lower()})")

    # 3. Seized-item descriptions.
    item_q = db.query(SeizedItem, Case).join(Case, SeizedItem.case_id == Case.id).filter(
        SeizedItem.description.ilike(like)
    )
    if io_only:
        item_q = item_q.filter(Case.created_by == user.id)
    for item, c in item_q.all():
        consider(c, "seized_item", _snippet(item.description, q))

    ordered = sorted(
        hits.values(),
        key=lambda t: t[3].created_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return [
        SearchHit(case=CaseOut.model_validate(c), matched_field=field, matched_value=value)
        for (_, field, value, c) in ordered
    ]


@router.get("/{case_id}", response_model=CaseDetailOut)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = _get_visible_case(db, user, case_id)

    persons = db.query(Person).filter(Person.case_id == case_id).order_by(Person.id).all()
    seized = db.query(SeizedItem).filter(SeizedItem.case_id == case_id).order_by(SeizedItem.id).all()
    statements = db.query(Statement).filter(Statement.case_id == case_id).order_by(Statement.id).all()
    documents = db.query(Document).filter(Document.case_id == case_id).order_by(Document.id).all()
    # Newest first, with id as a deterministic tiebreak: several entries can share an
    # entry_datetime (a document batch, or backfilled rows), and without the tiebreak
    # their relative order is undefined and can differ between requests.
    diary = (
        db.query(CaseDiaryEntry)
        .filter(CaseDiaryEntry.case_id == case_id)
        .order_by(CaseDiaryEntry.entry_datetime.desc(), CaseDiaryEntry.id.desc())
        .all()
    )

    base = CaseOut.model_validate(case).model_dump()
    if case.created_by is not None:
        # Resolve the assigned officer's name for the workspace header (the row itself
        # only carries created_by id). Mirrors the list endpoint.
        creator = db.get(User, case.created_by)
        base["created_by_name"] = creator.full_name if creator else None

    return CaseDetailOut(
        **base,
        persons=[PersonOut.model_validate(p) for p in persons],
        seized_items=[SeizedItemOut.model_validate(s) for s in seized],
        statements=[StatementOut.model_validate(s) for s in statements],
        documents=[DocumentOut.model_validate(d) for d in documents],
        diary_entries=[DiaryEntryOut.model_validate(e) for e in diary],
    )


@router.patch("/{case_id}", response_model=CaseOut)
def update_case(
    case_id: int,
    body: CaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.IO, UserRole.SHO)),
):
    case = _get_visible_case(db, user, case_id)

    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "No fields provided to update"
        )
    changes_json = body.model_dump(mode="json", exclude_unset=True)

    field_changes: dict = {}
    for key, new_value in changes.items():
        field_changes[key] = {
            "old": _json_safe(getattr(case, key)),
            "new": changes_json[key],
        }
        setattr(case, key, new_value)

    db.add(
        AuditLog(
            case_id=case.id,
            entity_type="case",
            entity_id=case.id,
            action=AuditAction.UPDATE,
            field_changes=field_changes,
            performed_by=user.id,
        )
    )

    # Auto-generate a case-diary entry when the case status transitions.
    if "status" in changes:
        new_status = changes["status"]
        db.add(
            CaseDiaryEntry(
                case_id=case.id,
                entry_datetime=datetime.now(timezone.utc),
                activity_type=_STATUS_TO_ACTIVITY.get(new_status, ActivityType.OTHER),
                description=f"Case status updated to {new_status.value}.",
                auto_generated=True,
                created_by=user.id,
            )
        )

    db.commit()
    db.refresh(case)
    return case
