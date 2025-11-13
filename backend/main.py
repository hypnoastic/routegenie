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
import polyline

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

def get_directions_with_stop(origin: str, destination: str, stop_place: str) -> str:
    """
    Get directions from origin to destination with an optional stop.
    Combines the stop into a single optimized route using waypoints.
    
    Args:
        origin: Starting location
        destination: Ending location
        stop_place: Stop/waypoint place (e.g., "McDonald's", "gas station", or "none" for no stop)
    
    Returns:
        Route information with polyline and stop details
    """
    global latest_route_data
    
    try:
        print(f"\n🗺️ 🔧 TOOL CALLED: get_directions_with_stop('{origin}' → '{destination}' via '{stop_place}')")
        
        waypoints = []
        stop_info = None
        
        # If stop is requested (not "none" or empty), find it and add as waypoint
        if stop_place and stop_place.lower() != "none" and stop_place.strip():
            print(f"🔍 Finding stop: {stop_place} near {origin}")
            
            try:
                # Geocode the origin to get coordinates for nearby search
                geocode_origin = gmaps.geocode(origin)
                if not geocode_origin:
                    print(f"⚠️ Could not geocode origin {origin}")
                else:
                    origin_coords = geocode_origin[0]['geometry']['location']
                    
                    # Find the stop location
                    nearby_result = gmaps.places_nearby(
                        location=(origin_coords['lat'], origin_coords['lng']),
                        radius=5000,
                        keyword=stop_place,
                        open_now=False
                    )
                    
                    if nearby_result.get('results') and len(nearby_result['results']) > 0:
                        best_place = nearby_result['results'][0]
                        
                        stop_info = {
                            "name": best_place.get('name', 'Unknown'),
                            "address": best_place.get('vicinity', 'Address not available'),
                            "lat": float(best_place['geometry']['location']['lat']),
                            "lng": float(best_place['geometry']['location']['lng']),
                            "rating": best_place.get('rating', None)
                        }
                        
                        # Add as waypoint
                        waypoints.append((stop_info['lat'], stop_info['lng']))
                        
                        print(f"✅ Stop found: {stop_info['name']}")
                        print(f"   Coordinates: ({stop_info['lat']}, {stop_info['lng']})")
                    else:
                        print(f"⚠️ Stop '{stop_place}' not found, continuing without stop")
            
            except Exception as e:
                print(f"⚠️ Error finding stop: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # Get directions with or without waypoint
        print(f"📍 Calculating route from {origin} to {destination}...")
        
        try:
            # Build directions parameters
            directions_params = {
                'origin': origin,
                'destination': destination,
                'mode': 'driving',
                'departure_time': datetime.now()
            }
            
            # Add waypoints if we found a stop
            if waypoints:
                directions_params['waypoints'] = waypoints
                directions_params['optimize_waypoints'] = True
                print(f"🛣️ Using waypoints: {waypoints}")
            
            directions = gmaps.directions(**directions_params)
            
        except Exception as e:
            print(f"❌ Directions API error: {str(e)}")
            import traceback
            traceback.print_exc()
            return json.dumps({"status": "error", "error": str(e)})
        
        if not directions:
            print("❌ No route found")
            return json.dumps({"error": "No route found"})
        
        route = directions[0]
        
        # PROPERLY combine polylines: decode each leg separately, then combine coordinates
        combined_coords = []
        total_distance = 0
        total_duration = 0
        origin_address = ""
        destination_address = ""
        all_steps = []
        
        legs = route['legs']
        print(f"📊 Processing {len(legs)} leg(s)...")
        
        for idx, leg in enumerate(legs):
            print(f"   Leg {idx + 1}: {leg['start_address']} → {leg['end_address']}")
            
            if idx == 0:
                origin_address = leg['start_address']
            if idx == len(legs) - 1:
                destination_address = leg['end_address']
            
            # Decode each leg's polyline separately
            if 'overview_polyline' in leg and leg['overview_polyline'].get('points'):
                try:
                    # Decode the polyline for this leg
                    leg_coords = polyline.decode(leg['overview_polyline']['points'])
                    print(f"      ✅ Decoded {len(leg_coords)} points from overview polyline")
                    
                    # Add all coordinates from this leg
                    combined_coords.extend(leg_coords)
                except Exception as e:
                    print(f"      ⚠️ Error decoding overview polyline: {e}")
                    # Fall back to step polylines
                    for step in leg['steps']:
                        if 'polyline' in step and step['polyline'].get('points'):
                            try:
                                step_coords = polyline.decode(step['polyline']['points'])
                                combined_coords.extend(step_coords)
                            except:
                                pass
            else:
                print(f"      ℹ️ No overview polyline, building from steps...")
                # Build from individual steps
                for step in leg['steps']:
                    if 'polyline' in step and step['polyline'].get('points'):
                        try:
                            step_coords = polyline.decode(step['polyline']['points'])
                            combined_coords.extend(step_coords)
                        except Exception as e:
                            print(f"      ⚠️ Error decoding step polyline: {e}")
            
            total_distance += leg['distance']['value']
            total_duration += leg['duration']['value']
            
            # Collect steps
            for step in leg['steps']:
                html_text = step['html_instructions'].replace('<b>', '').replace('</b>', '').replace('<div style="margin-left: 20px">', '').replace('</div>', '')
                all_steps.append({
                    "instruction": html_text,
                    "distance": step['distance']['text'],
                    "duration": step['duration']['text']
                })
        
        print(f"✅ Combined {len(combined_coords)} total coordinates")
        
        # Now encode the combined coordinates back to polyline
        try:
            combined_polyline = polyline.encode(combined_coords, 5)
            print(f"✅ Re-encoded polyline: {len(combined_polyline)} chars")
        except Exception as e:
            print(f"⚠️ Error encoding polyline: {e}")
            combined_polyline = ""
        
        # Convert to readable format
        distance_km = total_distance / 1000
        duration_hours = total_duration // 3600
        duration_mins = (total_duration % 3600) // 60
        
        distance_text = f"{distance_km:.1f} km"
        if duration_hours > 0:
            duration_text = f"{int(duration_hours)}h {int(duration_mins)}m"
        else:
            duration_text = f"{int(duration_mins)}m"
        
        result = {
            "status": "success",
            "origin": origin_address,
            "destination": destination_address,
            "distance": distance_text,
            "duration": duration_text,
            "polyline": combined_polyline,
            "steps": all_steps[:5]  # First 5 steps
        }
        
        # Add stop if found
        if stop_info:
            result["stop"] = stop_info
            print(f"✅ Stop included in route: {stop_info['name']}")
        
        # Store globally for retrieval
        with route_lock:
            latest_route_data['current'] = result
        
        print(f"✅ ROUTE COMPLETE")
        print(f"   Distance: {distance_text}")
        print(f"   Duration: {duration_text}")
        print(f"   Polyline length: {len(combined_polyline)} chars")
        if stop_info:
            print(f"   Stop: {stop_info['name']}")
        print()
        
        return json.dumps(result)
        
    except Exception as e:
        print(f"❌ Tool Error: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return json.dumps({"status": "error", "error": str(e)})


# Create tool
directions_tool = FunctionTool(func=get_directions_with_stop)

APP_NAME = "gemini-maps-assistant"
session_service = InMemorySessionService()

root_agent = Agent(
    name="maps_assistant",
    model=os.getenv("DEMO_AGENT_MODEL", "gemini-2.0-flash-exp"),
    description="Navigation assistant using Google Maps with optimized routes and stops.",
    instruction="""You are a helpful navigation assistant. When users ask for directions:

1. Extract the origin, destination, and any stops mentioned
2. Call get_directions_with_stop with all three required parameters
3. If no stop is mentioned, pass stop_place as "none"
4. Respond with SHORT responses like "Route found: [distance] in [duration]"

ALWAYS call the function with these exact parameters:
- origin: Starting location (string)
- destination: Ending location (string)  
- stop_place: Stop name or "none" (string)

Examples:
- "Route from Delhi to Gurgaon with McDonald's"
  → get_directions_with_stop(origin="Delhi", destination="Gurgaon", stop_place="McDonald's")
  
- "Directions from office to airport via Starbucks"
  → get_directions_with_stop(origin="office", destination="airport", stop_place="Starbucks")

- "Just directions to the mall"
  → get_directions_with_stop(origin="current location", destination="mall", stop_place="none")
""",
    tools=[directions_tool]
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
                    
                    if route_data.get('stop'):
                        print(f"   Stop: {route_data['stop']['name']}")
                        print(f"   Stop Coords: ({route_data['stop']['lat']}, {route_data['stop']['lng']})")
                    
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
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:5173")],
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
    print("\n" + "="*60)
    print("🗺️  ROUTEGENIE - VOICE NAVIGATION ASSISTANT")
    print("="*60)
    print(f"✅ Model: {root_agent.model}")
    print(f"✅ Tool: get_directions_with_stop")
    print(f"✅ Frontend: {os.getenv('FRONTEND_URL', 'http://localhost:5173')}")
    print(f"✅ Backend: http://localhost:8000")
    print("="*60 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
