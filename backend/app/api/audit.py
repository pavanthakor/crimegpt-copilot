"""Audit-trail endpoint (CLAUDE.md §7 `audit`).

    GET /api/cases/{id}/audit   paginated audit trail (JWT, all roles)

Newest first, optional `entity_type` filter. Each entry resolves `performed_by` to the
officer's name + role so the UI needs no second lookup.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.cases import _get_visible_case
from app.core.db import get_db
from app.models import AuditLog, User
from app.models.enums import AuditAction

router = APIRouter(prefix="/api/cases", tags=["audit"])


class AuditEntryOut(BaseModel):
    id: int
    action: AuditAction
    entity_type: str | None = None
    entity_id: int | None = None
    field_changes: dict | None = None
    performed_by: int | None = None
    performed_by_name: str | None = None
    performed_by_role: str | None = None
    performed_at: datetime | None = None


class AuditPage(BaseModel):
    entries: list[AuditEntryOut]
    total: int
    limit: int
    offset: int


@router.get("/{case_id}/audit", response_model=AuditPage)
def case_audit(
    case_id: int,
    entity_type: str | None = Query(None, description="filter by entity_type, e.g. 'document'"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),  # JWT, all roles
):
    _get_visible_case(db, user, case_id)  # visibility (also 404s unknown case)

    query = db.query(AuditLog).filter(AuditLog.case_id == case_id)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)

    total = query.count()
    rows = (
        query.order_by(AuditLog.performed_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Resolve performer name + role in one query.
    performer_ids = {r.performed_by for r in rows if r.performed_by is not None}
    performers = (
        {u.id: u for u in db.query(User).filter(User.id.in_(performer_ids)).all()}
        if performer_ids
        else {}
    )

    entries = [
        AuditEntryOut(
            id=r.id,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            field_changes=r.field_changes,
            performed_by=r.performed_by,
            performed_by_name=(
                (performers[r.performed_by].full_name or performers[r.performed_by].username)
                if r.performed_by in performers
                else None
            ),
            performed_by_role=(
                performers[r.performed_by].role.value if r.performed_by in performers else None
            ),
            performed_at=r.performed_at,
        )
        for r in rows
    ]
    return AuditPage(entries=entries, total=total, limit=limit, offset=offset)
