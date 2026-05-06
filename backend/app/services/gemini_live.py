from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from fastapi import HTTPException, WebSocket
from google import genai
from google.genai import live as live_module
from google.genai import types
from sqlalchemy.orm import Session
from websockets.exceptions import ConnectionClosed

from app.config import get_settings
from app.schemas import RouteConstraints, RoutePlace, TripCreateRequest
from app.services.auth import AuthService
from app.services.maps import MapsService
from app.services.personalization import build_personalization_context
from app.services.voice_planner import voice_route_reply


logger = logging.getLogger("uvicorn.error")

LIVE_SYSTEM_INSTRUCTION = """You are Route Genie, an AI-native voice-first trip planning and smart navigation assistant.

Rules:
- Never hallucinate route data, place details, tolls, timings, or stop ratings.
- For casual conversation, answer naturally and briefly without using route tools.
- Do not call route, place, history, personalization, or save tools for greetings, small talk, or general non-navigation questions.
- You decide when to call tools. Call route/place tools only when the user asks for navigation, trip planning, route comparison, route optimization, or stops.
- For route requests with "via", "pass by", "on the way", or "add a stop", find a concrete intermediate place and compute the route with that stop as an intermediate waypoint.
- Call save_trip only when the user explicitly asks to save the current trip.
- Ask at most one short clarification when absolutely necessary.
- Prefer the user's saved preferences and recent history when available.
- Keep confirmed route facts separate from suggestions.
- After route tools return data, speak a short route-found answer and keep it concise.
"""


class LiveSessionManager:
    def __init__(self, websocket: WebSocket, db: Session, user) -> None:
        self.websocket = websocket
        self.db = db
        self.user = user
        self.settings = get_settings()
        self.maps = MapsService()
        self.auth = AuthService(db)
        self.client = None
        self.session: live_module.AsyncSession | None = None
        self.live_model_name: str | None = None
        self.latest_route: dict[str, Any] | None = None
        self.input_transcript_parts: list[str] = []
        self.audio_chunks_received = 0
        self.audio_turn_buffer = bytearray()

    def build_live_session_response(self) -> dict[str, Any]:
        return {
            "live_model": self.live_model_name,
            "text_model": self.settings.gemini_text_model,
            "status": "ready" if not self.settings.runtime_validation_errors() else "degraded",
            "missing_config": self.settings.runtime_validation_errors(),
        }

    async def connect(self) -> str:
        self.client = genai.Client(
            vertexai=self.settings.use_vertex_ai,
            project=self.settings.google_cloud_project,
            location=self.settings.vertex_live_location,
            http_options=types.HttpOptions(api_version="v1beta1"),
        )
        last_error: Exception | None = None
        candidates = []
        primary = self.settings.gemini_live_model_primary
        fallback = self.settings.gemini_live_model_fallback
        if primary and primary.startswith("gemini-live-"):
            candidates.append(primary)
        candidates.append(fallback)
        for candidate in dict.fromkeys(candidates):
            try:
                config = self._live_config(candidate)
                self.session = await asyncio.wait_for(
                    self.client.aio.live.connect(model=candidate, config=config).__aenter__(),
                    timeout=8,
                )
                self.live_model_name = candidate
                return candidate
            except Exception as exc:
                last_error = exc
                continue
        detail = f"Unable to establish a Vertex Gemini Live session with the configured models"
        if last_error is not None:
            detail = f"{detail}: {last_error}"
        raise RuntimeError(detail)

    async def close(self) -> None:
        if self.session is not None:
            try:
                await self.session.close()
            except ConnectionClosed:
                pass
            except Exception as exc:
                logger.debug("Route Genie Live: session close ignored: %s", exc)

    async def pump_client_to_model(self) -> None:
        try:
            while True:
                message = await self.websocket.receive_text()
                data = json.loads(message)
                if data.get("type") == "audio":
                    decoded = base64.b64decode(data["data"])
                    self.audio_chunks_received += 1
                    if self.audio_chunks_received == 1:
                        logger.info("Route Genie Live: first audio chunk received")
                    elif self.audio_chunks_received % 20 == 0:
                        logger.info("Route Genie Live: received %s audio chunks", self.audio_chunks_received)
                    self.audio_turn_buffer.extend(decoded)
                elif data.get("type") == "text":
                    events = await self._run_text_turn(data["text"])
                    for event in events:
                        await self.websocket.send_text(json.dumps(event))
                elif data.get("type") == "end_audio":
                    logger.info("Route Genie Live: audio stream end after %s audio chunks", self.audio_chunks_received)
                    audio_payload = bytes(self.audio_turn_buffer)
                    self.audio_turn_buffer.clear()
                    if audio_payload:
                        events = await self._run_audio_turn(audio_payload)
                        for event in events:
                            await self.websocket.send_text(json.dumps(event))
        except (ConnectionClosed, RuntimeError):
            return
        except Exception as exc:
            logger.info("Route Genie Live: client audio pump stopped: %s", exc)
            try:
                await self.websocket.send_text(json.dumps({"type": "error", "detail": f"Live audio stream failed: {exc}"}))
            except Exception:
                pass
            return

    async def _run_audio_turn(self, audio_payload: bytes) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        client = genai.Client(
            vertexai=self.settings.use_vertex_ai,
            project=self.settings.google_cloud_project,
            location=self.settings.vertex_live_location,
            http_options=types.HttpOptions(api_version="v1beta1"),
        )
        model_name = self.live_model_name or self.settings.gemini_live_model_fallback
        logger.info("Route Genie Live: opening per-turn audio session (%s bytes)", len(audio_payload))
        async with client.aio.live.connect(model=model_name, config=self._live_config(model_name)) as session:
            await session.send_realtime_input(audio=types.Blob(data=audio_payload, mime_type="audio/pcm;rate=16000"))
            logger.info("Route Genie Live: per-turn audio forwarded to Vertex")
            async for message in session.receive():
                if message.tool_call:
                    responses = []
                    for call in message.tool_call.function_calls or []:
                        logger.info("Route Genie Live: model requested tool %s", call.name)
                        try:
                            payload = await self._run_tool(call.name, call.args or {}, emit_route=False)
                        except HTTPException as exc:
                            payload = {"error": exc.detail}
                        except Exception as exc:
                            logger.info("Route Genie Live: tool %s failed: %s", call.name, exc)
                            payload = {"error": str(exc)}
                        if call.name == "compute_route" and payload.get("result"):
                            events.append({"type": "route", "data": payload["result"]})
                        responses.append(types.FunctionResponse(id=call.id, name=call.name, response=payload))
                    if responses:
                        await session.send_tool_response(function_responses=responses)
                if message.server_content:
                    events.extend(self._server_content_events(message.server_content))
                    if message.server_content.turn_complete:
                        return events
        return events

    async def _run_text_turn(self, text: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        client = genai.Client(
            vertexai=self.settings.use_vertex_ai,
            project=self.settings.google_cloud_project,
            location=self.settings.vertex_live_location,
            http_options=types.HttpOptions(api_version="v1beta1"),
        )
        model_name = self.live_model_name or self.settings.gemini_live_model_fallback
        async with client.aio.live.connect(model=model_name, config=self._live_config(model_name)) as session:
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=text)]),
                turn_complete=True,
            )
            async for message in session.receive():
                if message.server_content:
                    events.extend(self._server_content_events(message.server_content))
                    if message.server_content.turn_complete:
                        return events
        return events

    async def receive_model_turn(self) -> None:
        assert self.session is not None
        try:
            async for message in self.session.receive():
                if message.tool_call:
                    await self._handle_tool_calls(message.tool_call)
                if message.server_content:
                    await self._handle_server_content(message.server_content)
                    if message.server_content.turn_complete:
                        return
        except ConnectionClosed:
            return
        except Exception as exc:
            logger.info("Route Genie Live: model stream closed: %s", exc)
            return

    async def _handle_tool_calls(self, tool_call: types.LiveServerToolCall) -> None:
        assert self.session is not None
        responses = []
        for call in tool_call.function_calls or []:
            logger.info("Route Genie Live: model requested tool %s", call.name)
            try:
                payload = await self._run_tool(call.name, call.args or {})
            except HTTPException as exc:
                payload = {"error": exc.detail}
            except Exception as exc:
                logger.info("Route Genie Live: tool %s failed: %s", call.name, exc)
                payload = {"error": str(exc)}
            responses.append(types.FunctionResponse(id=call.id, name=call.name, response=payload))
        if responses:
            await self.session.send_tool_response(function_responses=responses)

    async def _run_tool(self, name: str, args: dict[str, Any], emit_route: bool = True) -> dict[str, Any]:
        personalization = self._personalization_context()
        if name == "resolve_place":
            result = await self.maps.resolve_place(RoutePlace(**args))
            return {"result": result}
        if name == "search_places":
            result = await self.maps.search_places(
                args.get("query", ""),
                args.get("location_bias"),
                args.get("included_types") or [],
                args.get("max_result_count", 5),
            )
            return {"result": [item.model_dump() for item in result]}
        if name == "compute_route":
            constraints = RouteConstraints(**(args.get("preferences") or {}))
            route = await self.maps.compute_trip(
                origin=RoutePlace(**args["origin"]),
                destination=RoutePlace(**args["destination"]),
                stops=[RoutePlace(**stop) for stop in args.get("stops", [])],
                travel_mode=args.get("travel_mode", "DRIVE"),
                constraints=constraints,
                personalization=personalization,
                query_text=args.get("query_text"),
                rationale="",
                include_enrichment=False,
            )
            route.why_this_route = voice_route_reply(route.model_dump(mode="json"))
            self.latest_route = route.model_dump(mode="json")
            if emit_route:
                await self.websocket.send_text(json.dumps({"type": "route", "data": self.latest_route}))
            return {"result": self.latest_route}
        if name == "optimize_stops":
            constraints = RouteConstraints(**(args.get("preferences") or {}))
            result = await self.maps.optimize_stops(
                origin=RoutePlace(**args["origin"]),
                destination=RoutePlace(**args["destination"]),
                candidate_stops=[RoutePlace(**stop) for stop in args.get("candidate_stops", [])],
                travel_mode=args.get("travel_mode", "DRIVE"),
                constraints=constraints,
            )
            return {"result": result}
        if name == "save_trip":
            if self.user is None:
                return {"error": "Authentication required to save trips"}
            trip_payload = args.get("trip_data") or {}
            trip = self.auth.save_trip(
                self.user,
                TripCreateRequest(**trip_payload),
            )
            return {"result": {"trip_id": str(trip.id), "title": trip.title}}
        if name == "get_user_history":
            if self.user is None:
                return {"result": {"recent_trips": [], "recent_searches": []}}
            context = self.auth.build_user_context(self.user)
            return {"result": context.model_dump(mode="json")}
        if name == "personalize_route":
            return {"result": personalization}
        return {"error": f"Unknown tool '{name}'"}

    async def _handle_server_content(self, content: types.LiveServerContent) -> None:
        for event in self._server_content_events(content):
            await self.websocket.send_text(json.dumps(event))

    def _server_content_events(self, content: types.LiveServerContent) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if content.input_transcription and content.input_transcription.text:
            logger.info("Route Genie Live: input transcript received")
            self.input_transcript_parts.append(content.input_transcription.text)
            events.append(
                {
                    "type": "transcript",
                    "role": "user",
                    "text": content.input_transcription.text,
                    "final": content.input_transcription.finished,
                }
            )
        if content.output_transcription and content.output_transcription.text:
            logger.info("Route Genie Live: output transcript received")
            events.append(
                {
                    "type": "transcript",
                    "role": "assistant",
                    "text": content.output_transcription.text,
                    "final": content.output_transcription.finished,
                }
            )
        if content.model_turn and content.model_turn.parts:
            for part in content.model_turn.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("audio/pcm"):
                    logger.info("Route Genie Live: output audio received")
                    events.append(
                        {
                            "type": "audio",
                            "data": base64.b64encode(part.inline_data.data).decode("ascii"),
                        }
                    )
                if part.text:
                    logger.info("Route Genie Live: output text received")
                    events.append({"type": "assistant_text", "text": part.text})
        if content.turn_complete:
            logger.info("Route Genie Live: turn complete")
            events.append({"type": "turn_complete"})
        return events

    def _live_config(self, model_name: str) -> types.LiveConnectConfig:
        response_modalities = ["AUDIO", "TEXT"]
        tools = [
            types.Tool(
                function_declarations=[
                    self._function(
                        "resolve_place",
                        "Resolve a place query into a canonical place or coordinates.",
                        {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "place_id": {"type": "string"},
                                "latitude": {"type": "number"},
                                "longitude": {"type": "number"},
                            },
                        },
                    ),
                    self._function(
                        "search_places",
                        "Search for places such as cafes, EV charging, food, scenic stops, fuel, restrooms, shopping, hotels, and emergency options.",
                        {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "location_bias": {"type": "object"},
                                "included_types": {"type": "array", "items": {"type": "string"}},
                                "max_result_count": {"type": "integer"},
                            },
                            "required": ["query"],
                        },
                    ),
                    self._function(
                        "compute_route",
                        "Compute a route with optional stops and preferences. This must be used for all route facts.",
                        {
                            "type": "object",
                            "properties": {
                                "origin": {"type": "object"},
                                "destination": {"type": "object"},
                                "stops": {"type": "array", "items": {"type": "object"}},
                                "travel_mode": {"type": "string"},
                                "preferences": {"type": "object"},
                                "query_text": {"type": "string"},
                            },
                            "required": ["origin", "destination"],
                        },
                    ),
                    self._function(
                        "optimize_stops",
                        "Optimize candidate stops between an origin and destination.",
                        {
                            "type": "object",
                            "properties": {
                                "origin": {"type": "object"},
                                "destination": {"type": "object"},
                                "candidate_stops": {"type": "array", "items": {"type": "object"}},
                                "travel_mode": {"type": "string"},
                                "preferences": {"type": "object"},
                            },
                            "required": ["origin", "destination", "candidate_stops"],
                        },
                    ),
                    self._function(
                        "save_trip",
                        "Save a confirmed trip for the authenticated user. Use only when the user explicitly asks to save the trip.",
                        {
                            "type": "object",
                            "properties": {"trip_data": {"type": "object"}},
                            "required": ["trip_data"],
                        },
                    ),
                    self._function(
                        "get_user_history",
                        "Get recent trips, searches, and preferences for the authenticated user.",
                        {"type": "object", "properties": {}},
                    ),
                    self._function(
                        "personalize_route",
                        "Get personalization context for the current query and user.",
                        {
                            "type": "object",
                            "properties": {"current_query": {"type": "string"}},
                        },
                    ),
                ]
            )
        ]
        if "native-audio" in model_name:
            response_modalities = ["AUDIO"]
            tools = None
        config_kwargs: dict[str, Any] = {
            "response_modalities": response_modalities,
            "input_audio_transcription": {},
            "output_audio_transcription": {},
            "realtime_input_config": types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=False,
                ),
                activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
                turn_coverage=types.TurnCoverage.TURN_INCLUDES_ALL_INPUT,
            ),
            "system_instruction": LIVE_SYSTEM_INSTRUCTION,
        }
        if tools is not None:
            config_kwargs["tools"] = tools
        return types.LiveConnectConfig(**config_kwargs)

    def _personalization_context(self) -> dict[str, Any]:
        if self.user is None or self.user.preferences is None:
            return {"enabled": False, "interests": {}, "recent_trips": [], "recent_queries": []}
        trips = list(self.user.trips or [])[:5]
        searches = list(self.user.searches or [])[:5]
        return build_personalization_context(self.user.preferences, trips, searches)

    @staticmethod
    def _function(name: str, description: str, parameters_json_schema: dict[str, Any]) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=name,
            description=description,
            parameters_json_schema=parameters_json_schema,
        )


async def run_live_session(websocket: WebSocket, db: Session, user) -> None:
    loop = asyncio.get_running_loop()
    previous_exception_handler = loop.get_exception_handler()

    def _ignore_google_live_close_noise(loop, context):
        message = str(context.get("message") or "")
        exception = context.get("exception")
        if message.startswith("ConnectionClosedError exception in shielded future") or isinstance(exception, ConnectionClosed):
            logger.debug("Route Genie Live: ignored SDK close noise: %s", message or exception)
            return
        if previous_exception_handler:
            previous_exception_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(_ignore_google_live_close_noise)
    manager = LiveSessionManager(websocket, db, user)
    logger.info("Route Genie Live: starting Vertex Live session")
    await manager.connect()
    logger.info("Route Genie Live: session ready %s", manager.live_model_name)
    await manager.close()
    manager.session = None
    await websocket.send_text(json.dumps({"type": "session_ready", "data": manager.build_live_session_response()}))
    logger.info("Route Genie Live: sent session_ready to browser")
    receive_task = asyncio.create_task(manager.pump_client_to_model())
    try:
        done, pending = await asyncio.wait([receive_task], return_when=asyncio.FIRST_EXCEPTION)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            try:
                task.result()
                logger.info("Route Genie Live: task completed without exception")
            except Exception as exc:
                logger.info("Route Genie Live: task ended: %s", exc)
    finally:
        await manager.close()
        loop.set_exception_handler(previous_exception_handler)
