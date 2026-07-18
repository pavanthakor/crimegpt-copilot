"""Authentication & RBAC: login, me, register (SHO/admin only)."""
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


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str | None = None
    role: UserRole


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
            },
            performed_by=_admin.id,
        )
    )

    db.commit()
    db.refresh(user)
    return user
