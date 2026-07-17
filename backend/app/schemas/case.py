"""Pydantic schemas for cases and the nested case data pool."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    ActivityType,
    CaseStatus,
    CaseType,
    DocStatus,
    DocType,
    Language,
    PersonRole,
    StatementType,
)


# ---------- Requests ----------
class CaseCreate(BaseModel):
    case_number: str
    title: str | None = None
    case_type: CaseType = CaseType.CONVENTIONAL
    fir_number: str | None = None
    fir_date: date | None = None
    police_station: str | None = None
    district: str | None = None
    status: CaseStatus = CaseStatus.COMPLAINT
    incident_datetime: datetime | None = None
    incident_location: str | None = None
    complaint_narrative: str | None = None
    complaint_language: Language | None = None


class CaseUpdate(BaseModel):
    """All optional; only provided fields are applied (PATCH semantics).

    case_number is intentionally omitted — it is immutable after creation.
    """

    title: str | None = None
    case_type: CaseType | None = None
    fir_number: str | None = None
    fir_date: date | None = None
    police_station: str | None = None
    district: str | None = None
    status: CaseStatus | None = None
    incident_datetime: datetime | None = None
    incident_location: str | None = None
    complaint_narrative: str | None = None
    complaint_language: Language | None = None


# ---------- Responses ----------
class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_number: str
    case_type: CaseType
    title: str | None = None
    fir_number: str | None = None
    fir_date: date | None = None
    police_station: str | None = None
    district: str | None = None
    status: CaseStatus
    incident_datetime: datetime | None = None
    incident_location: str | None = None
    complaint_narrative: str | None = None
    complaint_language: Language | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


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


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_type: DocType
    version: int | None = None
    file_path: str | None = None
    language: Language | None = None
    status: DocStatus
    generated_by: int | None = None
    generated_at: datetime | None = None


class DiaryEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_datetime: datetime | None = None
    activity_type: ActivityType
    description: str | None = None
    related_person_id: int | None = None
    related_evidence_id: int | None = None
    auto_generated: bool | None = None
    created_by: int | None = None
    created_at: datetime | None = None


class CaseDetailOut(CaseOut):
    persons: list[PersonOut] = []
    seized_items: list[SeizedItemOut] = []
    statements: list[StatementOut] = []
    documents: list[DocumentOut] = []
    diary_entries: list[DiaryEntryOut] = []
