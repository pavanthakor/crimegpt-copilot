"""Case diary entries and the audit trail."""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.enums import ActivityType, AuditAction


class CaseDiaryEntry(Base):
    __tablename__ = "case_diary_entries"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    entry_datetime = Column(DateTime(timezone=True))
    activity_type = Column(Enum(ActivityType), nullable=False)
    description = Column(Text)
    related_person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    related_evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=True)
    auto_generated = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    entity_type = Column(String)
    entity_id = Column(Integer)
    action = Column(Enum(AuditAction), nullable=False)
    field_changes = Column(JSONB)
    performed_by = Column(Integer, ForeignKey("users.id"))
    performed_at = Column(DateTime(timezone=True), server_default=func.now())
