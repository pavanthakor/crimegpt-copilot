"""Unified Case Data Pool endpoints (CLAUDE.md §5 / §7 `pool`).

Persons, seized items, statements and evidence — the shared data every document
pulls from. Writes are gated to IO/SHO; every mutation writes an audit_log row, and
person/item/evidence additions also write an auto case_diary_entry.
"""
from __future__ import annotations

import enum
import hashlib
import json
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
from app.api.auth import get_current_user, require_role
from app.api.cases import _get_visible_case
from app.core.config import settings
from app.core.db import get_db
from app.models import (
    AuditLog,
    CaseDiaryEntry,
    Evidence,
    Person,
    SeizedItem,
    Statement,
    User,
)
from app.models.enums import (
    ActivityType,
    AuditAction,
    EvidenceType,
    Language,
    PersonRole,
    StatementType,
    UserRole,
)

router = APIRouter(prefix="/api/cases", tags=["pool"])

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


def _audit(db, case_id, entity_type, entity_id, action, changes, user):
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


def _diary(db, case_id, activity_type, description, user, related_person_id=None,
           related_evidence_id=None, event_time=None):
    """Write an auto diary entry.

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
    person = Person(case_id=case_id, **body.model_dump())
    db.add(person)
    db.flush()
    _audit(db, case_id, "person", person.id, AuditAction.CREATE, body.model_dump(mode="json"), user)
    activity = ActivityType.WITNESS_EXAM if body.role == PersonRole.WITNESS else ActivityType.OTHER
    label = (body.full_name or "person")
    _diary(db, case_id, activity, f"{body.role.value.title()} {label} added to the case.",
           user, related_person_id=person.id)
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
    item = SeizedItem(case_id=case_id, **body.model_dump())
    db.add(item)
    db.flush()
    _audit(db, case_id, "seized_item", item.id, AuditAction.CREATE, body.model_dump(mode="json"), user)
    _diary(db, case_id, ActivityType.EVIDENCE_SEIZURE,
           f"Seized item recorded: {body.description or 'item'}.", user,
           event_time=item.seizure_datetime)
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
    return db.query(Evidence).filter(Evidence.case_id == case_id).order_by(Evidence.id).all()


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
    cached = demo_cache.load_transcript(safe_name) if settings.DEMO_MODE else None
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
            # English narrative: only when we displayed the source script and it is
            # not already English. Uses the GENERAL model's translate task.
            translation_model = None
            if task == "transcribe" and detected != "en":
                english = ai_transcribe.transcribe(
                    str(out_path), language=lang, task="translate", model=None
                )
                translation = english["text"]
                translation_model = english["model"]
            else:
                translation = None
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
