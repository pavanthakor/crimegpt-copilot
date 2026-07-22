"""Legal-intelligence endpoints (CLAUDE.md §7 `legal`).

    POST  /api/cases/{id}/analyze          run grounded section mapping, persist suggestions
    GET   /api/cases/{id}/sections         list persisted sections for a case
    PATCH /api/cases/{id}/sections/{sid}   accept / reject a suggested section
    POST  /api/cases/{id}/judgments        suggest landmark judgments, persist them
    GET   /api/cases/{id}/judgments        list judgments attached to a case

All routes require a valid JWT and enforce the same case visibility as `cases.py`.
The heavy lifting (RAG retrieval + grounded LLM selection + hard validation) lives in
`app.ai.legal` and `app.ai.judgments`; this module only wires it to the DB, audit log,
and case diary.
"""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai import judgments as ai_judgments
from app.ai import legal as ai_legal
from app.ai import weak_charge as ai_weak_charge
from app.ai.translate import translate
from app import demo_cache
from app.core import runtime
from app.api.auth import get_current_user, require_role
from app.api.cases import _get_visible_case
from app.core.db import get_db
from app.models import (
    AuditLog,
    Case,
    CaseDiaryEntry,
    Judgment,
    LegalSection,
    Statement,
    User,
)
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
    # Pre-2024 equivalent (IPC/CrPC/Evidence Act) or null; see models.LegalSection.
    cross_reference: dict | None = None
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
    # Cache-mode honesty: where this result came from, and whether cached mode missed.
    source: str = "live"  # "cache" | "live"
    cache_miss: bool = False  # DEMO_MODE was on but the cache missed -> ran live


class SectionStatusUpdate(BaseModel):
    status: SectionStatus  # only ACCEPTED or REJECTED are allowed (checked in handler)


class JudgmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None = None
    citation: str | None = None
    court: str | None = None
    summary: str | None = None
    relevance_reason: str | None = None
    source_url: str | None = None


class RejectedJudgmentOut(BaseModel):
    title: str | None = None
    citation: str | None = None
    rejection_reason: str | None = None


class JudgmentResult(BaseModel):
    status: str  # "ok" | "no_grounded_match"
    judgments: list[JudgmentOut]
    rejected: list[RejectedJudgmentOut]


class SupportedIngredientOut(BaseModel):
    ingredient: str
    evidence_quote: str


class WeakChargeAlertOut(BaseModel):
    section_code: str | None = None
    citation: str | None = None
    missing_ingredients: list[str] = []
    supported_ingredients: list[SupportedIngredientOut] = []
    severity: str  # "high" | "low"
    suggestion: str | None = None
    note: str | None = None


class RejectedIngredientOut(BaseModel):
    section_code: str | None = None
    ingredient: str | None = None
    rejection_reason: str | None = None


class WeakChargeResult(BaseModel):
    status: str  # "ok" | "no_issues"
    alerts: list[WeakChargeAlertOut]
    rejected: list[RejectedIngredientOut]


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

    # DEMO_MODE (runtime-toggleable): serve pre-generated analysis and skip the LLM. On a
    # cache miss we fall through to the live pipeline, but flag it so the client can say so
    # rather than silently pretending a cached result was served.
    demo_on = runtime.get_demo_mode()
    payload = demo_cache.load_analysis(case_id, lang) if demo_on else None
    served_from = "cache" if payload is not None else "live"
    cache_miss = demo_on and payload is None
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
            cross_reference=s.get("cross_reference"),
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
        source=served_from,
        cache_miss=cache_miss,
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
    verb = "accepted" if body.status == SectionStatus.ACCEPTED else "rejected"
    db.add(
        CaseDiaryEntry(
            case_id=case_id,
            entry_datetime=datetime.now(timezone.utc),
            activity_type=ActivityType.OTHER,
            description=f"Legal section {section.act.value} {section.section_code} {verb}.",
            auto_generated=True,
            created_by=user.id,
        )
    )
    db.commit()
    db.refresh(section)
    return section


@router.post("/{case_id}/judgments", response_model=JudgmentResult)
def suggest_case_judgments(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_role(UserRole.IO, UserRole.SHO, UserRole.LEGAL_ADVISOR)
    ),
):
    """Suggest landmark judgments for the case, grounded in the curated corpus.

    Retrieval is steered by the narrative plus the officer's ACCEPTED sections, so the
    authorities returned match the charges actually being pursued. Anything the model
    returns whose citation is not in the retrieved candidate set is dropped and reported
    in `rejected` rather than silently swallowed (CLAUDE.md §6-B).
    """
    case = _get_visible_case(db, user, case_id)

    statements = db.query(Statement).filter(Statement.case_id == case_id).all()
    narrative = _build_narrative(case, statements)
    if not narrative:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Case has no narrative or statements to analyze"
        )

    accepted = (
        db.query(LegalSection)
        .filter(
            LegalSection.case_id == case_id,
            LegalSection.status == SectionStatus.ACCEPTED,
        )
        .order_by(LegalSection.id)
        .all()
    )
    accepted_ctx = [
        {
            "act": s.act.value,
            "section_code": s.section_code,
            "section_title": s.section_title,
        }
        for s in accepted
    ]

    try:
        result = ai_judgments.suggest_judgments(narrative, accepted_ctx)
    except RuntimeError as exc:  # empty collection -> actionable 503, not a 500
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    # Re-running replaces the previous suggestions rather than accumulating duplicates.
    existing = db.query(Judgment).filter(Judgment.case_id == case_id).all()
    already = {(j.citation or "").strip() for j in existing}

    persisted: list[Judgment] = []
    for j in result["judgments"]:
        if j["citation"] in already:
            continue
        row = Judgment(
            case_id=case_id,
            title=j["title"],
            citation=j["citation"],
            court=j["court"],
            summary=j["summary"],
            relevance_reason=j["relevance_reason"],
            source_url=j["source_url"],
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
                "action": "suggest_judgments",
                "status": result["status"],
                "suggested": len(persisted),
                "rejected": len(result["rejected"]),
            },
            performed_by=user.id,
        )
    )
    db.add(
        CaseDiaryEntry(
            case_id=case_id,
            entry_datetime=datetime.now(timezone.utc),
            activity_type=ActivityType.OTHER,
            description=(
                f"Landmark judgment research run; {len(persisted)} authority(ies) added."
            ),
            auto_generated=True,
            created_by=user.id,
        )
    )

    db.commit()
    for row in persisted:
        db.refresh(row)

    # Return everything on the case (newly persisted + previously kept), newest first.
    all_rows = (
        db.query(Judgment)
        .filter(Judgment.case_id == case_id)
        .order_by(Judgment.id.desc())
        .all()
    )
    return JudgmentResult(
        status=result["status"],
        judgments=[JudgmentOut.model_validate(r) for r in all_rows],
        rejected=[RejectedJudgmentOut(**r) for r in result["rejected"]],
    )


@router.get("/{case_id}/judgments", response_model=list[JudgmentOut])
def list_case_judgments(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List the judgments already attached to this case, newest first."""
    _get_visible_case(db, user, case_id)  # visibility (also 404s unknown case)
    rows = (
        db.query(Judgment)
        .filter(Judgment.case_id == case_id)
        .order_by(Judgment.id.desc())
        .all()
    )
    return [JudgmentOut.model_validate(r) for r in rows]


@router.get("/{case_id}/weak-charges", response_model=WeakChargeResult)
def weak_charges(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_role(UserRole.IO, UserRole.SHO, UserRole.LEGAL_ADVISOR)
    ),
):
    """Flag ACCEPTED charges whose offence ingredients are not established by the file.

    For each accepted section the real statutory text is compared against the case
    material; the model may only quote ingredient spans from the statute and supporting
    spans from the material, and anything not found verbatim is rejected (CLAUDE.md
    §6-C). Read-only: nothing is persisted, no diary entry is written.
    """
    case = _get_visible_case(db, user, case_id)
    try:
        result = ai_weak_charge.check_weak_charges(db, case)
    except RuntimeError as exc:  # empty corpus -> actionable 503, not a 500
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    return WeakChargeResult(
        status=result["status"],
        alerts=[WeakChargeAlertOut(**a) for a in result["alerts"]],
        rejected=[RejectedIngredientOut(**r) for r in result["rejected"]],
    )
