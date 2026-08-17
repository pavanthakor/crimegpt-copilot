"""Document endpoints (CLAUDE.md §7 `documents`).

    POST /api/cases/{id}/documents/{doc_type}   generate a document (roles IO, SHO)
    GET  /api/cases/{id}/documents              list generated documents
    GET  /api/documents/{id}/download           download the .docx
    GET  /api/cases/{id}/consistency            cross-document consistency check (all roles)

Generation logic lives in app.services.documents; this module wires it to HTTP,
role gates, and case visibility.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_role, require_step_up
from app.api.cases import _get_visible_case
from app.core.db import get_db
from app.models import Document, DocumentVersion, User
from app.models.enums import DocType, UserRole
from app.schemas.case import DocumentOut
from app.services.consistency import check_consistency
from app.services.documents import finalize_document, generate_document

router = APIRouter(prefix="/api", tags=["documents"])

_DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class InconsistencyOut(BaseModel):
    field: str
    severity: str  # "high" | "low"
    values: dict[str, str | None]  # doc_type (or "current_pool") -> value shown
    note: str


class ConsistencyResult(BaseModel):
    inconsistencies: list[InconsistencyOut]
    checked_documents: int
    status: str  # "ok" | "issues_found"


class VersionDiff(BaseModel):
    changed_fields: list[str]
    changes: dict[str, dict[str, str | None]]  # field -> {"from": ..., "to": ...}


class DocumentVersionOut(BaseModel):
    version: int
    status: str | None = None
    language: str | None = None
    generated_at: str | None = None  # ISO 8601
    generated_by: int | None = None
    generated_by_name: str | None = None
    diff_from_previous: VersionDiff | None = None  # None for the first version


def _officer_names(db: Session, ids) -> dict[int, str | None]:
    """Resolve {user_id: full_name} for a set of ids (empty set -> empty map)."""
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {u.id: u.full_name for u in db.query(User).filter(User.id.in_(ids)).all()}


class VersionHistoryOut(BaseModel):
    document_id: int
    doc_type: str
    current_version: int
    versions: list[DocumentVersionOut]  # newest first


def _short(value):
    """Compact, JSON-safe rendering of a field value for a diff line."""
    if value is None:
        return None
    if isinstance(value, list):
        return f"[{len(value)} item(s)]"
    text = str(value)
    return text if len(text) <= 80 else text[:77] + "..."


def _version_diff(prev: dict | None, curr: dict | None) -> VersionDiff | None:
    """Field-level diff of two generated_data snapshots (None if no previous version)."""
    if prev is None:
        return None
    prev, curr = prev or {}, curr or {}
    changes: dict[str, dict[str, str | None]] = {}
    for field in sorted(set(prev) | set(curr)):
        a, b = prev.get(field), curr.get(field)
        if a != b:
            changes[field] = {"from": _short(a), "to": _short(b)}
    return VersionDiff(changed_fields=list(changes), changes=changes)


@router.post("/cases/{case_id}/documents/{doc_type}", response_model=DocumentOut)
def create_document(
    case_id: int,
    doc_type: DocType,
    lang: str = "en",
    report_type: str = "original",
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.IO, UserRole.SHO)),
):
    _get_visible_case(db, user, case_id)  # visibility (also 404s unknown case)
    try:
        doc = generate_document(
            db, case_id, doc_type, user, lang=lang, report_type=report_type
        )
    except ValueError as exc:
        # missing required pool data, or unregistered doc_type -> clear 400
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return doc


@router.get("/cases/{case_id}/documents", response_model=list[DocumentOut])
def list_documents(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_visible_case(db, user, case_id)
    docs = (
        db.query(Document)
        .filter(Document.case_id == case_id)
        .order_by(Document.id)
        .all()
    )

    # Resolve generating-officer names in one query (the row carries only generated_by id).
    ids = {d.generated_by for d in docs if d.generated_by is not None}
    names = _officer_names(db, ids)

    out: list[DocumentOut] = []
    for d in docs:
        row = DocumentOut.model_validate(d)
        row.generated_by_name = names.get(d.generated_by)
        out.append(row)
    return out


@router.get("/cases/{case_id}/consistency", response_model=ConsistencyResult)
def case_consistency(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),  # JWT, all roles
):
    """Pure comparison of a case's generated documents vs the pool and each other."""
    case = _get_visible_case(db, user, case_id)
    return check_consistency(db, case, user)


@router.get("/documents/{doc_id}/versions", response_model=VersionHistoryOut)
def document_versions(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Version history for a document: each version's metadata + a diff vs the previous."""
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    _get_visible_case(db, user, doc.case_id)

    history = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == doc_id)
        .order_by(DocumentVersion.version, DocumentVersion.id)
        .all()
    )

    # Chronological timeline: archived snapshots, then the live document as the head.
    timeline: list[dict] = []
    for h in history:
        snap = h.snapshot or {}
        timeline.append(
            {
                "version": h.version,
                "status": snap.get("status"),
                "language": snap.get("language"),
                "generated_at": snap.get("generated_at"),
                "generated_by": snap.get("generated_by"),
                "data": snap.get("generated_data") or {},
            }
        )
    timeline.append(
        {
            "version": doc.version,
            "status": doc.status.value if doc.status else None,
            "language": doc.language.value if doc.language else None,
            "generated_at": doc.generated_at.isoformat() if doc.generated_at else None,
            "generated_by": doc.generated_by,
            "data": doc.generated_data or {},
        }
    )

    names = _officer_names(db, {t["generated_by"] for t in timeline})
    entries: list[DocumentVersionOut] = []
    prev_data: dict | None = None
    for t in timeline:
        entries.append(
            DocumentVersionOut(
                version=t["version"],
                status=t["status"],
                language=t["language"],
                generated_at=t["generated_at"],
                generated_by=t["generated_by"],
                generated_by_name=names.get(t["generated_by"]),
                diff_from_previous=_version_diff(prev_data, t["data"]),
            )
        )
        prev_data = t["data"]
    entries.reverse()  # newest first

    return VersionHistoryOut(
        document_id=doc.id,
        doc_type=doc.doc_type.value,
        current_version=doc.version or 1,
        versions=entries,
    )


@router.post("/documents/{doc_id}/finalize", response_model=DocumentOut)
def finalize(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.SHO)),  # §9: finalize/approve is an SHO action
    # Declared AFTER require_role so an IO still gets 403, not 401. NO pin_login
    # exemption: finalize always demands a live step-up, however the token was minted.
    # An SHO can PIN-login on a phone, so exempting it would let four digits approve a
    # document.
    _step_up: User = Depends(require_step_up()),
):
    """Transition a DRAFT document to FINALIZED (snapshots a version + audit + diary)."""
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    _get_visible_case(db, user, doc.case_id)
    try:
        return finalize_document(db, doc, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/documents/{doc_id}/download")
def download_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    _get_visible_case(db, user, doc.case_id)  # enforce case visibility

    if not doc.file_path or not Path(doc.file_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document file missing on disk")

    filename = f"{doc.doc_type.value}_{doc.case_id}.docx"
    return FileResponse(doc.file_path, media_type=_DOCX_MEDIA, filename=filename)
