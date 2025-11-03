# main.py
import os
import json
import asyncio
import base64
import warnings
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables BEFORE importing the agent
load_dotenv()

from google.genai import types
from google.genai.types import Part, Content, Blob
from google.adk.runners import Runner
from google.adk.agents import Agent, LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.websockets import WebSocketDisconnect

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Application configuration
APP_NAME = "gemini-live-voice-assistant"

# Initialize session service
session_service = InMemorySessionService()

# Define the agent
root_agent = Agent(
    name="voice_assistant",
    model=os.getenv("DEMO_AGENT_MODEL", "gemini-2.0-flash-exp"),
    description="A helpful voice assistant.",
    instruction="You are a helpful AI assistant. Respond naturally and conversationally to user queries.",
)

# Initialize runner once at module level (production pattern)
runner = Runner(
    app_name=APP_NAME,
    agent=root_agent,
    session_service=session_service,
)

async def start_agent_session(user_id, is_audio=False):
    """Starts an ADK agent session"""
    # Get or create session
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
    
    # Detect native audio models
    model_name = root_agent.model if isinstance(root_agent.model, str) else root_agent.model.model
    is_native_audio = "native-audio" in model_name.lower()
    
    # Configure response modality
    modality = "AUDIO" if (is_audio or is_native_audio) else "TEXT"
    
    # Configure run settings - NO TRANSCRIPTION
    run_config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=[modality],
        session_resumption=types.SessionResumptionConfig(),
        # REMOVED: output_audio_transcription - no text transcripts needed
    )
    
    # Create LiveRequestQueue in async context
    live_request_queue = LiveRequestQueue()
    
    # Start streaming session
    live_events = runner.run_live(
        user_id=user_id,
        session_id=session.id,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    
    return live_events, live_request_queue

async def agent_to_client_messaging(websocket, live_events):
    """Agent to client communication - AUDIO ONLY"""
    try:
        async for event in live_events:
            # Read the Content and its first Part
            part: Part = (
                event.content and event.content.parts and event.content.parts[0]
            )
            
            if part:
                # Handle audio data only
                is_audio = part.inline_data and part.inline_data.mime_type.startswith("audio/pcm")
                if is_audio:
                    audio_data = part.inline_data and part.inline_data.data
                    if audio_data:
                        message = {
                            "mime_type": "audio/pcm",
                            "data": base64.b64encode(audio_data).decode("ascii")
                        }
                        await websocket.send_text(json.dumps(message))
                        print(f"[AGENT TO CLIENT]: audio/pcm: {len(audio_data)} bytes.")
            
            # Handle turn completion/interruption
            if event.turn_complete or event.interrupted:
                message = {
                    "turn_complete": event.turn_complete,
                    "interrupted": event.interrupted,
                }
                await websocket.send_text(json.dumps(message))
                print(f"[AGENT TO CLIENT]: {message}")
                
    except WebSocketDisconnect:
        print("Client disconnected from agent_to_client_messaging")
    except Exception as e:
        print(f"Error in agent_to_client_messaging: {e}")

async def client_to_agent_messaging(websocket, live_request_queue):
    """Client to agent communication - AUDIO ONLY"""
    try:
        while True:
            message_json = await websocket.receive_text()
            message = json.loads(message_json)
            mime_type = message["mime_type"]
            data = message["data"]
            
            if mime_type == "audio/pcm":
                # Send audio in realtime mode
                decoded_data = base64.b64decode(data)
                live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
                print(f"[CLIENT TO AGENT]: audio/pcm: {len(decoded_data)} bytes")
            else:
                print(f"Unsupported mime type: {mime_type}")
                
    except WebSocketDisconnect:
        print("Client disconnected from client_to_agent_messaging")
    except Exception as e:
        print(f"Error in client_to_agent_messaging: {e}")

# FastAPI web app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path("static")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def root():
    if (STATIC_DIR / "index.html").exists():
        return FileResponse(STATIC_DIR / "index.html")
    return {"message": "Gemini Live Voice Assistant API (Audio Only)", "status": "running"}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, is_audio: str):
    """WebSocket endpoint for bidirectional audio streaming"""
    await websocket.accept()
    print(f"Client #{user_id} connected, audio mode: {is_audio}")
    
    user_id_str = str(user_id)
    live_events, live_request_queue = await start_agent_session(user_id_str, is_audio == "true")
    
    # Run bidirectional messaging concurrently
    agent_to_client_task = asyncio.create_task(
        agent_to_client_messaging(websocket, live_events)
    )
    client_to_agent_task = asyncio.create_task(
        client_to_agent_messaging(websocket, live_request_queue)
    )
    
    try:
        # Wait for either task to complete
        tasks = [agent_to_client_task, client_to_agent_task]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        
        # Check for errors in completed tasks
        for task in done:
            if task.exception() is not None:
                print(f"Task error for client #{user_id}: {task.exception()}")
                import traceback
                traceback.print_exception(type(task.exception()), task.exception(), task.exception().__traceback__)
    finally:
        # Clean up resources
        live_request_queue.close()
        print(f"Client #{user_id} disconnected")

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🎙️  Gemini Live Voice Assistant (Audio Only)")
    print("=" * 60)
    print(f"✅ Model: {root_agent.model}")
    print(f"✅ Mode: Audio-to-Audio (No Transcription)")
    print(f"✅ Listening on: http://localhost:8000")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
