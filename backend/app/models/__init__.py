"""SQLAlchemy models for the Unified Case Data Pool (CLAUDE.md Section 5).

Importing this package registers every table on `Base.metadata`, so Alembic
autogenerate and `Base.metadata.create_all` see the whole schema.
"""
from app.core.db import Base
from app.models.activity import AuditLog, CaseDiaryEntry
from app.models.case import Case
from app.models.document import Document, DocumentVersion
from app.models.enums import (
    ActivityType,
    AccusedStatus,
    AuditAction,
    CaseStatus,
    CaseType,
    DocStatus,
    DocType,
    EvidenceType,
    Language,
    LegalAct,
    PersonRole,
    SectionStatus,
    StatementType,
    UserRole,
)
from app.models.legal import Judgment, LegalSection
from app.models.pool import Evidence, Person, SeizedItem, Statement
from app.models.user import User

__all__ = [
    "Base",
    # tables
    "User",
    "Case",
    "Person",
    "SeizedItem",
    "Evidence",
    "Statement",
    "LegalSection",
    "Judgment",
    "Document",
    "DocumentVersion",
    "CaseDiaryEntry",
    "AuditLog",
    # enums
    "UserRole",
    "CaseType",
    "CaseStatus",
    "Language",
    "PersonRole",
    "AccusedStatus",
    "EvidenceType",
    "StatementType",
    "LegalAct",
    "SectionStatus",
    "DocType",
    "DocStatus",
    "ActivityType",
    "AuditAction",
]
