from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class APIError(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str
    missing_config: list[str] = []


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    avatar_url: str | None = None


class UserPreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    preferred_travel_mode: str
    avoid_tolls: bool
    avoid_highways: bool
    max_extra_minutes: int
    safety_mode: bool
    personalization_enabled: bool
    interests_json: dict[str, Any] | None = None


class UserPreferenceUpdate(BaseModel):
    preferred_travel_mode: str | None = None
    avoid_tolls: bool | None = None
    avoid_highways: bool | None = None
    max_extra_minutes: int | None = None
    safety_mode: bool | None = None
    personalization_enabled: bool | None = None


class UserContextResponse(BaseModel):
    user: UserOut | None
    preferences: UserPreferenceOut | None
    recent_trips: list["TripOut"] = []
    recent_searches: list["SearchSessionOut"] = []


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class GoogleAuthRequest(BaseModel):
    credential: str


class AuthResponse(BaseModel):
    user: UserOut
    preferences: UserPreferenceOut | None


class StopInput(BaseModel):
    name: str
    address: str | None = None
    place_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    reason: str | None = None
    category: str | None = None
    stop_order: int = 0


class RouteConstraints(BaseModel):
    avoid_tolls: bool = False
    avoid_highways: bool = False
    max_extra_minutes: int = 20
    safety_mode: bool = False


class TripCreateRequest(BaseModel):
    title: str
    origin_text: str
    destination_text: str
    route_summary: str | None = None
    route_payload_json: dict[str, Any] | None = None
    travel_mode: str = "DRIVE"
    constraints_json: dict[str, Any] | None = None
    why_this_route: str | None = None
    stops: list[StopInput] = []


class TripStopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    address: str | None = None
    place_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    stop_order: int
    reason: str | None = None
    category: str | None = None


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    origin_text: str
    destination_text: str
    route_summary: str | None = None
    route_payload_json: dict[str, Any] | None = None
    travel_mode: str
    constraints_json: dict[str, Any] | None = None
    why_this_route: str | None = None
    share_slug: str | None = None
    created_at: datetime
    updated_at: datetime
    stops: list[TripStopOut] = []


class SearchSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    query_text: str
    transcript: str | None = None
    gemini_response: str | None = None
    route_payload_json: dict[str, Any] | None = None
    created_at: datetime


class ShareTripResponse(BaseModel):
    share_slug: str
    share_url: str


class PlacesAutocompleteRequest(BaseModel):
    input: str = Field(min_length=1)
    session_token: str | None = None
    location_bias: dict[str, Any] | None = None


class PlacesSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    location_bias: dict[str, Any] | None = None
    included_types: list[str] = []
    max_result_count: int = Field(default=5, ge=1, le=10)


class PlaceSuggestion(BaseModel):
    place_id: str | None = None
    name: str
    formatted_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    rating: float | None = None
    types: list[str] = []
    source: Literal["autocomplete", "text_search", "geocode"] = "autocomplete"


class RoutePlace(BaseModel):
    text: str | None = None
    place_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class RouteComputeRequest(BaseModel):
    origin: RoutePlace
    destination: RoutePlace
    stops: list[RoutePlace] = []
    travel_mode: str = "DRIVE"
    constraints: RouteConstraints = Field(default_factory=RouteConstraints)
    query_text: str | None = None
    save_trip: bool = False


class RouteLeg(BaseModel):
    start_address: str
    end_address: str
    distance_text: str
    duration_text: str


class RouteOption(BaseModel):
    id: str
    label: str
    distance_text: str
    duration_text: str
    arrival_time: str | None = None
    polyline: str | None = None
    note: str | None = None


class RouteResult(BaseModel):
    origin: str
    destination: str
    travel_mode: str
    distance_text: str
    duration_text: str
    duration_minutes: int
    arrival_time: str | None = None
    polyline: str | None = None
    legs: list[RouteLeg] = []
    stops: list[PlaceSuggestion] = []
    smart_stop_suggestions: list[PlaceSuggestion] = []
    comparison_options: list[RouteOption] = []
    why_this_route: str
    route_summary: str
    confirmed_route_data: dict[str, Any]
    suggestion_notes: list[str] = []
    saved_trip_id: UUID | None = None


class LiveSessionResponse(BaseModel):
    live_model: str | None
    text_model: str
    status: str
    missing_config: list[str] = []


class VoicePlanRequest(BaseModel):
    transcript: str = Field(min_length=3, max_length=2000)
    save_trip: bool = False


class VoiceRouteIntent(BaseModel):
    origin: str | None = None
    destination: str | None = None
    stop_query: str | None = None
    travel_mode: str = "DRIVE"
    avoid_tolls: bool = False
    avoid_highways: bool = False
    safety_mode: bool = False
    max_extra_minutes: int = 20
    clarification_question: str | None = None


class SearchSessionCreate(BaseModel):
    query_text: str
    transcript: str | None = None
    gemini_response: str | None = None
    route_payload_json: dict[str, Any] | None = None


UserContextResponse.model_rebuild()
