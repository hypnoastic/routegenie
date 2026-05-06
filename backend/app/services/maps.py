from __future__ import annotations

import asyncio
from datetime import datetime
from math import isfinite
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import get_settings
from app.schemas import PlaceSuggestion, RouteConstraints, RouteLeg, RouteOption, RoutePlace, RouteResult


TRAVEL_MODE_MAP = {
    "DRIVE": "DRIVE",
    "DRIVING": "DRIVE",
    "WALK": "WALK",
    "WALKING": "WALK",
    "BICYCLE": "BICYCLE",
    "BIKE": "BICYCLE",
    "TWO_WHEELER": "TWO_WHEELER",
}


class MapsService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.api_key = self.settings.google_maps_server_api_key

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def autocomplete(self, input_text: str, session_token: str | None, location_bias: dict | None) -> list[PlaceSuggestion]:
        payload: dict[str, Any] = {"input": input_text}
        if session_token:
            payload["sessionToken"] = session_token
        if location_bias:
            payload["locationBias"] = location_bias
        data = await self._post_json(
            "https://places.googleapis.com/v1/places:autocomplete",
            payload,
            headers={
                "X-Goog-FieldMask": "suggestions.placePrediction.placeId,suggestions.placePrediction.text.text,suggestions.placePrediction.structuredFormat.mainText.text,suggestions.placePrediction.structuredFormat.secondaryText.text,suggestions.queryPrediction.text.text"
            },
        )
        suggestions: list[PlaceSuggestion] = []
        for item in data.get("suggestions", []):
            place_prediction = item.get("placePrediction")
            query_prediction = item.get("queryPrediction")
            if place_prediction:
                secondary = place_prediction.get("structuredFormat", {}).get("secondaryText", {}).get("text")
                suggestions.append(
                    PlaceSuggestion(
                        place_id=place_prediction.get("placeId"),
                        name=place_prediction.get("text", {}).get("text") or place_prediction.get("structuredFormat", {}).get("mainText", {}).get("text") or "Unknown place",
                        formatted_address=secondary,
                        source="autocomplete",
                    )
                )
            elif query_prediction:
                suggestions.append(
                    PlaceSuggestion(
                        name=query_prediction.get("text", {}).get("text", input_text),
                        source="autocomplete",
                    )
                )
        return suggestions

    async def search_places(self, query: str, location_bias: dict | None = None, included_types: list[str] | None = None, max_result_count: int = 5) -> list[PlaceSuggestion]:
        payload: dict[str, Any] = {
            "textQuery": query,
            "maxResultCount": max_result_count,
            "rankPreference": "RELEVANCE",
        }
        if location_bias:
            payload["locationBias"] = location_bias
        if included_types:
            payload["includedType"] = included_types[0]
        data = await self._post_json(
            "https://places.googleapis.com/v1/places:searchText",
            payload,
            headers={
                "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.types"
            },
        )
        return [self._place_from_text_search(place) for place in data.get("places", [])]

    async def resolve_place(self, place: RoutePlace) -> dict[str, Any]:
        if place.latitude is not None and place.longitude is not None and isfinite(place.latitude) and isfinite(place.longitude):
            return {
                "place_id": place.place_id,
                "text": place.text or "Pinned location",
                "formatted_address": place.text or "Pinned location",
                "latitude": place.latitude,
                "longitude": place.longitude,
            }

        if place.place_id:
            data = await self._get_json(
                f"https://places.googleapis.com/v1/places/{place.place_id}",
                headers={
                    "X-Goog-FieldMask": "id,displayName,formattedAddress,location,types"
                },
            )
            location = data.get("location", {})
            return {
                "place_id": data.get("id"),
                "text": data.get("displayName", {}).get("text") or place.text,
                "formatted_address": data.get("formattedAddress") or place.text,
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
            }

        if not place.text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Place text is required")

        data = await self._get_json(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": place.text, "key": self.api_key},
            passthrough_google_errors=True,
        )
        results = data.get("results", [])
        if not results:
            fallback = await self.search_places(place.text, max_result_count=1)
            if fallback:
                candidate = fallback[0]
                return {
                    "place_id": candidate.place_id,
                    "text": candidate.name or place.text,
                    "formatted_address": candidate.formatted_address or candidate.name or place.text,
                    "latitude": candidate.latitude,
                    "longitude": candidate.longitude,
                }
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Could not resolve place '{place.text}'")
        top = results[0]
        location = top.get("geometry", {}).get("location", {})
        return {
            "place_id": top.get("place_id"),
            "text": place.text,
            "formatted_address": top.get("formatted_address") or place.text,
            "latitude": location.get("lat"),
            "longitude": location.get("lng"),
        }

    async def compute_trip(
        self,
        origin: RoutePlace,
        destination: RoutePlace,
        stops: list[RoutePlace],
        travel_mode: str,
        constraints: RouteConstraints,
        personalization: dict,
        query_text: str | None,
        rationale: str,
        include_enrichment: bool = True,
    ) -> RouteResult:
        resolved_origin, resolved_destination, resolved_stops = await asyncio.gather(
            self.resolve_place(origin),
            self.resolve_place(destination),
            asyncio.gather(*[self.resolve_place(stop) for stop in stops]) if stops else asyncio.sleep(0, result=[]),
        )

        base_route = await self._compute_routes_request(
            resolved_origin,
            resolved_destination,
            resolved_stops,
            travel_mode,
            constraints,
            compute_alternatives=include_enrichment,
        )
        route_data = self._parse_primary_route(base_route, resolved_stops, travel_mode)
        comparison_options = self._parse_comparison_options(base_route)

        if include_enrichment:
            toll_variant = await self._compute_routes_request(
                resolved_origin,
                resolved_destination,
                resolved_stops,
                travel_mode,
                RouteConstraints(
                    avoid_tolls=True,
                    avoid_highways=constraints.avoid_highways,
                    max_extra_minutes=constraints.max_extra_minutes,
                    safety_mode=constraints.safety_mode,
                ),
                compute_alternatives=False,
            )
            comparison_options.append(self._single_variant_option("fewer-tolls", "Fewer tolls", toll_variant))
            comparison_options.append(self._single_variant_option("cheaper", "Cheaper", toll_variant, note="Uses the lower-toll route when available."))
            route_data.smart_stop_suggestions = await self._build_smart_stops(base_route, resolved_origin, resolved_destination, query_text, personalization, constraints)
        else:
            route_data.smart_stop_suggestions = []
        route_data.comparison_options = comparison_options
        route_data.why_this_route = rationale
        route_data.route_summary = f"{route_data.distance_text} in about {route_data.duration_text}"
        route_data.origin = resolved_origin.get("formatted_address") or route_data.origin
        route_data.destination = resolved_destination.get("formatted_address") or route_data.destination
        route_data.confirmed_route_data["constraints"] = constraints.model_dump()
        route_data.confirmed_route_data["origin_resolved"] = resolved_origin
        route_data.confirmed_route_data["destination_resolved"] = resolved_destination
        route_data.suggestion_notes = self._suggestion_notes(constraints, personalization)
        return route_data

    async def optimize_stops(self, origin: RoutePlace, destination: RoutePlace, candidate_stops: list[RoutePlace], travel_mode: str, constraints: RouteConstraints) -> list[dict[str, Any]]:
        resolved_origin = await self.resolve_place(origin)
        resolved_destination = await self.resolve_place(destination)
        resolved_stops = [await self.resolve_place(stop) for stop in candidate_stops]
        if not resolved_stops:
            return []

        direct_route = await self._compute_routes_request(resolved_origin, resolved_destination, [], travel_mode, constraints, compute_alternatives=False)
        direct_duration = direct_route["routes"][0]["duration"]
        baseline_seconds = int(direct_duration.rstrip("s"))

        scored: list[dict[str, Any]] = []
        for stop in resolved_stops:
            matrix = await self._compute_route_matrix_request(
                [resolved_origin, stop],
                [stop, resolved_destination],
                travel_mode,
            )
            detour = self._estimate_detour_seconds(matrix, baseline_seconds)
            scored.append({**stop, "detour_seconds": detour})
        scored.sort(key=lambda item: item["detour_seconds"])
        return scored

    async def _compute_routes_request(self, origin: dict[str, Any], destination: dict[str, Any], stops: list[dict[str, Any]], travel_mode: str, constraints: RouteConstraints, compute_alternatives: bool) -> dict[str, Any]:
        mode = TRAVEL_MODE_MAP.get(travel_mode.upper(), "DRIVE")
        payload: dict[str, Any] = {
            "origin": self._waypoint(origin),
            "destination": self._waypoint(destination),
            "travelMode": mode,
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL" if mode == "DRIVE" else "TRAFFIC_UNAWARE",
            "routeModifiers": {
                "avoidTolls": constraints.avoid_tolls,
                "avoidHighways": constraints.avoid_highways,
            },
            "computeAlternativeRoutes": compute_alternatives,
            "polylineEncoding": "ENCODED_POLYLINE",
            "polylineQuality": "HIGH_QUALITY",
            "languageCode": "en-US",
            "units": "METRIC",
            "extraComputations": ["TOLLS"] if mode == "DRIVE" else [],
        }
        if stops:
            payload["intermediates"] = [self._waypoint(stop) for stop in stops]

        return await self._post_json(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            payload,
            headers={
                "X-Goog-FieldMask": ",".join(
                    [
                        "routes.duration",
                        "routes.distanceMeters",
                        "routes.polyline.encodedPolyline",
                        "routes.legs",
                        "routes.legs.distanceMeters",
                        "routes.legs.duration",
                        "routes.legs.startLocation",
                        "routes.legs.endLocation",
                        "routes.localizedValues.distance",
                        "routes.localizedValues.duration",
                        "routes.travelAdvisory.tollInfo",
                        "routes.routeLabels",
                    ]
                )
            },
        )

    async def _compute_route_matrix_request(self, origins: list[dict[str, Any]], destinations: list[dict[str, Any]], travel_mode: str) -> list[dict[str, Any]]:
        payload = {
            "origins": [{"waypoint": self._waypoint(origin)} for origin in origins],
            "destinations": [{"waypoint": self._waypoint(destination)} for destination in destinations],
            "travelMode": TRAVEL_MODE_MAP.get(travel_mode.upper(), "DRIVE"),
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        }
        data = await self._post_json(
            "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix",
            payload,
            headers={
                "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters,status,condition"
            },
        )
        return data if isinstance(data, list) else []

    def _parse_primary_route(self, response: dict[str, Any], resolved_stops: list[dict[str, Any]], travel_mode: str) -> RouteResult:
        routes = response.get("routes", [])
        if not routes:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No route found")
        route = routes[0]
        duration_seconds = int(route.get("duration", "0s").rstrip("s") or 0)
        arrival = datetime.utcnow().isoformat(timespec="minutes") + "Z"
        legs = [
            RouteLeg(
                start_address=self._format_leg_endpoint(leg.get("startLocation")),
                end_address=self._format_leg_endpoint(leg.get("endLocation")),
                distance_text=self._meters_to_text(leg.get("distanceMeters", 0)),
                duration_text=self._seconds_to_text(int(leg.get("duration", "0s").rstrip("s") or 0)),
            )
            for leg in route.get("legs", [])
        ]
        stops = [
            PlaceSuggestion(
                place_id=stop.get("place_id"),
                name=stop.get("text") or stop.get("formatted_address") or "Stop",
                formatted_address=stop.get("formatted_address"),
                latitude=stop.get("latitude"),
                longitude=stop.get("longitude"),
                source="text_search",
            )
            for stop in resolved_stops
        ]
        return RouteResult(
            origin=legs[0].start_address if legs else "Origin",
            destination=legs[-1].end_address if legs else "Destination",
            travel_mode=travel_mode,
            distance_text=self._meters_to_text(route.get("distanceMeters", 0)),
            duration_text=self._seconds_to_text(duration_seconds),
            duration_minutes=max(1, duration_seconds // 60),
            arrival_time=arrival,
            polyline=route.get("polyline", {}).get("encodedPolyline"),
            legs=legs,
            stops=stops,
            smart_stop_suggestions=[],
            comparison_options=[],
            why_this_route="",
            route_summary="",
            confirmed_route_data={
                "distance_meters": route.get("distanceMeters", 0),
                "duration_seconds": duration_seconds,
                "polyline": route.get("polyline", {}).get("encodedPolyline"),
                "legs": route.get("legs", []),
                "travel_advisory": route.get("travelAdvisory", {}),
            },
        )

    def _parse_comparison_options(self, response: dict[str, Any]) -> list[RouteOption]:
        options: list[RouteOption] = []
        for index, route in enumerate(response.get("routes", [])[:3]):
            label = "Fastest" if index == 0 else f"Option {index + 1}"
            route_labels = route.get("routeLabels", [])
            if "DEFAULT_ROUTE" in route_labels:
                label = "Fastest"
            options.append(
                RouteOption(
                    id=f"route-{index}",
                    label=label,
                    distance_text=self._meters_to_text(route.get("distanceMeters", 0)),
                    duration_text=self._seconds_to_text(int(route.get("duration", "0s").rstrip("s") or 0)),
                    arrival_time=None,
                    polyline=route.get("polyline", {}).get("encodedPolyline"),
                    note="Confirmed route option from Google Routes API.",
                )
            )
        return options

    def _single_variant_option(self, option_id: str, label: str, response: dict[str, Any], note: str | None = None) -> RouteOption:
        route = response.get("routes", [{}])[0]
        return RouteOption(
            id=option_id,
            label=label,
            distance_text=self._meters_to_text(route.get("distanceMeters", 0)),
            duration_text=self._seconds_to_text(int(route.get("duration", "0s").rstrip("s") or 0)),
            polyline=route.get("polyline", {}).get("encodedPolyline"),
            note=note or "Confirmed route option from Google Routes API.",
        )

    async def _build_smart_stops(self, base_route: dict[str, Any], origin: dict[str, Any], destination: dict[str, Any], query_text: str | None, personalization: dict, constraints: RouteConstraints) -> list[PlaceSuggestion]:
        categories = self._infer_categories(query_text, personalization)
        suggestions: list[PlaceSuggestion] = []
        midpoint = self._route_midpoint(base_route)
        for category in categories[:3]:
            query = self._category_query(category)
            results = await self.search_places(
                query,
                location_bias={
                    "circle": {
                        "center": {
                            "latitude": midpoint["latitude"],
                            "longitude": midpoint["longitude"],
                        },
                        "radius": 25000.0,
                    }
                },
                max_result_count=3,
            )
            if constraints.safety_mode:
                results = [item for item in results if (item.rating or 0) >= 4.0]
            if results:
                result = results[0]
                result.source = "text_search"
                suggestions.append(result)
        if not suggestions:
            suggestions = await self.search_places("best rest stop", max_result_count=3)
        return suggestions[:3]

    def _estimate_detour_seconds(self, matrix_rows: list[dict[str, Any]], baseline_seconds: int) -> int:
        origin_to_stop = 0
        stop_to_destination = 0
        for row in matrix_rows:
            duration = int(str(row.get("duration", "0s")).rstrip("s") or 0)
            if row.get("originIndex") == 0 and row.get("destinationIndex") == 0:
                origin_to_stop = duration
            if row.get("originIndex") == 1 and row.get("destinationIndex") == 1:
                stop_to_destination = duration
        return max(0, origin_to_stop + stop_to_destination - baseline_seconds)

    def _waypoint(self, place: dict[str, Any]) -> dict[str, Any]:
        return {
            "location": {
                "latLng": {
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                }
            }
        }

    def _place_from_text_search(self, place: dict[str, Any]) -> PlaceSuggestion:
        location = place.get("location", {})
        return PlaceSuggestion(
            place_id=place.get("id"),
            name=place.get("displayName", {}).get("text", "Unknown place"),
            formatted_address=place.get("formattedAddress"),
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
            rating=place.get("rating"),
            types=place.get("types", []),
            source="text_search",
        )

    @staticmethod
    def _meters_to_text(meters: int) -> str:
        return f"{meters / 1000:.1f} km"

    @staticmethod
    def _seconds_to_text(seconds: int) -> str:
        hours, remainder = divmod(seconds, 3600)
        minutes = max(1, remainder // 60)
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    @staticmethod
    def _format_leg_endpoint(location: dict[str, Any] | None) -> str:
        latlng = (location or {}).get("latLng", {})
        lat = latlng.get("latitude")
        lng = latlng.get("longitude")
        if lat is None or lng is None:
            return "Waypoint"
        return f"{lat:.4f}, {lng:.4f}"

    @staticmethod
    def _route_midpoint(base_route: dict[str, Any]) -> dict[str, float]:
        legs = base_route.get("routes", [{}])[0].get("legs", [])
        if not legs:
            return {"latitude": 28.6139, "longitude": 77.2090}
        start = legs[0].get("startLocation", {}).get("latLng", {})
        end = legs[-1].get("endLocation", {}).get("latLng", {})
        return {
            "latitude": ((start.get("latitude") or 0) + (end.get("latitude") or 0)) / 2,
            "longitude": ((start.get("longitude") or 0) + (end.get("longitude") or 0)) / 2,
        }

    @staticmethod
    def _infer_categories(query_text: str | None, personalization: dict) -> list[str]:
        haystack = (query_text or "").lower()
        categories: list[str] = []
        for category in ["food", "fuel", "ev_charging", "restroom", "scenic", "shopping", "hotel", "emergency"]:
            if category.replace("_", " ") in haystack or category in haystack:
                categories.append(category)
        interests = personalization.get("interests") or {}
        categories.extend([key for key, _ in sorted(interests.items(), key=lambda item: item[1], reverse=True)[:2]])
        if not categories:
            categories = ["food", "fuel", "ev_charging"]
        # Preserve order while removing duplicates.
        deduped = []
        for category in categories:
            if category not in deduped:
                deduped.append(category)
        return deduped

    @staticmethod
    def _category_query(category: str) -> str:
        mapping = {
            "food": "good food stop",
            "fuel": "fuel station",
            "ev_charging": "ev charging station",
            "restroom": "rest stop",
            "scenic": "scenic viewpoint",
            "shopping": "shopping stop",
            "hotel": "hotel",
            "emergency": "urgent care",
            "cafe": "cafe",
        }
        return mapping.get(category, category.replace("_", " "))

    @staticmethod
    def _suggestion_notes(constraints: RouteConstraints, personalization: dict) -> list[str]:
        notes = [
            "Confirmed route data comes from Google Routes API.",
            "Smart stop suggestions are ranked suggestions and may require confirmation.",
        ]
        if constraints.safety_mode:
            notes.append("Safety mode prefers well-rated public places and main-road style detours when possible.")
        if personalization.get("enabled"):
            notes.append("Personalization is based on lightweight recent history and saved preferences.")
        return notes

    async def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> Any:
        self._ensure_key()
        request_headers = {"X-Goog-Api-Key": self.api_key, "Content-Type": "application/json", **headers}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=request_headers)
        return self._handle_response(response)

    async def _get_json(self, url: str, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None, passthrough_google_errors: bool = False) -> Any:
        self._ensure_key()
        request_headers = headers or {}
        if "maps.googleapis.com" not in url:
            request_headers = {"X-Goog-Api-Key": self.api_key, **request_headers}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=request_headers, params=params)
        return self._handle_response(response, passthrough_google_errors=passthrough_google_errors)

    def _handle_response(self, response: httpx.Response, passthrough_google_errors: bool = False) -> Any:
        if response.status_code >= 400:
            detail = response.text
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Google Maps API error: {detail}")
        data = response.json()
        if passthrough_google_errors and data.get("status") not in (None, "OK"):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Google Maps API error: {data.get('status')}")
        return data

    def _ensure_key(self) -> None:
        if not self.api_key:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GOOGLE_MAPS_SERVER_API_KEY is not configured")
