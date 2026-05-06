from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import AuthResponse, LoginRequest, SignupRequest, UserContextResponse, UserPreferenceOut, UserPreferenceUpdate
from app.services.auth import AuthService
from app.schemas import GoogleAuthRequest


router = APIRouter()


@router.post("/auth/signup", response_model=AuthResponse)
def signup(payload: SignupRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    return AuthService(db).signup(payload.name, payload.email, payload.password, request, response)


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    return AuthService(db).login(payload.email, payload.password, request, response)


@router.post("/auth/google", response_model=AuthResponse)
def login_with_google(payload: GoogleAuthRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    return AuthService(db).login_with_google(payload.credential, request, response)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    AuthService(db).logout(request, response)
    return {"status": "ok"}


@router.get("/me", response_model=UserContextResponse)
def me(request: Request, db: Session = Depends(get_db)):
    service = AuthService(db)
    return service.build_user_context(service.current_user(request))


@router.put("/me/preferences", response_model=UserPreferenceOut)
def update_preferences(payload: UserPreferenceUpdate, request: Request, db: Session = Depends(get_db)):
    service = AuthService(db)
    user = service.require_user(request)
    return service.update_preferences(user, payload)
