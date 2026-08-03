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


# ---------------------------------------------------------------------------
# PIN login — the mobile field path.
#
# A SECOND, WEAKER FRONT DOOR, and it is worth being plain about that. Everywhere else in
# this file a PIN is a STEP-UP: the officer has already proved who they are with a
# password, and the PIN re-confirms that the same person is still at the terminal. Here
# the PIN IS the credential — four digits between the station LAN and a token that can
# register a case. It exists because an officer in the field is holding a phone, not a
# keyboard, and it is meant for that network and no other.
#
# So it is hardened past the step-up above rather than sharing it:
#   * its own failure counter, so an attacker on the mobile path cannot burn down a desk
#     officer's step-up allowance — and so the step-up's behaviour is left exactly as it
#     was;
#   * five minutes of lockout rather than sixty seconds;
#   * ONE answer for every kind of failure — unknown user, no PIN set, wrong PIN, locked
#     out — so the response never tells the caller which of those they hit;
#   * a bcrypt verify runs even when there is no account to check, so the reply takes the
#     same time either way and cannot be used to enumerate usernames;
#   * fails closed: an account with no PIN set cannot sign in this way at all.
#
# What it does NOT do is invent a second kind of session. It issues the SAME JWT as the
# password login, signed the same way, so every existing endpoint accepts it unchanged and
# RBAC applies exactly as before.
#
# THE ROUTE NAME IS LOAD-BEARING: it must keep "/api/auth/login" as a prefix. The
# frontend's 401 interceptor treats any URL containing that as a failed sign-in rather
# than an expired session, so a mistyped PIN shows an error instead of bouncing the page
# to the login screen. "/api/auth/pin-login" would not match and would redirect-loop.
# ---------------------------------------------------------------------------
_PIN_LOGIN_MAX_ATTEMPTS = 5
_PIN_LOGIN_LOCKOUT_SECONDS = 5 * 60
# username -> (consecutive failures, locked-until timestamp). Keyed by the string typed,
# not by user id, because a failed attempt may name no real account. Deliberately SEPARATE
# from `_pin_failures` above: the step-up counter must keep behaving exactly as it did.
_pin_login_failures: dict[str, tuple[int, float]] = {}

# Something for bcrypt to chew on when there is no account (or no PIN) to check against,
# so a miss costs the same wall-clock as a hit. The value is irrelevant and never matches.
_ABSENT_PIN_HASH = hash_password("no-such-pin")


class PinLoginRequest(BaseModel):
    username: str
    pin: str


def _pin_login_rejected() -> HTTPException:
    """The ONLY failure this endpoint ever reports, whatever actually went wrong."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or PIN",
    )


@router.post("/login-pin", response_model=TokenResponse)
def login_pin(body: PinLoginRequest, db: Session = Depends(get_db)):
    """Sign in with username + step-up PIN. Same JWT as the password login."""
    username = body.username.strip()
    now = time.time()

    failures, locked_until = _pin_login_failures.get(username, (0, 0.0))
    if now < locked_until:
        logger.warning("pin-login: %r is locked out", username)
        raise _pin_login_rejected()

    user = db.query(User).filter(User.username == username).first()
    # Always run the verify — against the real digest when there is one, against the
    # throwaway otherwise — so "no such user" and "wrong PIN" cost the same.
    digest = user.pin_hash if (user and user.pin_hash) else _ABSENT_PIN_HASH
    matched = verify_password(body.pin, digest)

    if user is not None and user.pin_hash and matched:
        _pin_login_failures.pop(username, None)
        token = create_access_token(user.id, user.role.value)
        return TokenResponse(token=token, role=user.role, full_name=user.full_name)

    failures += 1
    locked = failures >= _PIN_LOGIN_MAX_ATTEMPTS
    _pin_login_failures[username] = (
        (0, now + _PIN_LOGIN_LOCKOUT_SECONDS) if locked else (failures, 0.0)
    )

    # Record that a PIN sign-in failed — for whom when we can tell, and whether it tripped
    # the lockout. The PIN itself is never written, logged or echoed, here or anywhere.
    # `performed_by` is null when the username matched no account: there is no officer to
    # attribute it to, and inventing one would be worse than leaving it open.
    db.add(
        AuditLog(
            case_id=None,
            entity_type="auth.pin_login",
            entity_id=user.id if user else None,
            action=AuditAction.CREATE,
            field_changes={
                "result": "locked_out" if locked else "failed",
                "username_attempted": username,
                "attempt": failures,
            },
            performed_by=user.id if user else None,
        )
    )
    db.commit()

    logger.info(
        "pin-login: failed for %r (%s/%s)%s",
        username, failures, _PIN_LOGIN_MAX_ATTEMPTS, " — locked out" if locked else "",
    )
    raise _pin_login_rejected()


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
