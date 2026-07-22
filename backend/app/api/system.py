"""System runtime controls (CLAUDE.md §6 DEMO_MODE, §16 demo safety).

    GET   /api/system/demo-mode   current effective mode (any authenticated role)
    PATCH /api/system/demo-mode   toggle it at runtime (SHO only), audit-logged

The value lives in application state (app.core.runtime), so a toggle takes effect on the
next request with NO backend restart. The env var stays the startup default. Every toggle
writes an audit_log row so the change is traceable.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_role
from app.core import runtime
from app.core.db import get_db
from app.models import AuditLog, User
from app.models.enums import AuditAction, UserRole

router = APIRouter(prefix="/api/system", tags=["system"])


class DemoModeOut(BaseModel):
    demo_mode: bool


class DemoModeUpdate(BaseModel):
    demo_mode: bool


@router.get("/demo-mode", response_model=DemoModeOut)
def read_demo_mode(_user: User = Depends(get_current_user)):
    """Current DEMO_MODE state — any authenticated role may read it."""
    return DemoModeOut(demo_mode=runtime.get_demo_mode())


@router.patch("/demo-mode", response_model=DemoModeOut)
def update_demo_mode(
    body: DemoModeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.SHO)),
):
    """Toggle DEMO_MODE at runtime (SHO only). Writes an audit_log row and takes effect
    immediately for every subsequent request."""
    old = runtime.get_demo_mode()
    new = runtime.set_demo_mode(body.demo_mode)
    db.add(
        AuditLog(
            case_id=None,
            entity_type="system",
            entity_id=None,
            action=AuditAction.UPDATE,
            field_changes={"setting": "DEMO_MODE", "old": old, "new": new},
            performed_by=user.id,
        )
    )
    db.commit()
    return DemoModeOut(demo_mode=new)
