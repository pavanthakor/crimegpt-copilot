"""Unified Case Data Pool endpoints (CLAUDE.md §5 / §7 `pool`).

Persons, seized items, statements and evidence — the shared data every document
pulls from. Writes are gated to IO/SHO; every mutation writes an audit_log row, and
person/item/evidence additions also write an auto case_diary_entry.
"""
from __future__ import annotations

import enum
import hashlib
import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app import demo_cache
from app.ai import transcribe as ai_transcribe
from app.ai.transcribe import TranscriptionError
from app.ai.translate import translate as ai_translate
from fastapi.responses import FileResponse

from app.api.auth import get_current_user, require_role
from app.api.cases import _get_visible_case
from app.core.config import settings
from app.core import runtime
from app.core.db import get_db
from app.services import pool_writes
from app.schemas.case import DiaryEntryOut
from app.models import (
    CaseDiaryEntry,
    Evidence,
    Person,
    SeizedItem,
    Statement,
    User,
)
from app.models.enums import (
    AccusedStatus,
    ActivityType,
    AuditAction,
    EvidenceType,
    Language,
    PersonRole,
    StatementType,
    UserRole,
)

router = APIRouter(prefix="/api/cases", tags=["pool"])
logger = logging.getLogger("crimegpt.pool")

_STORAGE_EVIDENCE = Path(__file__).resolve().parents[1] / "storage" / "evidence"
_STORAGE_AUDIO = Path(__file__).resolve().parents[1] / "storage" / "audio"
_WRITE_ROLES = (UserRole.IO, UserRole.SHO)


def _json_safe(value):
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


# Audit + diary writers and the core creates now live in services.pool_writes, so a
# multi-entity create (conversational intake) can compose them in ONE transaction.
# Aliased to the original private names so every call site below is unchanged.
_audit = pool_writes.audit
_diary = pool_writes.diary


def _apply_patch(db, obj, body, entity_type, case_id, user):
    """Apply a PATCH body to an ORM object, writing an audit row of the diff."""
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields provided to update")
    changes_json = body.model_dump(mode="json", exclude_unset=True)
    field_changes = {}
    for key, new_value in changes.items():
        field_changes[key] = {"old": _json_safe(getattr(obj, key)), "new": changes_json[key]}
        setattr(obj, key, new_value)
    _audit(db, case_id, entity_type, obj.id, AuditAction.UPDATE, field_changes, user)
    label = entity_type.replace("_", " ")
    _diary(
        db, case_id, ActivityType.OTHER,
        f"{label.capitalize()} updated ({', '.join(field_changes)}).",
        user,
        related_person_id=obj.id if entity_type == "person" else None,
    )


# ---------------------------------------------------------------------------
# Schemas (requests). Response models reuse app.schemas.case where they exist.
# ---------------------------------------------------------------------------
class PersonCreate(BaseModel):
    role: PersonRole
    full_name: str | None = None
    alias: str | None = None
    father_name: str | None = None
    age: int | None = None
    gender: str | None = None
    address: str | None = None
    phone: str | None = None
    occupation: str | None = None
    extra: dict | None = None
    # Form I item 9 (chargesheet) — all optional / nullable
    dob_or_year: str | None = None
    nationality: str | None = None
    address_verified: str | None = None
    passport_no: str | None = None
    passport_issue_date: date | None = None
    passport_issue_place: str | None = None
    religion: str | None = None
    sc_st_obc: str | None = None
    provisional_criminal_no: str | None = None
    regular_criminal_no: str | None = None
    arrest_date: date | None = None
    bail_release_date: date | None = None
    forwarded_to_court_date: date | None = None
    arrest_acts_sections: str | None = None
    surety_details: str | None = None
    previous_convictions: str | None = None
    status_of_accused: AccusedStatus | None = None


class PersonUpdate(BaseModel):
    role: PersonRole | None = None
    full_name: str | None = None
    alias: str | None = None
    father_name: str | None = None
    age: int | None = None
    gender: str | None = None
    address: str | None = None
    phone: str | None = None
    occupation: str | None = None
    extra: dict | None = None
    dob_or_year: str | None = None
    nationality: str | None = None
    address_verified: str | None = None
    passport_no: str | None = None
    passport_issue_date: date | None = None
    passport_issue_place: str | None = None
    religion: str | None = None
    sc_st_obc: str | None = None
    provisional_criminal_no: str | None = None
    regular_criminal_no: str | None = None
    arrest_date: date | None = None
    bail_release_date: date | None = None
    forwarded_to_court_date: date | None = None
    arrest_acts_sections: str | None = None
    surety_details: str | None = None
    previous_convictions: str | None = None
    status_of_accused: AccusedStatus | None = None


class SeizedItemCreate(BaseModel):
    description: str | None = None
    quantity: int | None = None
    estimated_value: float | None = None
    seized_from: int | None = None
    seizure_datetime: datetime | None = None
    seizure_location: str | None = None
    item_hash: str | None = None


class SeizedItemUpdate(BaseModel):
    description: str | None = None
    quantity: int | None = None
    estimated_value: float | None = None
    seized_from: int | None = None
    seizure_datetime: datetime | None = None
    seizure_location: str | None = None
    item_hash: str | None = None


class StatementCreate(BaseModel):
    person_id: int
    statement_type: StatementType
    statement_text: str | None = None
    language: Language | None = None


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: PersonRole
    full_name: str | None = None
    alias: str | None = None
    father_name: str | None = None
    age: int | None = None
    gender: str | None = None
    address: str | None = None
    phone: str | None = None
    occupation: str | None = None
    extra: dict | None = None
    dob_or_year: str | None = None
    nationality: str | None = None
    address_verified: str | None = None
    passport_no: str | None = None
    passport_issue_date: date | None = None
    passport_issue_place: str | None = None
    religion: str | None = None
    sc_st_obc: str | None = None
    provisional_criminal_no: str | None = None
    regular_criminal_no: str | None = None
    arrest_date: date | None = None
    bail_release_date: date | None = None
    forwarded_to_court_date: date | None = None
    arrest_acts_sections: str | None = None
    surety_details: str | None = None
    previous_convictions: str | None = None
    status_of_accused: AccusedStatus | None = None


class SeizedItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    description: str | None = None
    quantity: int | None = None
    estimated_value: float | None = None
    seized_from: int | None = None
    seizure_datetime: datetime | None = None
    seizure_location: str | None = None
    item_hash: str | None = None


class StatementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    person_id: int | None = None
    statement_type: StatementType
    statement_text: str | None = None
    language: Language | None = None
    recorded_by: int | None = None
    recorded_at: datetime | None = None


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: EvidenceType
    file_path: str | None = None
    file_hash: str | None = None
    description: str | None = None
    tags: list | dict | None = None
    linked_person_id: int | None = None
    collected_by: int | None = None
    collected_by_name: str | None = None  # resolved officer name (populated by the list endpoint)
    collected_at: datetime | None = None
    chain_of_custody: list | dict | None = None


# ---------------------------------------------------------------------------
# Persons
# ---------------------------------------------------------------------------
@router.post("/{case_id}/persons", response_model=PersonOut, status_code=201)
def add_person(
    case_id: int,
    body: PersonCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _get_visible_case(db, user, case_id)
    person = pool_writes.create_person_row(db, case_id, body, user)
    db.commit()
    db.refresh(person)
    return person


@router.get("/{case_id}/persons", response_model=list[PersonOut])
def list_persons(case_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_visible_case(db, user, case_id)
    return db.query(Person).filter(Person.case_id == case_id).order_by(Person.id).all()


@router.patch("/{case_id}/persons/{pid}", response_model=PersonOut)
def update_person(
    case_id: int,
    pid: int,
    body: PersonUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _get_visible_case(db, user, case_id)
    person = db.get(Person, pid)
    if person is None or person.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    _apply_patch(db, person, body, "person", case_id, user)
    db.commit()
    db.refresh(person)
    return person


@router.delete("/{case_id}/persons/{pid}", status_code=204)
def delete_person(
    case_id: int,
    pid: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _get_visible_case(db, user, case_id)
    person = db.get(Person, pid)
    if person is None or person.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")

    # A statement is meaningless without the person who gave it — refuse the delete
    # rather than silently orphaning it (409, officer-facing message).
    if db.query(Statement).filter(Statement.person_id == pid).count():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Cannot delete — this person has recorded statements. Remove the statements first.",
        )

    # These records should SURVIVE the person with the reference cleared: the diary entry
    # is a log of what happened, and a seized item / evidence is still valid case property.
    # Null the FKs so the delete doesn't raise a ForeignKeyViolation.
    db.query(CaseDiaryEntry).filter(CaseDiaryEntry.related_person_id == pid).update(
        {CaseDiaryEntry.related_person_id: None}, synchronize_session=False
    )
    db.query(SeizedItem).filter(SeizedItem.seized_from == pid).update(
        {SeizedItem.seized_from: None}, synchronize_session=False
    )
    db.query(Evidence).filter(Evidence.linked_person_id == pid).update(
        {Evidence.linked_person_id: None}, synchronize_session=False
    )

    _audit(db, case_id, "person", pid, AuditAction.DELETE,
           {"full_name": person.full_name, "role": _json_safe(person.role)}, user)
    db.delete(person)
    db.commit()


# ---------------------------------------------------------------------------
# Seized items
# ---------------------------------------------------------------------------
@router.post("/{case_id}/seized-items", response_model=SeizedItemOut, status_code=201)
def add_seized_item(
    case_id: int,
    body: SeizedItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _get_visible_case(db, user, case_id)
    item = pool_writes.create_seized_item_row(db, case_id, body, user)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{case_id}/seized-items", response_model=list[SeizedItemOut])
def list_seized_items(case_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_visible_case(db, user, case_id)
    return db.query(SeizedItem).filter(SeizedItem.case_id == case_id).order_by(SeizedItem.id).all()


@router.patch("/{case_id}/seized-items/{sid}", response_model=SeizedItemOut)
def update_seized_item(
    case_id: int,
    sid: int,
    body: SeizedItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _get_visible_case(db, user, case_id)
    item = db.get(SeizedItem, sid)
    if item is None or item.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Seized item not found")
    _apply_patch(db, item, body, "seized_item", case_id, user)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{case_id}/seized-items/{sid}", status_code=204)
def delete_seized_item(
    case_id: int,
    sid: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _get_visible_case(db, user, case_id)
    item = db.get(SeizedItem, sid)
    if item is None or item.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Seized item not found")
    _audit(db, case_id, "seized_item", sid, AuditAction.DELETE,
           {"description": item.description}, user)
    db.delete(item)
    db.commit()


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------
@router.post("/{case_id}/statements", response_model=StatementOut, status_code=201)
def add_statement(
    case_id: int,
    body: StatementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _get_visible_case(db, user, case_id)
    stmt = Statement(case_id=case_id, recorded_by=user.id, **body.model_dump())
    db.add(stmt)
    db.flush()
    _audit(db, case_id, "statement", stmt.id, AuditAction.CREATE, body.model_dump(mode="json"), user)
    person = db.get(Person, body.person_id)
    who = (person.full_name or person.alias) if person else None
    who = who or f"person #{body.person_id}"
    _diary(
        db, case_id,
        ActivityType.WITNESS_EXAM if body.statement_type == StatementType.WITNESS else ActivityType.OTHER,
        f"{body.statement_type.value.capitalize()} statement recorded for {who}.",
        user,
        related_person_id=body.person_id,
    )
    db.commit()
    db.refresh(stmt)
    return stmt


@router.get("/{case_id}/statements", response_model=list[StatementOut])
def list_statements(case_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_visible_case(db, user, case_id)
    return db.query(Statement).filter(Statement.case_id == case_id).order_by(Statement.id).all()


# ---------------------------------------------------------------------------
# Evidence (multipart upload -> hash + tag + chain of custody)
# ---------------------------------------------------------------------------
def _parse_tags(raw: str | None) -> list:
    if not raw:
        return []
    raw = raw.strip()
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else [val]
    except (json.JSONDecodeError, ValueError):
        return [t.strip() for t in raw.split(",") if t.strip()]


@router.post("/{case_id}/evidence", response_model=EvidenceOut, status_code=201)
async def upload_evidence(
    case_id: int,
    file: UploadFile = File(...),
    type: EvidenceType = Form(EvidenceType.IMAGE),
    description: str | None = Form(None),
    tags: str | None = Form(None),
    linked_person_id: int | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _get_visible_case(db, user, case_id)

    data = await file.read()
    file_hash = hashlib.sha256(data).hexdigest()
    now = datetime.now(timezone.utc)

    ev = Evidence(
        case_id=case_id,
        type=type,
        file_hash=file_hash,
        description=description,
        tags=_parse_tags(tags),
        linked_person_id=linked_person_id,
        collected_by=user.id,
        chain_of_custody=[
            {
                "action": "COLLECTED",
                "by": user.id,
                "by_name": user.full_name or user.username,
                "at": now.isoformat(),
                "note": "Initial collection / upload",
                "sha256": file_hash,
            }
        ],
    )
    db.add(ev)
    db.flush()

    _STORAGE_EVIDENCE.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "evidence").name
    out_path = _STORAGE_EVIDENCE / f"{ev.id}_{safe_name}"
    out_path.write_bytes(data)
    ev.file_path = str(out_path)

    _audit(db, case_id, "evidence", ev.id, AuditAction.CREATE,
           {"type": _json_safe(type), "file_hash": file_hash, "description": description}, user)
    _diary(db, case_id, ActivityType.EVIDENCE_SEIZURE,
           f"Evidence collected: {description or safe_name} (sha256 {file_hash[:12]}…).",
           user, related_evidence_id=ev.id, event_time=ev.collected_at)
    db.commit()
    db.refresh(ev)
    return ev


@router.get("/{case_id}/evidence", response_model=list[EvidenceOut])
def list_evidence(case_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_visible_case(db, user, case_id)
    rows = db.query(Evidence).filter(Evidence.case_id == case_id).order_by(Evidence.id).all()

    # Resolve collecting-officer names in one query (the row carries only collected_by id).
    ids = {e.collected_by for e in rows if e.collected_by is not None}
    names: dict[int, str | None] = {}
    if ids:
        for u in db.query(User).filter(User.id.in_(ids)).all():
            names[u.id] = u.full_name

    out: list[EvidenceOut] = []
    for e in rows:
        row = EvidenceOut.model_validate(e)
        row.collected_by_name = names.get(e.collected_by)
        out.append(row)
    return out


@router.get("/{case_id}/evidence/{eid}/file")
def get_evidence_file(
    case_id: int,
    eid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Serve the stored evidence file (image thumbnails / previews).

    Authenticated + case-visibility enforced, so the frontend fetches it as an
    authenticated blob rather than exposing storage over a public URL.
    """
    ev = db.get(Evidence, eid)
    if ev is None or ev.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found")
    _get_visible_case(db, user, case_id)
    if not ev.file_path or not Path(ev.file_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence file missing on disk")
    return FileResponse(ev.file_path)


@router.delete("/{case_id}/evidence/{eid}", status_code=204)
def delete_evidence(
    case_id: int,
    eid: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _get_visible_case(db, user, case_id)
    ev = db.get(Evidence, eid)
    if ev is None or ev.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found")

    # The diary entry logging this collection should SURVIVE with the reference cleared.
    # case_diary_entries.related_evidence_id is the ONLY FK pointing at evidence, so nulling
    # it is sufficient to avoid a ForeignKeyViolation on delete.
    db.query(CaseDiaryEntry).filter(CaseDiaryEntry.related_evidence_id == eid).update(
        {CaseDiaryEntry.related_evidence_id: None}, synchronize_session=False
    )

    _audit(db, case_id, "evidence", eid, AuditAction.DELETE,
           {"description": ev.description, "file_hash": ev.file_hash}, user)
    stored = ev.file_path
    db.delete(ev)
    db.commit()

    # Best-effort removal of the stored file after the row is gone (a missing file is not fatal).
    if stored:
        try:
            Path(stored).unlink(missing_ok=True)
        except OSError:
            pass


class DiaryEntryCreate(BaseModel):
    activity_type: ActivityType = ActivityType.OTHER
    description: str
    entry_datetime: datetime | None = None
    related_person_id: int | None = None
    related_evidence_id: int | None = None


@router.post("/{case_id}/diary", response_model=DiaryEntryOut, status_code=201)
def add_diary_entry(
    case_id: int,
    body: DiaryEntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    """Manual case-diary entry an officer records themselves (auto_generated = False).

    Auto entries are written by the system on key actions; this is the officer's own note.
    """
    _get_visible_case(db, user, case_id)
    if not body.description or not body.description.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A description is required")

    entry = CaseDiaryEntry(
        case_id=case_id,
        entry_datetime=body.entry_datetime or datetime.now(timezone.utc),
        activity_type=body.activity_type,
        description=body.description.strip(),
        related_person_id=body.related_person_id,
        related_evidence_id=body.related_evidence_id,
        auto_generated=False,
        created_by=user.id,
    )
    db.add(entry)
    db.flush()
    _audit(db, case_id, "case_diary_entry", entry.id, AuditAction.CREATE,
           {"activity_type": body.activity_type.value, "manual": True}, user)
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# Voice input — dictate the complaint in Gujarati/Hindi/English (CLAUDE.md §4)
# ---------------------------------------------------------------------------
class TranscribeResult(BaseModel):
    transcript: str          # display text, in the `task` output (source script by default)
    language: str            # gu | hi | en (source)
    task: str                # transcribe | translate — how `transcript` was produced
    translation: str | None  # English narrative (None when source is en or task==translate)
    duration: float | None   # seconds of audio
    confidence: float | None # 0-1 proxy from segment log-probs
    model: str | None        # the WHISPER_MODEL used
    audio_id: str            # sha256 of the stored audio


@router.post("/{case_id}/transcribe", response_model=TranscribeResult, status_code=201)
async def transcribe_audio(
    case_id: int,
    file: UploadFile = File(...),
    language: str = Form("gu"),
    task: str = Form("transcribe"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_WRITE_ROLES)),
):
    """Transcribe a dictated complaint and translate it to English.

    Saves the audio under storage/audio/ with a sha256 (same treatment as evidence),
    then runs faster-whisper on CPU. By default (task="transcribe") it does BOTH:
    a transcript in the spoken script for display, AND — when the source is not
    English — an English narrative via Whisper's own translate task. task="translate"
    returns only the direct English. The result is RETURNED for officer review; it
    does NOT overwrite the case narrative. Writes an audit row and a diary entry.
    """
    case = _get_visible_case(db, user, case_id)

    lang = (language or "gu").lower()
    if lang not in ai_transcribe.SUPPORTED_LANGS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported language {lang!r}; expected one of {ai_transcribe.SUPPORTED_LANGS}",
        )
    task = (task or "transcribe").lower()
    if task not in ai_transcribe.TASKS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported task {task!r}; expected one of {ai_transcribe.TASKS}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty audio upload")
    audio_hash = hashlib.sha256(data).hexdigest()

    _STORAGE_AUDIO.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "audio").name
    suffix = Path(safe_name).suffix or ".wav"
    out_path = _STORAGE_AUDIO / f"{audio_hash}{suffix}"
    out_path.write_bytes(data)

    model_used = settings.WHISPER_MODEL
    translation_model = None
    # DEMO_MODE: serve a pre-generated transcript keyed by the audio filename so a
    # slow/stalled model never breaks the demo. Miss -> fall through to live.
    cached = demo_cache.load_transcript(safe_name) if runtime.get_demo_mode() else None
    if cached is not None:
        transcript = cached.get("transcript", "")
        detected = cached.get("language", lang)
        translation = cached.get("translation")
        duration = cached.get("duration")
        confidence = cached.get("confidence")
        model_used = cached.get("model", model_used)
    else:
        try:
            # Dual-model path: the Gujarati DISPLAY transcript comes from the
            # Gujarati-specialised model (with prompt + guards, applied inside
            # transcribe()); the English NARRATIVE comes from the general model's
            # translate task. Both on CPU. If no Gujarati model is configured/present,
            # display_model is None and the general model handles both.
            display_model = None
            if task == "transcribe" and lang == "gu":
                display_model = ai_transcribe.gu_model_spec()
            display = ai_transcribe.transcribe(
                str(out_path), language=lang, task=task, model=display_model
            )
            transcript = display["text"]
            detected = display["language"]
            duration = display["duration"]
            confidence = display["confidence"]
            model_used = display["model"]
            # English narrative: only when we displayed the source script and it is not
            # already English. PREFERRED path = LLM-translate the (clean, complete)
            # Gujarati transcript via Qwen (app.ai.translate). Whisper's own speech->English
            # translate task is the weak link — repetitive/garbled on real audio — so it is
            # kept only as a FALLBACK for when the LLM call fails or returns nothing.
            translation = None
            translation_model = None
            if task == "transcribe" and detected != "en" and transcript.strip():
                try:
                    translation = ai_translate(transcript, target="en", source=detected)
                    translation_model = f"llm:{settings.LLM_MODEL}"
                except Exception:  # noqa: BLE001 — LLM/Ollama down must not fail the request
                    logger.exception("LLM narrative translation failed; using Whisper translate")
                    translation = None
                if not translation or not translation.strip():
                    english = ai_transcribe.transcribe(
                        str(out_path), language=lang, task="translate", model=None
                    )
                    translation = english["text"]
                    translation_model = english["model"]
        except TranscriptionError as exc:
            # Clear, non-silent failure — the officer must know to re-record.
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    _audit(db, case_id, "audio", None, AuditAction.CREATE, {
        "action": "transcribe",
        "audio_sha256": audio_hash,
        "language": detected,
        "task": task,
        "model": model_used,
        "translation_model": translation_model,
        "duration": duration,
        "chars": len(transcript),
    }, user)
    _diary(db, case_id, ActivityType.OTHER, "Voice statement recorded", user)

    db.commit()
    return TranscribeResult(
        transcript=transcript,
        language=detected,
        task=task,
        translation=translation,
        duration=duration,
        confidence=confidence,
        model=model_used,
        audio_id=audio_hash,
    )
