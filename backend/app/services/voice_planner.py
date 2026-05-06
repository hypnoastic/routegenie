from __future__ import annotations

import asyncio
import re
from typing import Any

from fastapi import HTTPException, status

from app.schemas import RouteConstraints, RoutePlace, RouteResult
from app.services.gemini_text import GeminiTextService
from app.services.maps import MapsService


def city_hint(address: str | None) -> str | None:
    if not address:
        return None
    parts = [part.strip() for part in address.split(",") if part.strip()]
    for part in reversed(parts):
        if part.lower() not in {"india"} and not any(char.isdigit() for char in part):
            return part
    return None


def clean_place_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = text.strip()
    filler_patterns = [
        r"^(hey|hi|hello)\b[\s,]*",
        r"\b(can you|could you|would you|please|tell me|show me|give me|find me)\b",
        r"\b(route from|go from|take me from|directions from)\b",
    ]
    for pattern in filler_patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
    cleaned = re.sub(r"^(a|an|the)\s+", "", cleaned, flags=re.IGNORECASE).strip(" ,.")
    return cleaned or None


def voice_route_reply(route_payload: dict[str, Any]) -> str:
    stops = route_payload.get("stops") or []
    stop_name = None
    if stops:
        stop_name = stops[0].get("name") or stops[0].get("formatted_address")
    suffix = f" via {stop_name}" if stop_name else ""
    return f"Route ready: {route_payload.get('duration_text')}, {route_payload.get('distance_text')}{suffix}."


def looks_like_route_request(transcript: str) -> bool:
    lowered = transcript.lower()
    route_markers = [
        r"\bfrom\b.+\bto\b",
        r"\btake me\b",
        r"\bnavigate\b",
        r"\bdirections?\b",
        r"\broute\b",
        r"\bgo to\b",
        r"\bdrive to\b",
        r"\bwalk to\b",
        r"\bpass by\b",
        r"\bvia\b",
        r"\bstop at\b",
        r"\badd a stop\b",
    ]
    return any(re.search(marker, lowered) for marker in route_markers)


def _normalized_search_text(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _brand_tokens(query: str) -> list[str]:
    normalized = _normalized_search_text(query)
    tokens = [token for token in normalized.split() if len(token) > 2]
    generic_tokens = {
        "a",
        "an",
        "the",
        "good",
        "best",
        "near",
        "stop",
        "place",
        "places",
        "food",
        "restaurant",
        "restaurants",
        "cafe",
        "cafes",
        "coffee",
        "fuel",
        "petrol",
        "gas",
        "ev",
        "charging",
        "charger",
        "restroom",
        "toilet",
        "scenic",
        "viewpoint",
        "shopping",
        "mall",
        "hotel",
        "emergency",
        "hospital",
    }
    return [token for token in tokens if token not in generic_tokens]


def _candidate_matches_stop_query(candidate, stop_query: str) -> bool:
    tokens = _brand_tokens(stop_query)
    if not tokens:
        return True
    haystack = _normalized_search_text(f"{candidate.name} {candidate.formatted_address or ''}")
    return any(token in haystack for token in tokens)


def _place_variants(text: str | None, hint_text: str | None = None) -> list[str]:
    base = clean_place_text(text)
    if not base:
        return []

    variants: list[str] = [base]
    generic_words = {"university", "college", "institute", "school", "campus"}
    simplified = " ".join(token for token in base.split() if token.lower() not in generic_words).strip()
    if simplified and simplified.lower() != base.lower():
        variants.append(simplified)
    if hint_text:
        hint = clean_place_text(hint_text)
        if hint:
            variants.append(f"{base} {hint}")
            if simplified and simplified.lower() != base.lower():
                variants.append(f"{simplified} {hint}")

    seen: set[str] = set()
    ordered: list[str] = []
    for variant in variants:
        key = variant.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(variant)
    return ordered


async def resolve_best_place(maps: MapsService, text: str | None, hint_text: str | None = None) -> dict | None:
    for variant in _place_variants(text, hint_text):
        try:
            return await maps.resolve_place(RoutePlace(text=variant))
        except HTTPException:
            continue

    for variant in _place_variants(text, hint_text):
        candidates = await maps.search_places(variant, max_result_count=1)
        if candidates:
            candidate = candidates[0]
            return {
                "place_id": candidate.place_id,
                "text": candidate.name or variant,
                "formatted_address": candidate.formatted_address or candidate.name or variant,
                "latitude": candidate.latitude,
                "longitude": candidate.longitude,
            }
    return None


async def _select_route_stop(
    maps: MapsService,
    stop_query: str,
    origin_query: str,
    resolved_origin: dict,
    resolved_destination: dict,
) -> RoutePlace | None:
    destination_hint = resolved_destination.get("formatted_address") or ""
    midpoint = {
        "latitude": (resolved_origin["latitude"] + resolved_destination["latitude"]) / 2,
        "longitude": (resolved_origin["longitude"] + resolved_destination["longitude"]) / 2,
    }
    searches = [
        (
            stop_query,
            {
                "circle": {
                    "center": midpoint,
                    "radius": 50000.0,
                }
            },
        ),
        (f"{stop_query} between {origin_query} and {destination_hint}", None),
        (f"{stop_query} near {origin_query}", None),
        (f"{stop_query} near {destination_hint}", None),
        (f"{stop_query} {origin_query}", None),
        (f"{stop_query} {destination_hint}", None),
    ]
    search_results = await asyncio.gather(
        *[maps.search_places(query, location_bias=location_bias, max_result_count=6) for query, location_bias in searches],
        return_exceptions=True,
    )

    candidates_by_id = {}
    for result in search_results:
        if isinstance(result, Exception):
            continue
        for candidate in result:
            key = candidate.place_id or f"{candidate.latitude}:{candidate.longitude}:{candidate.name}"
            if (
                key
                and candidate.latitude is not None
                and candidate.longitude is not None
                and _candidate_matches_stop_query(candidate, stop_query)
            ):
                candidates_by_id.setdefault(key, candidate)

    candidates = list(candidates_by_id.values())
    if not candidates:
        return None

    origin_lat = float(resolved_origin["latitude"])
    origin_lng = float(resolved_origin["longitude"])
    dest_lat = float(resolved_destination["latitude"])
    dest_lng = float(resolved_destination["longitude"])
    route_lat = dest_lat - origin_lat
    route_lng = dest_lng - origin_lng
    route_len_sq = max(route_lat * route_lat + route_lng * route_lng, 0.000001)

    def score(candidate) -> float:
        cand_lat = float(candidate.latitude)
        cand_lng = float(candidate.longitude)
        progress = ((cand_lat - origin_lat) * route_lat + (cand_lng - origin_lng) * route_lng) / route_len_sq
        projected_lat = origin_lat + progress * route_lat
        projected_lng = origin_lng + progress * route_lng
        corridor_distance = (cand_lat - projected_lat) ** 2 + (cand_lng - projected_lng) ** 2
        endpoint_penalty = 0
        if progress < 0.06:
            endpoint_penalty += (0.06 - progress) * 3
        if progress > 0.88:
            endpoint_penalty += (progress - 0.88) * 6
        return corridor_distance + endpoint_penalty + abs(progress - 0.45) * 0.02

    geometrically_ranked = sorted(candidates, key=score)
    route_origin = RoutePlace(
        text=resolved_origin.get("formatted_address"),
        place_id=resolved_origin.get("place_id"),
        latitude=resolved_origin.get("latitude"),
        longitude=resolved_origin.get("longitude"),
    )
    route_destination = RoutePlace(
        text=resolved_destination.get("formatted_address"),
        place_id=resolved_destination.get("place_id"),
        latitude=resolved_destination.get("latitude"),
        longitude=resolved_destination.get("longitude"),
    )
    route_candidates = [
        RoutePlace(
            text=candidate.name,
            place_id=candidate.place_id,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
        )
        for candidate in geometrically_ranked[:8]
    ]
    try:
        optimized = await maps.optimize_stops(
            route_origin,
            route_destination,
            route_candidates,
            "DRIVE",
            RouteConstraints(),
        )
        if optimized:
            best_optimized = optimized[0]
            return RoutePlace(
                text=best_optimized.get("text") or best_optimized.get("formatted_address"),
                place_id=best_optimized.get("place_id"),
                latitude=best_optimized.get("latitude"),
                longitude=best_optimized.get("longitude"),
            )
    except Exception:
        pass

    best = geometrically_ranked[0]
    return RoutePlace(
        text=best.name,
        place_id=best.place_id,
        latitude=best.latitude,
        longitude=best.longitude,
    )


async def plan_voice_route(
    transcript: str,
    maps: MapsService,
    gemini: GeminiTextService,
    personalization: dict,
) -> RouteResult:
    intent = gemini.extract_route_intent(transcript)
    origin_query = clean_place_text(intent.origin)
    destination_query = clean_place_text(intent.destination)
    stop_query = clean_place_text(intent.stop_query)

    if not origin_query or not destination_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=intent.clarification_question or "Say where you are starting and where you want to go.",
        )

    constraints = RouteConstraints(
        avoid_tolls=intent.avoid_tolls,
        avoid_highways=intent.avoid_highways,
        max_extra_minutes=intent.max_extra_minutes,
        safety_mode=intent.safety_mode,
    )
    resolved_destination, resolved_origin = await asyncio.gather(
        resolve_best_place(maps, destination_query),
        resolve_best_place(maps, origin_query),
    )
    if resolved_destination is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Could not resolve place '{destination_query}'")

    origin_place = RoutePlace(text=origin_query)
    destination_place = RoutePlace(
        text=resolved_destination["formatted_address"],
        place_id=resolved_destination.get("place_id"),
        latitude=resolved_destination.get("latitude"),
        longitude=resolved_destination.get("longitude"),
    )
    if resolved_origin is not None:
        origin_place = RoutePlace(
            text=resolved_origin["formatted_address"],
            place_id=resolved_origin.get("place_id"),
            latitude=resolved_origin.get("latitude"),
            longitude=resolved_origin.get("longitude"),
        )

    stops: list[RoutePlace] = []
    if stop_query:
        if resolved_origin is not None:
            selected_stop = await _select_route_stop(maps, stop_query, origin_query, resolved_origin, resolved_destination)
            if selected_stop is not None:
                stops.append(selected_stop)
        if not stops:
            stops.append(RoutePlace(text=stop_query))

    result = await maps.compute_trip(
        origin_place,
        destination_place,
        stops,
        intent.travel_mode,
        constraints,
        personalization,
        transcript,
        "",
        include_enrichment=False,
    )
    result.why_this_route = voice_route_reply(result.model_dump(mode="json"))
    return result
