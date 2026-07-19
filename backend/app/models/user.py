from sqlalchemy import Column, DateTime, Enum, Integer, String, func

from app.core.db import Base
from app.models.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(Enum(UserRole), nullable=False)
    rank = Column(String)      # e.g. "Police Inspector" — printed on the IF4 signature block
    badge_no = Column(String)  # buckle / badge number — printed on the IF4 signature block
    created_at = Column(DateTime(timezone=True), server_default=func.now())
