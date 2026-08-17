"""Password hashing (passlib/bcrypt) and JWT helpers (python-jose)."""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    user_id: int, role: str, expires_minutes: int | None = None, pin_login: bool = False
) -> str:
    """Signed JWT: sub = user id (str), plus role and an expiry claim.

    `pin_login` marks a token minted by the mobile PIN sign-in (`POST /auth/login-pin`),
    where the PIN WAS the credential. The step-up gate reads it to exempt that path from
    being asked for the same PIN again seconds later (see `require_step_up`).

    ADDITIVE BY DESIGN: the claim is written only when True, so a password-login token
    carries exactly the payload it always has and every existing token stays valid.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {"sub": str(user_id), "role": role, "exp": expire}
    if pin_login:
        payload["pin_login"] = True
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode/verify a JWT. Raises jose.JWTError on invalid/expired tokens."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
