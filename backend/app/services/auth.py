from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, Request, Response, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import SearchSession, Trip, TripStop, User, UserPreference, UserSession
from app.schemas import AuthResponse, SearchSessionCreate, TripCreateRequest, UserContextResponse, UserPreferenceOut, UserPreferenceUpdate
from app.security import generate_session_token, get_session_expiry, hash_password, hash_session_token, make_share_slug, verify_password
from app.services.personalization import update_preferences_from_history


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def signup(self, name: str, email: str, password: str, request: Request, response: Response) -> AuthResponse:
        existing = self.db.scalar(select(User).where(User.email == email.lower()))
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

        user = User(name=name.strip(), email=email.lower(), password_hash=hash_password(password))
        preferences = UserPreference(user=user)
        self.db.add_all([user, preferences])
        self.db.flush()
        self._create_session(user, request, response)
        self.db.commit()
        self.db.refresh(user)
        return AuthResponse(user=user, preferences=UserPreferenceOut.model_validate(preferences))

    def login(self, email: str, password: str, request: Request, response: Response) -> AuthResponse:
        user = self.db.scalar(select(User).where(User.email == email.lower()))
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        preferences = self._ensure_preferences(user)
        self._create_session(user, request, response)
        self.db.commit()
        return AuthResponse(user=user, preferences=UserPreferenceOut.model_validate(preferences))

    def login_with_google(self, credential: str, request: Request, response: Response) -> AuthResponse:
        if not self.settings.google_oauth_client_id:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GOOGLE_OAUTH_CLIENT_ID is not configured")
        token_info = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            audience=self.settings.google_oauth_client_id,
        )
        email = str(token_info["email"]).lower()
        sub = str(token_info["sub"])
        user = self.db.scalar(select(User).where((User.email == email) | (User.google_sub == sub)))
        if user is None:
            user = User(
                name=token_info.get("name") or email.split("@")[0],
                email=email,
                google_sub=sub,
                avatar_url=token_info.get("picture"),
            )
            self.db.add(user)
            self.db.flush()
        else:
            user.google_sub = sub
            user.avatar_url = token_info.get("picture") or user.avatar_url
            user.name = token_info.get("name") or user.name

        preferences = self._ensure_preferences(user)
        self._create_session(user, request, response)
        self.db.commit()
        self.db.refresh(user)
        return AuthResponse(user=user, preferences=UserPreferenceOut.model_validate(preferences))

    def logout(self, request: Request, response: Response) -> None:
        raw = request.cookies.get(self.settings.session_cookie_name)
        if raw:
            session = self.db.scalar(select(UserSession).where(UserSession.session_token_hash == hash_session_token(raw)))
            if session and session.revoked_at is None:
                session.revoked_at = datetime.now(UTC)
                self.db.add(session)
                self.db.commit()
        response.delete_cookie(
            key=self.settings.session_cookie_name,
            httponly=True,
            secure=self.settings.environment == "production",
            samesite="none" if self.settings.environment == "production" else "lax",
            path="/",
        )

    def current_user(self, request: Request) -> User | None:
        raw = request.cookies.get(self.settings.session_cookie_name)
        return self.current_user_from_token(raw)

    def current_user_from_token(self, raw_token: str | None) -> User | None:
        if not raw_token:
            return None
        session = self.db.scalar(select(UserSession).where(UserSession.session_token_hash == hash_session_token(raw_token)))
        if not session or session.revoked_at is not None or session.expires_at < datetime.now(UTC):
            return None
        return session.user

    def require_user(self, request: Request) -> User:
        user = self.current_user(request)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        return user

    def build_user_context(self, user: User | None) -> UserContextResponse:
        if user is None:
            return UserContextResponse(user=None, preferences=None, recent_trips=[], recent_searches=[])
        preferences = self._ensure_preferences(user)
        trips = self.db.scalars(select(Trip).where(Trip.user_id == user.id).order_by(Trip.created_at.desc()).limit(8)).all()
        searches = self.db.scalars(select(SearchSession).where(SearchSession.user_id == user.id).order_by(SearchSession.created_at.desc()).limit(8)).all()
        update_preferences_from_history(preferences, trips, searches)
        self.db.add(preferences)
        self.db.commit()
        return UserContextResponse(
            user=user,
            preferences=preferences,
            recent_trips=trips,
            recent_searches=searches,
        )

    def save_trip(self, user: User, payload: TripCreateRequest) -> Trip:
        trip = Trip(
            user_id=user.id,
            title=payload.title,
            origin_text=payload.origin_text,
            destination_text=payload.destination_text,
            route_summary=payload.route_summary,
            route_payload_json=payload.route_payload_json,
            travel_mode=payload.travel_mode,
            constraints_json=payload.constraints_json,
            why_this_route=payload.why_this_route,
        )
        trip.stops = [
            TripStop(
                name=stop.name,
                address=stop.address,
                place_id=stop.place_id,
                latitude=stop.latitude,
                longitude=stop.longitude,
                stop_order=index,
                reason=stop.reason,
                category=stop.category,
            )
            for index, stop in enumerate(payload.stops)
        ]
        self.db.add(trip)
        self.db.commit()
        self.db.refresh(trip)
        return trip

    def record_search(self, user: User | None, payload: SearchSessionCreate) -> SearchSession:
        search = SearchSession(
            user_id=user.id if user else None,
            query_text=payload.query_text,
            transcript=payload.transcript,
            gemini_response=payload.gemini_response,
            route_payload_json=payload.route_payload_json,
        )
        self.db.add(search)
        self.db.commit()
        self.db.refresh(search)
        return search

    def share_trip(self, trip: Trip) -> str:
        if not trip.share_slug:
            trip.share_slug = make_share_slug()
            self.db.add(trip)
            self.db.commit()
            self.db.refresh(trip)
        return trip.share_slug

    def update_preferences(self, user: User, payload: UserPreferenceUpdate) -> UserPreference:
        preferences = self._ensure_preferences(user)
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(preferences, field, value)
        self.db.add(preferences)
        self.db.commit()
        self.db.refresh(preferences)
        return preferences

    def _create_session(self, user: User, request: Request, response: Response) -> None:
        raw_token = generate_session_token()
        session = UserSession(
            user_id=user.id,
            session_token_hash=hash_session_token(raw_token),
            expires_at=get_session_expiry(),
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        self.db.add(session)
        response.set_cookie(
            key=self.settings.session_cookie_name,
            value=raw_token,
            httponly=True,
            secure=self.settings.environment == "production",
            samesite="none" if self.settings.environment == "production" else "lax",
            max_age=self.settings.session_ttl_days * 24 * 60 * 60,
            path="/",
        )

    def _ensure_preferences(self, user: User) -> UserPreference:
        if user.preferences is None:
            user.preferences = UserPreference(user_id=user.id)
            self.db.add(user.preferences)
            self.db.flush()
        return user.preferences
