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
    # The officer's posting. A case header's station/district describe WHERE IT WAS
    # REGISTERED, which is a property of the registering officer, not of the incident —
    # so conversational intake reads them from here rather than from the complaint text.
    police_station = Column(String)
    district = Column(String)
    # Step-up PIN for high-stakes actions (registering a case, finalizing a document).
    # A bcrypt digest from the same hash_password() that hashes the password — never a
    # plaintext PIN. Nullable, and the gate treats a null as "cannot step up" rather than
    # "no check required", so a missing PIN fails closed.
    pin_hash = Column(String)

    @property
    def has_pin(self) -> bool:
        """Whether a step-up PIN is set. Safe to expose — the digest itself never is."""
        return bool(self.pin_hash)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
