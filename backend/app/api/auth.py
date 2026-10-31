"""Authentication: register, login, me, logout."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import ACCOUNT_ACTIVE, ROLE_DONOR
from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.core.rate_limit import limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import DonorProfile, User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.services.audit import log_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().rate_limit_login)
async def register(
    request: Request,
    payload: RegisterRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    email = payload.email.lower().strip()
    existing = db.scalar(select(User).where(User.email == email).limit(1))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=payload.role,
        status=ACCOUNT_ACTIVE,
    )
    db.add(user)
    db.flush()
    if payload.role == ROLE_DONOR:
        db.add(DonorProfile(user_id=user.id))
    log_audit(
        db,
        actor_user_id=user.id,
        action="auth.register",
        target_type="user",
        target_id=user.id,
        note=f"Registered as {payload.role}",
        ip=_client_ip(request),
    )
    db.commit()
    db.refresh(user)
    # slowapi requires rate-limited endpoints to return a Starlette Response.
    body = AuthResponse(
        access_token=create_access_token(user.id, user.role),
        token_type="bearer",
        user=UserOut.model_validate(user),
    )
    return JSONResponse(status_code=201, content=body.model_dump(mode="json"))


@router.post("/login", response_model=AuthResponse)
@limiter.limit(get_settings().rate_limit_login)
async def login(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    email = payload.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email).limit(1))
    ip = _client_ip(request)

    if user is None or not verify_password(payload.password, user.password_hash):
        # Same message for unknown email and wrong password (no user enumeration).
        log_audit(
            db,
            actor_user_id=user.id if user else None,
            action="auth.login_failed",
            target_type="user",
            target_id=user.id if user else None,
            note=f"Failed login attempt for {email}",
            ip=ip,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )

    if user.status != ACCOUNT_ACTIVE:
        log_audit(
            db,
            actor_user_id=user.id,
            action="auth.login_blocked",
            target_type="user",
            target_id=user.id,
            note=f"Login blocked for {user.status} account",
            ip=ip,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status}. Contact an administrator.",
        )

    log_audit(
        db,
        actor_user_id=user.id,
        action="auth.login_success",
        target_type="user",
        target_id=user.id,
        ip=ip,
    )
    db.commit()
    # slowapi requires rate-limited endpoints to return a Starlette Response.
    body = AuthResponse(
        access_token=create_access_token(user.id, user.role),
        token_type="bearer",
        user=UserOut.model_validate(user),
    )
    return JSONResponse(content=body.model_dump(mode="json"))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_active_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/logout")
async def logout(user: User = Depends(get_current_active_user)) -> dict:
    # JWT is stateless: the client discards the token. This endpoint confirms
    # the session was valid and gives the UI a single call to make on logout.
    return {"message": "Logged out. Discard the access token on the client."}

