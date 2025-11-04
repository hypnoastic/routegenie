import os
import json
import asyncio
import base64
import warnings
from pathlib import Path
from dotenv import load_dotenv
import googlemaps
from datetime import datetime
import threading

load_dotenv()

from google.genai import types
from google.genai.types import Part, Content, Blob
from google.adk.runners import Runner
from google.adk.agents import Agent, LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools import FunctionTool
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocketDisconnect

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Initialize Google Maps client
gmaps = googlemaps.Client(key=os.getenv("GOOGLE_MAPS_API_KEY"))

# Global route storage with thread lock
route_lock = threading.Lock()
latest_route_data = {}

def get_directions(origin: str, destination: str, mode: str = "driving") -> str:
    """
    Get directions from origin to destination.
    """
    global latest_route_data
    
    try:
        print(f"\n🗺️ 🔧 TOOL CALLED: get_directions('{origin}' → '{destination}')")
        
        directions = gmaps.directions(
            origin,
            destination,
            mode=mode,
            departure_time=datetime.now()
        )
        
        if not directions:
            return json.dumps({"error": "No route found"})
        
        route = directions[0]
        leg = route['legs'][0]
        
        # Create result
        result = {
            "status": "success",
            "origin": leg['start_address'],
            "destination": leg['end_address'],
            "distance": leg['distance']['text'],
            "duration": leg['duration']['text'],
            "polyline": route['overview_polyline']['points'],
            "steps": [],
            "stops": []
        }
        
        # Store globally for retrieval
        with route_lock:
            latest_route_data['current'] = result
        
        # Get steps
        for step in leg['steps'][:3]:
            result['steps'].append({
                "instruction": step['html_instructions'].replace('<b>', '').replace('</b>', ''),
                "distance": step['distance']['text'],
                "duration": step['duration']['text']
            })
        
        print(f"✅ ROUTE FOUND: {result['distance']}, {result['duration']}")
        print(f"✅ Polyline length: {len(result['polyline'])} chars\n")
        
        return json.dumps(result)
        
    except Exception as e:
        print(f"❌ Tool Error: {str(e)}\n")
        return json.dumps({"status": "error", "error": str(e)})

def find_nearby_stops(place_name: str, location: str, radius: int = 5000) -> str:
    """
    Find nearby places of a specific type near a location.
    
    Args:
        place_name: Type of place (e.g., "McDonald's", "gas station", "restaurant")
        location: The location to search around (address or coordinates)
        radius: Search radius in meters (default 5000m = 5km)
    
    Returns:
        JSON with nearby places information
    """
    try:
        print(f"\n🔍 🔧 TOOL CALLED: find_nearby_stops('{place_name}' near '{location}')")
        
        # First geocode the location to get coordinates
        geocode_result = gmaps.geocode(location)
        
        if not geocode_result:
            return json.dumps({"error": f"Location '{location}' not found"})
        
        location_coords = geocode_result[0]['geometry']['location']
        location_name = geocode_result[0]['formatted_address']
        
        print(f"📍 Location found: {location_name}")
        
        # Search for nearby places
        try:
            nearby_result = gmaps.places_nearby(
                location=(location_coords['lat'], location_coords['lng']),
                radius=radius,
                keyword=place_name,
                open_now=False
            )
            
            if not nearby_result['results']:
                return json.dumps({
                    "error": f"No {place_name} found near {location_name}",
                    "status": "not_found"
                })
            
            stops = []
            
            # Get top 3 results
            for place in nearby_result['results'][:3]:
                stop_info = {
                    "name": place.get('name', 'Unknown'),
                    "address": place.get('vicinity', 'Address not available'),
                    "lat": place['geometry']['location']['lat'],
                    "lng": place['geometry']['location']['lng'],
                    "distance": place.get('distance', 'N/A'),
                    "rating": place.get('rating', 'N/A'),
                    "open_now": place.get('opening_hours', {}).get('open_now', 'N/A')
                }
                stops.append(stop_info)
            
            result = {
                "status": "success",
                "place_type": place_name,
                "location_searched": location_name,
                "stops_found": len(stops),
                "stops": stops
            }
            
            print(f"✅ FOUND {len(stops)} stops")
            for i, stop in enumerate(stops, 1):
                print(f"   {i}. {stop['name']} - {stop['address']}")
            print()
            
            # Store stops in route data
            with route_lock:
                if 'current' in latest_route_data:
                    latest_route_data['current']['stops'] = stops
            
            return json.dumps(result)
            
        except Exception as e:
            print(f"❌ Places search error: {str(e)}\n")
            return json.dumps({"error": f"Error searching for places: {str(e)}"})
        
    except Exception as e:
        print(f"❌ Tool Error: {str(e)}\n")
        return json.dumps({"status": "error", "error": str(e)})

# Create tools
directions_tool = FunctionTool(func=get_directions)
stops_tool = FunctionTool(func=find_nearby_stops)

APP_NAME = "gemini-maps-assistant"
session_service = InMemorySessionService()

root_agent = Agent(
    name="maps_assistant",
    model=os.getenv("DEMO_AGENT_MODEL", "gemini-2.0-flash-exp"),
    description="Navigation assistant using Google Maps.",
    instruction="""You are a navigation assistant. When users ask for directions:
1. Use get_directions tool to find the route
2. If they mention stops/places they want to visit, use find_nearby_stops tool
3. Respond with SHORT sentences: "Route found: [distance] in [duration]" and "Found [stop name] as a stop"
4. Be conversational and brief.
""",
    tools=[directions_tool, stops_tool]
)

runner = Runner(
    app_name=APP_NAME,
    agent=root_agent,
    session_service=session_service,
)

async def start_agent_session(user_id, is_audio=False):
    """Starts an ADK agent session"""
    session_id = f"{APP_NAME}_{user_id}"
    session = await runner.session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    
    if not session:
        session = await runner.session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
    
    model_name = root_agent.model if isinstance(root_agent.model, str) else root_agent.model.model
    is_native_audio = "native-audio" in model_name.lower()
    modality = "AUDIO" if (is_audio or is_native_audio) else "TEXT"
    
    run_config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=[modality],
        session_resumption=types.SessionResumptionConfig(),
    )
    
    live_request_queue = LiveRequestQueue()
    
    live_events = runner.run_live(
        user_id=user_id,
        session_id=session.id,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    
    return live_events, live_request_queue

async def agent_to_client_messaging(websocket, live_events, user_id):
    """Agent to client communication"""
    global latest_route_data
    
    try:
        turn_counter = 0
        
        async for event in live_events:
            part: Part = (
                event.content and event.content.parts and event.content.parts[0]
            )
            
            if part:
                # Handle audio data
                is_audio = part.inline_data and part.inline_data.mime_type.startswith("audio/pcm")
                if is_audio:
                    audio_data = part.inline_data and part.inline_data.data
                    if audio_data:
                        message = {
                            "type": "audio",
                            "data": base64.b64encode(audio_data).decode("ascii")
                        }
                        await websocket.send_text(json.dumps(message))
                        print(f"[AUDIO SENT]: {len(audio_data)} bytes")
            
            # Handle turn completion
            if event.turn_complete:
                turn_counter += 1
                print(f"\n{'='*60}")
                print(f"✅ TURN #{turn_counter} COMPLETE")
                print(f"{'='*60}")
                
                # CHECK ROUTE CACHE
                with route_lock:
                    route_data = latest_route_data.get('current')
                
                if route_data:
                    print(f"✅ ROUTE DATA FOUND IN CACHE")
                    print(f"   From: {route_data['origin']}")
                    print(f"   To: {route_data['destination']}")
                    print(f"   Distance: {route_data['distance']}")
                    print(f"   Duration: {route_data['duration']}")
                    if route_data.get('stops'):
                        print(f"   Stops: {len(route_data['stops'])}")
                    
                    # SEND ROUTE TO FRONTEND
                    try:
                        message = {
                            "type": "route",
                            "data": route_data
                        }
                        await websocket.send_text(json.dumps(message))
                        print(f"✅ ROUTE SENT TO FRONTEND\n")
                        
                        # Clear cache after sending
                        with route_lock:
                            latest_route_data.pop('current', None)
                    except Exception as e:
                        print(f"❌ Error sending route: {e}\n")
                else:
                    print(f"⚠️  NO ROUTE DATA IN CACHE\n")
                
                # Send turn complete
                try:
                    await websocket.send_text(json.dumps({"type": "turn_complete"}))
                except:
                    pass
                
    except WebSocketDisconnect:
        print(f"❌ Client {user_id} disconnected")
    except Exception as e:
        print(f"❌ Error in agent_to_client_messaging: {e}")
        import traceback
        traceback.print_exc()

async def client_to_agent_messaging(websocket, live_request_queue, user_id):
    """Client to agent communication"""
    try:
        while True:
            message_json = await websocket.receive_text()
            message = json.loads(message_json)
            
            if message.get("type") == "audio":
                decoded_data = base64.b64decode(message["data"])
                live_request_queue.send_realtime(Blob(data=decoded_data, mime_type="audio/pcm"))
                
    except WebSocketDisconnect:
        print(f"Client {user_id} disconnected")
    except Exception as e:
        print(f"Error in client_to_agent_messaging: {e}")

# FastAPI app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Gemini Maps Voice Assistant", "status": "running"}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, is_audio: str):
    """WebSocket endpoint"""
    await websocket.accept()
    print(f"\n{'='*60}")
    print(f"👤 CLIENT #{user_id} CONNECTED")
    print(f"{'='*60}\n")
    
    user_id_str = str(user_id)
    live_events, live_request_queue = await start_agent_session(user_id_str, is_audio == "true")
    
    agent_to_client_task = asyncio.create_task(
        agent_to_client_messaging(websocket, live_events, user_id_str)
    )
    client_to_agent_task = asyncio.create_task(
        client_to_agent_messaging(websocket, live_request_queue, user_id_str)
    )
    
    try:
        tasks = [agent_to_client_task, client_to_agent_task]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        
        for task in done:
            if task.exception():
                print(f"Task error: {task.exception()}")
    finally:
        live_request_queue.close()
        print(f"\n❌ CLIENT #{user_id} DISCONNECTED\n")

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🗺️  Gemini Maps Voice Assistant")
    print("=" * 60)
    print(f"✅ Model: {root_agent.model}")
    print(f"✅ Tools: Directions, Nearby Stops")
    print(f"✅ Listening on: http://localhost:8000")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
