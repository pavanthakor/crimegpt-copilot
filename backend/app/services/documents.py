"""Document generation engine (CLAUDE.md §8).

Gathers every field from the Unified Case Data Pool, merges it into a Word template
via docxtpl, and records the result (documents row + audit_log + DOC_GENERATED diary).

Adding a new document type needs only a template + a registry entry (templates/_registry.py)
— no change here. Free-text/narrative portions are drafted deterministically from pool
data for now; every output is a DRAFT the officer reviews before finalizing.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

from docxtpl import DocxTemplate
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Case,
    CaseDiaryEntry,
    Document,
    LegalSection,
    Person,
    SeizedItem,
    Statement,
    User,
)
from app.models.enums import (
    ActivityType,
    AuditAction,
    DocStatus,
    DocType,
    PersonRole,
    SectionStatus,
)

# services/documents.py -> parents: [1]=app, [2]=backend, [3]=repo root
_APP_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = _REPO_ROOT / "templates"
STORAGE_DIR = _APP_DIR / "storage" / "documents"


def _load_registry() -> dict:
    """Load templates/_registry.py by path (it lives outside the backend package)."""
    spec = importlib.util.spec_from_file_location(
        "doc_registry", TEMPLATES_DIR / "_registry.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.REGISTRY


def _fmt_dt(dt: datetime | None) -> str | None:
    return dt.strftime("%d/%m/%Y at %H:%M hrs") if dt else None


def _fmt_date(dt) -> str | None:
    return dt.strftime("%d/%m/%Y") if dt else None


def _first(persons: list[Person], role: PersonRole) -> Person | None:
    return next((p for p in persons if p.role == role), None)


def _build_context(db: Session, case: Case, user: User) -> dict:
    """Assemble the full merge context from the case pool. All JSON-safe."""
    persons = db.query(Person).filter(Person.case_id == case.id).order_by(Person.id).all()
    seized = db.query(SeizedItem).filter(SeizedItem.case_id == case.id).order_by(SeizedItem.id).all()
    statements = db.query(Statement).filter(Statement.case_id == case.id).all()
    accepted = (
        db.query(LegalSection)
        .filter(
            LegalSection.case_id == case.id,
            LegalSection.status == SectionStatus.ACCEPTED,
        )
        .order_by(LegalSection.id)
        .all()
    )

    accused = _first(persons, PersonRole.ACCUSED)
    victim = _first(persons, PersonRole.VICTIM)
    complainant = _first(persons, PersonRole.COMPLAINANT)
    witnesses = [p for p in persons if p.role == PersonRole.WITNESS]

    seized_items = [
        {
            "description": s.description,
            "quantity": s.quantity,
            "estimated_value": float(s.estimated_value) if s.estimated_value is not None else None,
        }
        for s in seized
    ]
    witnesses_ctx = [
        {"full_name": w.full_name, "father_name": w.father_name, "address": w.address}
        for w in witnesses
    ]
    sections_applied = [
        {"act": s.act.value, "section_code": s.section_code, "section_title": s.section_title}
        for s in accepted
    ]

    # Seizure header derives from the first seized item (per-item in the pool).
    first_seized = seized[0] if seized else None

    # Medical subject: accused first, then victim, then complainant.
    subject = accused or victim or complainant
    subject_role = (
        "accused" if subject is accused and accused
        else "victim" if subject is victim and victim
        else "complainant" if subject else None
    )
    if subject is accused and accused:
        exam_purpose = (
            "Medical examination of the accused to record the physical condition and any "
            "injuries prior to production before the Hon'ble Court."
        )
    else:
        exam_purpose = (
            "Medical examination and treatment of the person named above and issuance of the "
            "medical certificate for the purpose of investigation."
        )

    district = case.district or ""
    item_list = ", ".join(s.description for s in seized if s.description) or "nil"
    investigation_done = (
        f"The complaint was registered vide FIR No. {case.fir_number or '—'} "
        f"dated {_fmt_date(case.fir_date) or '—'} at {case.police_station or '—'}. "
        + (f"The accused {accused.full_name} has been arrested. " if accused else "")
        + f"The following article(s) have been seized during investigation: {item_list}. "
        + (f"Statement(s) of {len(statements)} witness(es)/person(s) have been recorded."
           if statements else "Recording of witness statements is in progress.")
    )

    return {
        # case
        "case_number": case.case_number,
        "title": case.title,
        "fir_number": case.fir_number,
        "fir_date": _fmt_date(case.fir_date),
        "police_station": case.police_station,
        "district": district,
        "incident_location": case.incident_location,
        "incident_datetime": _fmt_dt(case.incident_datetime),
        "complaint_narrative": case.complaint_narrative,
        # officer
        "io_name": user.full_name or user.username,
        # accused
        "accused_name": accused.full_name if accused else None,
        "accused_father": (accused.father_name if accused else None) or "",
        "accused_age": (accused.age if accused else None) or "",
        "accused_address": (accused.address if accused else None) or "",
        # lists
        "seized_items": seized_items,
        "witnesses": witnesses_ctx,
        "sections_applied": sections_applied,
        # seizure header
        "seizure_datetime": _fmt_dt(first_seized.seizure_datetime) if first_seized else None,
        "seizure_location": (first_seized.seizure_location if first_seized else None),
        # panchnama
        "panchnama_date": _fmt_date(datetime.now(timezone.utc).date()),
        "panchnama_place": case.incident_location or case.police_station,
        "proceedings_narrative": (
            f"In connection with case {case.case_number}, the place and the articles connected "
            "with the offence were examined in the presence of the panch witnesses. On "
            "examination the article(s) described below were found and seized as per law."
        ),
        # remand narratives
        "investigation_done": investigation_done,
        "pending_investigation": (
            "Recovery of the remaining case property, verification of the antecedents of the "
            "accused, identification of any associates, and recording of further statements "
            "remain to be completed."
        ),
        "grounds_for_custody": (
            f"The custodial interrogation of the accused "
            f"{accused.full_name if accused else 'named above'} is necessary to recover the "
            "remaining case property, to identify the associates involved in the offence, and "
            "to complete the investigation. There is a likelihood of the accused tampering with "
            "evidence or influencing witnesses if not taken into custody."
        ),
        # medical
        "hospital": f"Civil Hospital, {district}" if district else "the Government Hospital",
        "subject_name": subject.full_name if subject else None,
        "subject_role": subject_role,
        "examination_purpose": exam_purpose,
    }


def _missing_required(context: dict, required: list[str]) -> list[str]:
    missing = []
    for field in required:
        val = context.get(field)
        if val is None or (isinstance(val, (str, list)) and len(val) == 0):
            missing.append(field)
    return missing


def generate_document(db: Session, case_id: int, doc_type: DocType, user: User) -> Document:
    """Generate one document for a case and persist it as a DRAFT.

    Raises ValueError with the missing field list rather than rendering blanks.
    """
    case = db.get(Case, case_id)
    if case is None:
        raise ValueError(f"Case {case_id} not found")

    registry = _load_registry()
    entry = registry.get(doc_type.value)
    if entry is None:
        raise ValueError(f"No template registered for doc_type {doc_type.value}")

    context = _build_context(db, case, user)

    missing = _missing_required(context, entry["required_fields"])
    if missing:
        raise ValueError(
            f"Cannot generate {entry['title']}: missing required field(s): {', '.join(missing)}"
        )

    template_path = TEMPLATES_DIR / entry["template_file"]
    if not template_path.exists():
        raise ValueError(f"Template file not found: {template_path}")

    # Persist row first to get an id for a collision-free filename.
    doc = Document(
        case_id=case_id,
        doc_type=doc_type,
        version=1,
        status=DocStatus.DRAFT,
        generated_data=context,
        language=case.complaint_language,
        generated_by=user.id,
    )
    db.add(doc)
    db.flush()

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = STORAGE_DIR / f"{doc.id}_{doc_type.value}.docx"
    tpl = DocxTemplate(str(template_path))
    tpl.render(context)
    tpl.save(str(out_path))
    doc.file_path = str(out_path)

    db.add(
        AuditLog(
            case_id=case_id,
            entity_type="document",
            entity_id=doc.id,
            action=AuditAction.CREATE,
            field_changes={"doc_type": doc_type.value, "version": 1, "status": "DRAFT"},
            performed_by=user.id,
        )
    )
    db.add(
        CaseDiaryEntry(
            case_id=case_id,
            activity_type=ActivityType.DOC_GENERATED,
            description=f"{entry['title']} generated (draft).",
            auto_generated=True,
            created_by=user.id,
        )
    )

    db.commit()
    db.refresh(doc)
    return doc
