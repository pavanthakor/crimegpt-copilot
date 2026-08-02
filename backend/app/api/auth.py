"""Authentication & RBAC: login, me, step-up PIN, register (SHO/admin only)."""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import AuditLog, User
from app.models.enums import AuditAction, UserRole

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer_scheme = HTTPBearer()
logger = logging.getLogger("crimegpt.auth")


# ---------- Schemas ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    role: UserRole
    full_name: str | None = None


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str | None = None
    role: UserRole
    # The officer's posting. Optional so existing callers are unaffected; an account
    # created without them simply pre-fills nothing when that officer runs intake.
    police_station: str | None = None
    district: str | None = None
    # Step-up PIN for high-stakes actions. Optional so existing callers keep working,
    # but the gate FAILS CLOSED: an account created without one cannot register a case
    # or finalize a document until a PIN is set. Create accounts with one.
    pin: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str | None = None
    role: UserRole
    police_station: str | None = None
    district: str | None = None
    # Whether a step-up PIN exists — never the digest, and never the PIN.
    has_pin: bool = False


# ---------- Dependencies ----------
def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(creds.credentials)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = db.get(User, int(user_id))
    if user is None:
        raise credentials_exc
    return user


def require_role(*roles: UserRole):
    """Dependency factory: allow only the given roles through."""
    allowed = {r.value for r in roles}

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this action",
            )
        return user

    return checker


# ---------- Endpoints ----------
@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(user.id, user.role.value)
    return TokenResponse(token=token, role=user.role, full_name=user.full_name)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


# ---------------------------------------------------------------------------
# Step-up re-authentication.
#
# A high-stakes action — registering a case, finalizing a document — asks the officer to
# confirm they are still the person at the terminal. The PIN is per-officer and checked
# against the same bcrypt digest machinery as the password.
#
# THIS ENDPOINT NEVER ANSWERS 401. The frontend's response interceptor treats any 401 as
# a dead session and redirects to the login screen, so answering 401 for a mistyped PIN
# would end the officer's session over a typo — losing an in-progress draft. A wrong PIN
# is a normal, expected outcome and comes back 200 with ok=false; only a genuinely
# invalid token still 401s, from the dependency, as everywhere else.
#
# FAILS CLOSED. An officer with no PIN set cannot step up: the answer is ok=false with
# reason "no_pin_set", never "no PIN required".
# ---------------------------------------------------------------------------
_PIN_MAX_ATTEMPTS = 5
_PIN_LOCKOUT_SECONDS = 60
# user id -> (consecutive failures, locked-until timestamp). In-process and deliberately
# simple: this is a speed bump against guessing a 4-digit PIN, not a distributed lock. On
# the single-worker on-prem deployment it is the whole story; behind multiple workers it
# would be per-worker, which is why the real protection remains that a PIN only ever
# gates an action the officer must already be authenticated and authorised to perform.
_pin_failures: dict[int, tuple[int, float]] = {}


class VerifyPinRequest(BaseModel):
    pin: str


class VerifyPinResponse(BaseModel):
    ok: bool
    # "no_pin_set" | "wrong_pin" | "locked" — a code, not a sentence, so the UI can say
    # it in the officer's language.
    reason: str | None = None
    attempts_remaining: int | None = None


@router.post("/verify-pin", response_model=VerifyPinResponse)
def verify_pin(
    body: VerifyPinRequest,
    user: User = Depends(get_current_user),
):
    """Check the logged-in officer's step-up PIN. Writes nothing, logs no PIN."""
    now = time.time()
    failures, locked_until = _pin_failures.get(user.id, (0, 0.0))
    if now < locked_until:
        logger.warning("step-up: user %s is locked out after repeated failures", user.id)
        return VerifyPinResponse(ok=False, reason="locked")

    if not user.pin_hash:
        # Fail closed: no PIN set is a refusal, not a bypass.
        return VerifyPinResponse(ok=False, reason="no_pin_set")

    if verify_password(body.pin, user.pin_hash):
        _pin_failures.pop(user.id, None)
        return VerifyPinResponse(ok=True)

    failures += 1
    if failures >= _PIN_MAX_ATTEMPTS:
        _pin_failures[user.id] = (0, now + _PIN_LOCKOUT_SECONDS)
        logger.warning("step-up: user %s locked out for %ss", user.id, _PIN_LOCKOUT_SECONDS)
        return VerifyPinResponse(ok=False, reason="locked")
    _pin_failures[user.id] = (failures, 0.0)
    # Never log the attempted PIN.
    logger.info("step-up: wrong PIN for user %s (%s/%s)", user.id, failures, _PIN_MAX_ATTEMPTS)
    return VerifyPinResponse(
        ok=False, reason="wrong_pin", attempts_remaining=_PIN_MAX_ATTEMPTS - failures
    )


@router.post(
    "/register", response_model=UserOut, status_code=status.HTTP_201_CREATED
)
def register(
    body: RegisterRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.SHO)),
):
    if db.query(User).filter(User.username == body.username).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already exists"
        )
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        police_station=body.police_station,
        district=body.district,
        pin_hash=hash_password(body.pin) if body.pin else None,
    )
    db.add(user)
    db.flush()  # assign user.id

    db.add(
        AuditLog(
            case_id=None,
            entity_type="user",
            entity_id=user.id,
            action=AuditAction.CREATE,
            field_changes={
                "username": body.username,
                "full_name": body.full_name,
                "role": body.role.value,
                "police_station": body.police_station,
                "district": body.district,
                # Whether a PIN was set — NEVER the PIN itself. The audit trail records
                # that a credential exists, not what it is.
                "pin_set": bool(body.pin),
            },
            performed_by=_admin.id,
        )
    )

    db.commit()
    db.refresh(user)
    return user
