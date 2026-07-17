"""Generated documents and their version history."""
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base
from app.models.enums import DocStatus, DocType, Language


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    doc_type = Column(Enum(DocType), nullable=False)
    version = Column(Integer, default=1)
    file_path = Column(String)
    generated_data = Column(JSONB)  # the exact data merged in
    language = Column(Enum(Language))
    status = Column(Enum(DocStatus), nullable=False, default=DocStatus.DRAFT)
    generated_by = Column(Integer, ForeignKey("users.id"))
    generated_at = Column(DateTime(timezone=True), server_default=func.now())


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    version = Column(Integer)
    snapshot = Column(JSONB)
    edited_by = Column(Integer, ForeignKey("users.id"))
    edited_at = Column(DateTime(timezone=True), server_default=func.now())
