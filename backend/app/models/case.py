from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)

from app.core.db import Base
from app.models.enums import CaseStatus, CaseType, Language


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True)
    case_number = Column(String, unique=True, nullable=False, index=True)
    case_type = Column(
        Enum(CaseType), nullable=False, default=CaseType.CONVENTIONAL
    )  # Golden Hour seam
    title = Column(String)
    fir_number = Column(String)
    fir_date = Column(Date)
    police_station = Column(String)
    district = Column(String)
    status = Column(Enum(CaseStatus), nullable=False, default=CaseStatus.COMPLAINT)
    incident_datetime = Column(DateTime(timezone=True))
    incident_location = Column(String)
    complaint_narrative = Column(Text)
    complaint_language = Column(Enum(Language))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
