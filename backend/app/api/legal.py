"""Legal-intelligence endpoints (CLAUDE.md §7 `legal`).

    POST  /api/cases/{id}/analyze          run grounded section mapping, persist suggestions
    GET   /api/cases/{id}/sections         list persisted sections for a case
    PATCH /api/cases/{id}/sections/{sid}   accept / reject a suggested section

All routes require a valid JWT and enforce the same case visibility as `cases.py`.
The heavy lifting (RAG retrieval + grounded LLM selection + hard validation) lives in
`app.ai.legal`; this module only wires it to the DB, audit log, and case diary.
"""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai import legal as ai_legal
from app.ai.translate import translate
from app import demo_cache
from app.core.config import settings
from app.api.auth import get_current_user, require_role
from app.api.cases import _get_visible_case
from app.core.db import get_db
from app.models import AuditLog, Case, CaseDiaryEntry, LegalSection, Statement, User
from app.models.enums import (
    ActivityType,
    AuditAction,
    LegalAct,
    SectionStatus,
    UserRole,
)

router = APIRouter(prefix="/api/cases", tags=["legal"])


# ---------- Schemas ----------
class LegalSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    act: LegalAct
    section_code: str | None = None
    section_title: str | None = None
    reason: str | None = None
    triggering_phrase: str | None = None
    confidence: float | None = None
    status: SectionStatus


class RejectedOut(BaseModel):
    act: str | None = None
    section_code: str | None = None
    triggering_phrase: str | None = None
    rejection_reason: str | None = None


class AnalyzeResult(BaseModel):
    status: str  # "ok" | "no_grounded_match"
    sections: list[LegalSectionOut]
    rejected: list[RejectedOut]


class SectionStatusUpdate(BaseModel):
    status: SectionStatus  # only ACCEPTED or REJECTED are allowed (checked in handler)


# ---------- Helpers ----------
def _build_narrative(case: Case, statements: list[Statement]) -> str:
    """Analysis input = complaint narrative + any recorded statements."""
    parts: list[str] = []
    if case.complaint_narrative:
        parts.append(case.complaint_narrative)
    for st in statements:
        if st.statement_text:
            parts.append(st.statement_text)
    return "\n\n".join(p for p in parts if p and p.strip())


# ---------- Endpoints ----------
@router.post("/{case_id}/analyze", response_model=AnalyzeResult)
def analyze_case(
    case_id: int,
    lang: str = "en",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = _get_visible_case(db, user, case_id)

    # DEMO_MODE: serve pre-generated analysis (already translated) and skip the LLM.
    # On a cache miss, fall through to the live pipeline below rather than erroring.
    payload = demo_cache.load_analysis(case_id, lang) if settings.DEMO_MODE else None
    if payload is not None:
        status_val = payload["status"]
        sections_data = payload["sections"]
        rejected = payload.get("rejected", [])
    else:
        statements = db.query(Statement).filter(Statement.case_id == case_id).all()
        narrative = _build_narrative(case, statements)
        if not narrative:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Case has no narrative or statements to analyze"
            )
        result = ai_legal.map_sections(narrative)
        status_val = result["status"]
        rejected = result["rejected"]
        sections_data = []
        for s in result["sections"]:
            # Translate only the human-readable reason for display; section_code, title,
            # citation and triggering_phrase stay in the original so highlighting still
            # matches the narrative and legal identifiers remain canonical.
            reason = s.get("reason")
            if reason and lang.lower() != "en":
                reason = translate(reason, target=lang)
            sections_data.append({**s, "reason": reason})

    # Refresh suggestions: drop prior SUGGESTED rows, keep officer-decided ones so
    # a re-run never duplicates an already ACCEPTED/REJECTED section.
    existing = db.query(LegalSection).filter(LegalSection.case_id == case_id).all()
    decided = {
        (row.act.value, row.section_code)
        for row in existing
        if row.status != SectionStatus.SUGGESTED
    }
    for row in existing:
        if row.status == SectionStatus.SUGGESTED:
            db.delete(row)

    persisted: list[LegalSection] = []
    for s in sections_data:
        if (s["act"], str(s["section_code"])) in decided:
            continue  # already accepted/rejected — don't re-suggest
        try:
            act_enum = LegalAct(s["act"])
        except ValueError:
            act_enum = LegalAct.OTHER
        row = LegalSection(
            case_id=case_id,
            act=act_enum,
            section_code=str(s["section_code"]),
            section_title=s.get("section_title"),
            reason=s.get("reason"),
            triggering_phrase=s.get("triggering_phrase"),
            confidence=s.get("confidence"),
            status=SectionStatus.SUGGESTED,
            added_by=user.id,
        )
        db.add(row)
        persisted.append(row)

    db.add(
        AuditLog(
            case_id=case_id,
            entity_type="case",
            entity_id=case_id,
            action=AuditAction.CREATE,
            field_changes={
                "action": "analyze",
                "status": status_val,
                "suggested": len(persisted),
                "rejected": len(rejected),
            },
            performed_by=user.id,
        )
    )
    db.add(
        CaseDiaryEntry(
            case_id=case_id,
            entry_datetime=datetime.now(timezone.utc),
            activity_type=ActivityType.OTHER,
            description="AI section analysis run",
            auto_generated=True,
            created_by=user.id,
        )
    )

    db.commit()
    for row in persisted:
        db.refresh(row)

    return AnalyzeResult(
        status=status_val,
        sections=[LegalSectionOut.model_validate(r) for r in persisted],
        rejected=[RejectedOut(**r) for r in rejected],
    )


@router.get("/{case_id}/sections", response_model=list[LegalSectionOut])
def list_sections(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_visible_case(db, user, case_id)  # visibility check
    rows = (
        db.query(LegalSection)
        .filter(LegalSection.case_id == case_id)
        .order_by(LegalSection.id)
        .all()
    )
    return rows


@router.patch("/{case_id}/sections/{sid}", response_model=LegalSectionOut)
def update_section_status(
    case_id: int,
    sid: int,
    body: SectionStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_role(UserRole.IO, UserRole.SHO, UserRole.LEGAL_ADVISOR)
    ),
):
    _get_visible_case(db, user, case_id)  # visibility check
    if body.status not in (SectionStatus.ACCEPTED, SectionStatus.REJECTED):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "status must be ACCEPTED or REJECTED"
        )

    section = db.get(LegalSection, sid)
    if section is None or section.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")

    old = section.status.value
    section.status = body.status

    db.add(
        AuditLog(
            case_id=case_id,
            entity_type="legal_section",
            entity_id=sid,
            action=AuditAction.UPDATE,
            field_changes={"status": {"old": old, "new": body.status.value}},
            performed_by=user.id,
        )
    )
    db.commit()
    db.refresh(section)
    return section
