"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Prediction, Draw, PredictionResult
from ..schemas import (
    UserCreate, UserLogin, Token, UserOut, ProfileStats,
    ChangePassword, ForgotPassword, ResetPassword,
)
from ..auth import (
    hash_password, verify_password, create_access_token, get_current_user,
    create_reset_token, verify_reset_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=Token)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    user = User(
        name=payload.name.strip(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = create_access_token(user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/login-form", response_model=Token)
def login_form(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password flow (for Swagger 'Authorize')."""
    user = db.query(User).filter(User.email == form.username.lower()).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = create_access_token(user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/logout")
def logout(_: User = Depends(get_current_user)):
    # Stateless JWT: client discards the token.
    return {"message": "Sesión cerrada"}


@router.post("/change-password")
def change_password(payload: ChangePassword, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Contraseña actualizada"}


@router.post("/forgot-password")
def forgot_password(payload: ForgotPassword, db: Session = Depends(get_db)):
    """Issue a password-reset token.

    No email service is configured in this deployment, so the token is returned
    directly (demo). In real production this would be emailed to the user.
    """
    from ..email_util import send_reset_email, email_configured
    generic = "Si el email existe, recibirás un correo con instrucciones para restablecer tu contraseña."
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if email_configured():
        # Always return the same response to avoid user enumeration.
        if user:
            send_reset_email(user.email, create_reset_token(user.id))
        return {"message": generic, "sent": True}
    # Demo mode (no email provider): return the token directly.
    if not user:
        return {"message": generic, "sent": False}
    token = create_reset_token(user.id)
    return {
        "message": "Token de recuperación generado.",
        "reset_token": token,
        "sent": False,
        "note": "Sin servicio de email configurado; usa este token para restablecer tu contraseña.",
    }


@router.post("/reset-password")
def reset_password(payload: ResetPassword, db: Session = Depends(get_db)):
    user_id = verify_reset_token(payload.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Contraseña restablecida. Ya puedes iniciar sesión."}


@router.get("/me", response_model=ProfileStats)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total_predictions = db.query(Prediction).filter(Prediction.user_id == user.id).count()
    total_draws = db.query(Draw).filter(Draw.created_by == user.id).count()
    best = (
        db.query(PredictionResult)
        .join(Prediction, Prediction.id == PredictionResult.prediction_id)
        .filter(Prediction.user_id == user.id)
        .order_by(PredictionResult.hits.desc())
        .first()
    )
    return ProfileStats(
        user=UserOut.model_validate(user),
        total_predictions=total_predictions,
        total_draws_added=total_draws,
        best_hits=best.hits if best else 0,
    )
