"""Document endpoints (CLAUDE.md §7 `documents`).

    POST /api/cases/{id}/documents/{doc_type}   generate a document (roles IO, SHO)
    GET  /api/cases/{id}/documents              list generated documents
    GET  /api/documents/{id}/download           download the .docx

Generation logic lives in app.services.documents; this module wires it to HTTP,
role gates, and case visibility.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_role
from app.api.cases import _get_visible_case
from app.core.db import get_db
from app.models import Document, User
from app.models.enums import DocType, UserRole
from app.schemas.case import DocumentOut
from app.services.documents import generate_document

router = APIRouter(prefix="/api", tags=["documents"])

_DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post("/cases/{case_id}/documents/{doc_type}", response_model=DocumentOut)
def create_document(
    case_id: int,
    doc_type: DocType,
    lang: str = "en",
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.IO, UserRole.SHO)),
):
    _get_visible_case(db, user, case_id)  # visibility (also 404s unknown case)
    try:
        doc = generate_document(db, case_id, doc_type, user, lang=lang)
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
    return (
        db.query(Document)
        .filter(Document.case_id == case_id)
        .order_by(Document.id)
        .all()
    )


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
