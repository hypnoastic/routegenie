from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import LiveSessionResponse, RouteResult, SearchSessionCreate, StopInput, TripCreateRequest, VoicePlanRequest
from app.services.auth import AuthService
from app.services.gemini_live import LiveSessionManager
from app.services.gemini_text import GeminiTextService
from app.services.maps import MapsService
from app.services.personalization import build_personalization_context
from app.services.voice_planner import plan_voice_route


router = APIRouter()


@router.post("/gemini/live-session", response_model=LiveSessionResponse)
def create_live_session(request: Request, db: Session = Depends(get_db)):
    user = AuthService(db).current_user(request)
    manager = LiveSessionManager.__new__(LiveSessionManager)
    # Reuse the same response shape without opening a session.
    LiveSessionManager.__init__(manager, None, db, user)  # type: ignore[arg-type]
    return LiveSessionResponse(**manager.build_live_session_response())


@router.post("/gemini/voice-plan", response_model=RouteResult)
async def voice_plan(payload: VoicePlanRequest, request: Request, db: Session = Depends(get_db)):
    auth = AuthService(db)
    user = auth.current_user(request)
    preferences = user.preferences if user else None
    personalization = build_personalization_context(
        preferences,
        list(user.trips[:5]) if user and user.trips else [],
        list(user.searches[:5]) if user and user.searches else [],
    )

    maps = MapsService()
    gemini = GeminiTextService()
    result = await plan_voice_route(payload.transcript, maps, gemini, personalization)

    auth.record_search(
        user,
        SearchSessionCreate(
            query_text=payload.transcript,
            transcript=payload.transcript,
            gemini_response=result.why_this_route,
            route_payload_json=result.model_dump(mode="json"),
        ),
    )

    if payload.save_trip and user is not None:
        trip = auth.save_trip(
            user,
            TripCreateRequest(
                title=gemini.generate_trip_title(result.origin, result.destination, payload.transcript),
                origin_text=result.origin,
                destination_text=result.destination,
                route_summary=result.route_summary,
                route_payload_json=result.model_dump(mode="json"),
                travel_mode=result.travel_mode,
                constraints_json=result.confirmed_route_data.get("constraints"),
                why_this_route=result.why_this_route,
                stops=[
                    StopInput(
                        name=stop.name,
                        address=stop.formatted_address,
                        place_id=stop.place_id,
                        latitude=stop.latitude,
                        longitude=stop.longitude,
                        reason=stop.name,
                        category=(stop.types[0] if stop.types else stop.source),
                        stop_order=index,
                    )
                    for index, stop in enumerate(result.stops)
                ],
            ),
        )
        result.saved_trip_id = trip.id

    return result
