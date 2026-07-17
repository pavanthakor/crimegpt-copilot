"""The shared Unified Case Data Pool: persons, seized_items, evidence, statements."""
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.enums import EvidenceType, Language, PersonRole, StatementType


class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    role = Column(Enum(PersonRole), nullable=False)
    full_name = Column(String)
    alias = Column(String)
    father_name = Column(String)
    age = Column(Integer)
    gender = Column(String)
    address = Column(Text)
    phone = Column(String)
    occupation = Column(String)
    extra = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SeizedItem(Base):
    __tablename__ = "seized_items"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    description = Column(Text)
    quantity = Column(Integer)
    estimated_value = Column(Numeric(12, 2))
    seized_from = Column(Integer, ForeignKey("persons.id"), nullable=True)
    seizure_datetime = Column(DateTime(timezone=True))
    seizure_location = Column(String)
    item_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    type = Column(Enum(EvidenceType), nullable=False)
    file_path = Column(String)
    file_hash = Column(String(64))  # sha256
    description = Column(Text)
    tags = Column(JSONB)
    linked_person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    collected_by = Column(Integer, ForeignKey("users.id"))
    collected_at = Column(DateTime(timezone=True), server_default=func.now())
    chain_of_custody = Column(JSONB)


class Statement(Base):
    __tablename__ = "statements"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    statement_type = Column(Enum(StatementType), nullable=False)
    statement_text = Column(Text)
    language = Column(Enum(Language))
    recorded_by = Column(Integer, ForeignKey("users.id"))
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
