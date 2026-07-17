"""AI-suggested, officer-confirmed legal intelligence: legal_sections, judgments."""
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.enums import LegalAct, SectionStatus


class LegalSection(Base):
    __tablename__ = "legal_sections"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    act = Column(Enum(LegalAct), nullable=False)
    section_code = Column(String)
    section_title = Column(String)
    reason = Column(Text)
    triggering_phrase = Column(Text)  # explainability
    confidence = Column(Float)
    ingredient_evidence_map = Column(JSONB)  # ingredient -> evidence
    status = Column(
        Enum(SectionStatus), nullable=False, default=SectionStatus.SUGGESTED
    )
    added_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Judgment(Base):
    __tablename__ = "judgments"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    title = Column(String)
    citation = Column(String)
    court = Column(String)
    summary = Column(Text)
    relevance_reason = Column(Text)
    source_url = Column(String)
    added_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
