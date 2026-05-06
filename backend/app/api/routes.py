from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import RouteComputeRequest, RouteResult, SearchSessionCreate, StopInput, TripCreateRequest
from app.services.auth import AuthService
from app.services.gemini_text import GeminiTextService
from app.services.maps import MapsService
from app.services.personalization import build_personalization_context


router = APIRouter()


@router.post("/routes/compute", response_model=RouteResult)
async def compute_route(payload: RouteComputeRequest, request: Request, db: Session = Depends(get_db)):
    auth = AuthService(db)
    user = auth.current_user(request)
    preferences = user.preferences if user else None
    personalization = build_personalization_context(preferences, list(user.trips[:5]) if user and user.trips else [], list(user.searches[:5]) if user and user.searches else [])

    maps = MapsService()
    result = await maps.compute_trip(
        payload.origin,
        payload.destination,
        payload.stops,
        payload.travel_mode,
        payload.constraints,
        personalization,
        payload.query_text,
        "",
    )
    result.why_this_route = GeminiTextService().generate_route_rationale(result.model_dump(mode="json"), personalization, payload.query_text)

    auth.record_search(
        user,
        SearchSessionCreate(
            query_text=payload.query_text or f"{result.origin} to {result.destination}",
            transcript=payload.query_text,
            gemini_response=result.why_this_route,
            route_payload_json=result.model_dump(mode="json"),
        ),
    )

    if payload.save_trip:
        if user is None:
            result.suggestion_notes.append("Sign in to save this trip.")
        else:
            trip = auth.save_trip(
                user,
                TripCreateRequest(
                    title=GeminiTextService().generate_trip_title(result.origin, result.destination, payload.query_text),
                    origin_text=result.origin,
                    destination_text=result.destination,
                    route_summary=result.route_summary,
                    route_payload_json=result.model_dump(mode="json"),
                    travel_mode=result.travel_mode,
                    constraints_json=payload.constraints.model_dump(),
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
