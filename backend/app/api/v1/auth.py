import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, security
from app.core.security import (
    decode_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.core.throttle import auth_rate_limit
from app.models.db_models import AuthSession, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserOut,
)
from app.services.audit import log_audit
from app.services.concurrency import lock_and_verify_version, resolve_expected_version, set_etag
from app.services.sessions import active_session, digest, issue

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    dependencies=[Depends(auth_rate_limit)],
    response_model=UserOut,
    status_code=201,
)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    err = validate_password_strength(payload.password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_audit(
        db,
        user_id=user.id,
        project_id=None,
        action="user.register",
        entity_type="user",
        entity_id=user.id,
    )
    set_etag(response, user.version)
    return user


@router.post(
    "/login",
    dependencies=[Depends(auth_rate_limit)],
    response_model=TokenResponse,
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    tokens = issue(db, user.id)
    log_audit(
        db,
        user_id=user.id,
        project_id=None,
        action="user.login",
        entity_type="user",
        entity_id=user.id,
    )
    return tokens


@router.post(
    "/refresh",
    dependencies=[Depends(auth_rate_limit)],
    response_model=TokenResponse,
)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    data = decode_token(payload.refresh_token)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = data.get("sub")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    active_session(db, data)
    session = (
        db.query(AuthSession)
        .filter_by(id=data["sid"])
        .with_for_update()
        .populate_existing()
        .one()
    )
    if session.revoked or not secrets.compare_digest(
        session.refresh_digest, digest(payload.refresh_token)
    ):
        session.revoked = True
        db.commit()
        raise HTTPException(401, "Refresh token replay detected; sign in again")
    return issue(db, user.id, session)


@router.post("/logout")
def logout(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    session = active_session(db, decode_token(credentials.credentials))
    session.revoked = True
    db.commit()
    return {"status": "logged_out"}


@router.get("/me", response_model=UserOut)
def me(response: Response, user: User = Depends(get_current_user)):
    set_etag(response, user.version)
    return user


@router.put("/me", response_model=UserOut)
def update_me(
    payload: UpdateProfileRequest,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    expected = resolve_expected_version(
        if_match=if_match,
        version=payload.version,
        base_version=payload.base_version,
    )
    locked_user = lock_and_verify_version(db, User, user.id, expected)
    if payload.display_name is not None:
        locked_user.display_name = payload.display_name
    if payload.email is not None:
        existing = (
            db.query(User)
            .filter(User.email == payload.email.lower(), User.id != locked_user.id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        locked_user.email = payload.email.lower()
    locked_user.version += 1
    db.commit()
    db.refresh(locked_user)
    log_audit(
        db,
        user_id=locked_user.id,
        project_id=None,
        action="user.update_profile",
        entity_type="user",
        entity_id=locked_user.id,
    )
    set_etag(response, locked_user.version)
    return locked_user


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password incorrect")
    err = validate_password_strength(payload.new_password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    user.hashed_password = hash_password(payload.new_password)
    db.query(AuthSession).filter_by(user_id=user.id).update({"revoked": True})
    db.commit()
    log_audit(
        db,
        user_id=user.id,
        project_id=None,
        action="user.change_password",
        entity_type="user",
        entity_id=user.id,
    )
    return {"status": "password_changed"}


@router.post("/password-recovery", dependencies=[Depends(auth_rate_limit)])
def password_recovery(email: str, db: Session = Depends(get_db)):
    raise HTTPException(
        status_code=503,
        detail="Password recovery email delivery is not configured",
    )
