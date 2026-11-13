from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token, validate_password_strength
from app.models.db_models import User
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest, UserOut, UpdateProfileRequest, ChangePasswordRequest
from app.core.deps import get_current_user
from app.services.audit import log_audit

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
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
    log_audit(db, user_id=user.id, project_id=None, action="user.register", entity_type="user", entity_id=user.id)
    return user

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    log_audit(db, user_id=user.id, project_id=None, action="user.login", entity_type="user", entity_id=user.id)
    return TokenResponse(access_token=access, refresh_token=refresh, expires_in=1800)

@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    data = decode_token(payload.refresh_token)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = data.get("sub")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    access = create_access_token(user.id)
    refresh_tok = create_refresh_token(user.id)
    return TokenResponse(access_token=access, refresh_token=refresh_tok)

@router.post("/logout")
def logout(user: User = Depends(get_current_user)):
    # Stateless JWT: client discards tokens. In production, maintain denylist.
    return {"status": "logged_out"}

@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user

@router.put("/me", response_model=UserOut)
def update_me(payload: UpdateProfileRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.email is not None:
        existing = db.query(User).filter(User.email == payload.email.lower(), User.id != user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = payload.email.lower()
    db.commit()
    db.refresh(user)
    log_audit(db, user_id=user.id, project_id=None, action="user.update_profile", entity_type="user", entity_id=user.id)
    return user

@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password incorrect")
    err = validate_password_strength(payload.new_password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    log_audit(db, user_id=user.id, project_id=None, action="user.change_password", entity_type="user", entity_id=user.id)
    return {"status": "password_changed"}

# Password recovery placeholder (requires email service)
@router.post("/password-recovery")
def password_recovery(email: str, db: Session = Depends(get_db)):
    # Do not reveal if email exists
    return {"status": "if_account_exists_email_sent"}
