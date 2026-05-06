from __future__ import annotations

import json
import re
from functools import cached_property

from google import genai
from google.genai import types

from app.config import get_settings
from app.schemas import VoiceRouteIntent


class GeminiTextService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @cached_property
    def client(self):
        return genai.Client(
            vertexai=self.settings.use_vertex_ai,
            credentials=self.settings.vertex_credentials(),
            project=self.settings.google_cloud_project,
            location=self.settings.vertex_text_location,
            http_options=types.HttpOptions(api_version="v1"),
        )

    def generate_route_rationale(self, route_payload: dict, personalization: dict, query_text: str | None) -> str:
        if not self.settings.use_vertex_ai or not self.settings.google_cloud_project:
            return self._fallback_rationale(route_payload, personalization)

        prompt = (
            "You are Route Genie, an AI-native travel planning assistant.\n"
            "Write a concise 2 sentence explanation for why this route fits the user.\n"
            "Clearly distinguish confirmed route facts from soft suggestions.\n"
            f"User query: {query_text or 'N/A'}\n"
            f"Personalization context: {personalization}\n"
            f"Confirmed route payload: {route_payload}\n"
        )
        try:
            response = self.client.models.generate_content(
                model=self.settings.gemini_text_model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.3),
            )
            if response.text:
                return response.text.strip()
        except Exception:
            pass
        return self._fallback_rationale(route_payload, personalization)

    def generate_trip_title(self, origin: str, destination: str, query_text: str | None) -> str:
        if query_text:
            normalized = query_text.strip().rstrip(".")
            if normalized:
                return normalized[:120]
        return f"{origin} to {destination}"

    def extract_route_intent(self, transcript: str) -> VoiceRouteIntent:
        cleaned = transcript.strip()
        if not cleaned:
            return VoiceRouteIntent(clarification_question="Say your start and destination.")

        spoken_intent = self._spoken_route_intent(cleaned)
        if spoken_intent.origin and spoken_intent.destination:
            return spoken_intent

        if not self.settings.use_vertex_ai or not self.settings.google_cloud_project:
            return self._fallback_intent(cleaned)

        prompt = (
            "Extract a navigation intent from this spoken route request.\n"
            "Return JSON only with keys: origin, destination, stop_query, travel_mode, avoid_tolls, avoid_highways, safety_mode, max_extra_minutes, clarification_question.\n"
            "Rules:\n"
            "- If origin or destination is missing, set clarification_question to one short question.\n"
            "- Put an intermediate stop request like 'via McDonald's' or 'pass by a fuel station' into stop_query.\n"
            "- travel_mode must be one of DRIVE, WALK, BICYCLE, TWO_WHEELER.\n"
            "- Infer avoid_tolls, avoid_highways, safety_mode, and max_extra_minutes when explicitly requested.\n"
            "- Do not add markdown.\n"
            f"Transcript: {cleaned}\n"
        )
        try:
            response = self.client.models.generate_content(
                model=self.settings.gemini_text_model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1),
            )
            if response.text:
                raw = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                payload = json.loads(raw)
                model_intent = VoiceRouteIntent(**payload)
                if self._looks_misparsed(model_intent):
                    return spoken_intent if spoken_intent.origin or spoken_intent.destination else self._fallback_intent(cleaned)
                return model_intent
        except Exception:
            pass
        return self._fallback_intent(cleaned)

    @staticmethod
    def _spoken_route_intent(transcript: str) -> VoiceRouteIntent:
        normalized = re.sub(r"\s+", " ", transcript).strip(" ,.")
        lowered = normalized.lower()

        match = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+)$", normalized, flags=re.IGNORECASE)
        if not match:
            return VoiceRouteIntent()

        origin = GeminiTextService._clean_spoken_place(match.group(1))
        destination_tail = match.group(2).strip()
        destination, stop_query = GeminiTextService._split_destination_and_stop(destination_tail)

        return VoiceRouteIntent(
            origin=origin,
            destination=GeminiTextService._clean_spoken_place(destination),
            stop_query=GeminiTextService._clean_stop_query(stop_query),
            travel_mode="TWO_WHEELER" if "bike" in lowered or "two wheeler" in lowered else "DRIVE",
            avoid_tolls="avoid toll" in lowered or "no toll" in lowered,
            avoid_highways="avoid highway" in lowered or "avoid highways" in lowered,
            safety_mode="safe" in lowered or "safer" in lowered,
        )

    @staticmethod
    def _split_destination_and_stop(destination_tail: str) -> tuple[str, str | None]:
        stop_patterns = [
            r"\s+(?:and\s+)?(?:in\s+between|between|on\s+the\s+way|along\s+the\s+way)\s+(?:i\s+want\s+to\s+)?(?:pass\s+by|go\s+via|via|stop\s+at|add)\s+(.+)$",
            r"\s+(?:and\s+)?(?:pass\s+by|go\s+via|via|stop\s+at|add)\s+(.+)$",
        ]
        for pattern in stop_patterns:
            match = re.search(pattern, destination_tail, flags=re.IGNORECASE)
            if match:
                destination = destination_tail[: match.start()].strip(" ,.")
                return destination, match.group(1)
        return destination_tail, None

    @staticmethod
    def _clean_spoken_place(text: str | None) -> str | None:
        if not text:
            return None
        cleaned = text.strip(" ,.")
        cleaned = re.sub(r"^(hey|hi|hello)\b[\s,]*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(i\s+want\s+to\s+go|i\s+want|can\s+you|could\s+you|please|tell\s+me|show\s+me|give\s+me|route)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
        return cleaned or None

    @staticmethod
    def _clean_stop_query(text: str | None) -> str | None:
        cleaned = GeminiTextService._clean_spoken_place(text)
        if not cleaned:
            return None
        cleaned = re.sub(r"\b(on my route|on the route|in between|between)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
        return cleaned or None

    @staticmethod
    def _looks_misparsed(intent: VoiceRouteIntent) -> bool:
        origin = (intent.origin or "").lower()
        destination = (intent.destination or "").lower()
        return (
            " to " in origin
            or " from " in destination
            or origin in {"hey i want", "i want", "hey"}
            or destination.startswith("go from ")
        )

    @staticmethod
    def _fallback_rationale(route_payload: dict, personalization: dict) -> str:
        distance = route_payload.get("distance_text", "the selected")
        duration = route_payload.get("duration_text", "the current")
        preference_hint = []
        if personalization.get("avoid_tolls"):
            preference_hint.append("your toll-avoidance setting")
        if personalization.get("safety_mode"):
            preference_hint.append("safer stop suggestions")
        if personalization.get("interests"):
            top_interest = sorted(personalization["interests"].items(), key=lambda item: item[1], reverse=True)[0][0]
            preference_hint.append(f"your recent interest in {top_interest.replace('_', ' ')}")
        suffix = ""
        if preference_hint:
            suffix = f" It also reflects {', '.join(preference_hint)}."
        return f"Confirmed route data shows a {distance} trip taking about {duration}.{suffix}"

    @staticmethod
    def _fallback_intent(transcript: str) -> VoiceRouteIntent:
        lowered = transcript.lower()
        separator = " to "
        if separator not in lowered:
            return VoiceRouteIntent(clarification_question="Say where you are starting and where you want to go.")
        parts = transcript.split(" to ", 1)
        origin = parts[0].replace("take me from", "").replace("route from", "").replace("go from", "").strip(" ,.")
        tail = parts[1]
        destination = tail.split(" and ", 1)[0].split(" with ", 1)[0].strip(" ,.")
        stop_query = None
        if "pass by " in lowered:
            stop_query = transcript.lower().split("pass by ", 1)[1].split(" and ", 1)[0].strip(" ,.")
        elif "via " in lowered:
            stop_query = transcript.lower().split("via ", 1)[1].split(" and ", 1)[0].strip(" ,.")
        return VoiceRouteIntent(
            origin=origin or None,
            destination=destination or None,
            stop_query=stop_query or None,
            avoid_tolls="avoid toll" in lowered,
            avoid_highways="avoid highway" in lowered or "avoid highways" in lowered,
            safety_mode="safe" in lowered or "safer" in lowered,
        )
