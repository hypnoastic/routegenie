<p align="center">
  <img src="https://img.shields.io/badge/Gemini_Live-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Gemini Live"/>
  <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React"/>
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"/>
  <img src="https://img.shields.io/badge/Google_Maps-4285F4?style=for-the-badge&logo=google-maps&logoColor=white" alt="Google Maps"/>
</p>

# RouteGenie

**Voice-First AI Navigation Assistant with Intelligent Stop Insertion**

RouteGenie is a cutting-edge voice-controlled navigation application that enables hands-free route planning with smart waypoint insertion. Speak naturally to get driving directions with stops like restaurants, gas stations, or coffee shops — all rendered on an interactive Google Map.

---

## Problem Statement

Traditional navigation apps require manual text input to plan routes and add stops. This is:

- **Inconvenient** when driving or multitasking
- **Cumbersome** for complex routes with multiple waypoints
- **Not accessible** for users who prefer voice interaction

**RouteGenie solves this** by providing a fully voice-activated navigation experience powered by Gemini Live's real-time audio streaming and LLM tool-calling capabilities.

---

## Key Features

| Feature                        | Description                                                      |
| ------------------------------ | ---------------------------------------------------------------- |
| **Voice-First Navigation**  | Speak naturally: _"Route from Delhi to Gurgaon with McDonald's"_ |
| **Gemini Live Integration** | Real-time bidirectional audio streaming with Google's latest AI  |
| **Smart Stop Insertion**    | Automatically finds and adds stops as optimized waypoints        |
| **Interactive Google Maps** | Full-screen map with polyline routes, markers, and info windows  |
| **Real-Time Response**      | Audio responses streamed back with sub-second latency            |
| **Google OAuth**            | Secure authentication with session persistence                   |
| **Route History**           | PostgreSQL-backed storage of routes and user preferences         |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE                              │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  React 19 + Vite + @react-google-maps/api                       │    │
│  │  • Full-screen Google Map with Polyline/Markers                 │    │
│  │  • Glassmorphism UI with animated voice bars                    │    │
│  │  • WebRTC audio capture (16kHz PCM16)                          │    │
│  │  • Web Audio API for playback (24kHz)                          │    │
│  └────────────────────────────┬────────────────────────────────────┘    │
│                               │ WebSocket (Bidirectional)               │
└───────────────────────────────┼─────────────────────────────────────────┘
                                │
┌───────────────────────────────┼─────────────────────────────────────────┐
│                               ▼                                          │
│                         BACKEND SERVER                                   │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  FastAPI + Uvicorn                                               │    │
│  │  • WebSocket endpoint (/ws/{user_id})                           │    │
│  │  • Async task management with asyncio                           │    │
│  │  • Thread-safe route caching with locks                         │    │
│  │  • CORS middleware for frontend                                 │    │
│  └────────────────────────────┬────────────────────────────────────┘    │
│                               │                                          │
│  ┌────────────────────────────┼────────────────────────────────────┐    │
│  │                    GOOGLE ADK AGENT                              │    │
│  │  ┌─────────────────────────▼──────────────────────────────┐     │    │
│  │  │  Gemini Live (gemini-2.5-flash-native-audio-preview)   │     │    │
│  │  │  • StreamingMode.BIDI for full-duplex audio            │     │    │
│  │  │  • Real-time speech understanding                       │     │    │
│  │  │  • LLM tool-calling with FunctionTool                  │     │    │
│  │  └─────────────────────────┬──────────────────────────────┘     │    │
│  │                            │                                     │    │
│  │  ┌─────────────────────────▼──────────────────────────────┐     │    │
│  │  │  Custom Tool: get_directions_with_stop()               │     │    │
│  │  │  • Geocoding origin location                           │     │    │
│  │  │  • Places API nearby search for stops                  │     │    │
│  │  │  • Directions API with waypoint optimization           │     │    │
│  │  │  • Multi-leg polyline decoding and merging             │     │    │
│  │  └────────────────────────────────────────────────────────┘     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  PostgreSQL (Neon)                                               │    │
│  │  • User accounts & OAuth tokens                                 │    │
│  │  • Route history & favorites                                    │    │
│  │  • Session persistence                                          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL APIS                                     │
│  • Google Maps JavaScript API (map rendering)                            │
│  • Google Maps Directions API (route calculation)                        │
│  • Google Maps Places API (nearby stop search)                           │
│  • Google Maps Geocoding API (address resolution)                        │
│  • Serper API (optional web search)                                      │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend (React)
    participant WS as WebSocket
    participant B as Backend (FastAPI)
    participant G as Gemini Live
    participant T as Tool (Directions)
    participant M as Google Maps APIs

    U->>F: Clicks "Find your route"
    F->>WS: Opens WebSocket connection
    F->>F: Starts mic recording (16kHz PCM16)

    loop Voice Streaming
        F->>WS: Send audio chunks (base64)
        WS->>B: Forward to ADK agent
        B->>G: Stream to Gemini Live
    end

    U->>F: "Route from Delhi to Gurgaon with McDonald's"
    G->>G: Understands intent
    G->>T: Calls get_directions_with_stop()

    T->>M: Geocode origin
    M-->>T: Origin coordinates
    T->>M: Places nearby (McDonald's)
    M-->>T: Stop location & details
    T->>M: Directions with waypoint
    M-->>T: Multi-leg route + polylines

    T-->>G: Route JSON response
    G->>B: Audio response + turn complete
    B->>WS: Send route data
    WS->>F: Route JSON

    F->>F: Decode polyline
    F->>F: Render on Google Map
    F->>F: Play audio response
```

---

## Tech Stack

### Frontend

| Technology                 | Purpose                                   |
| -------------------------- | ----------------------------------------- |
| **React 19**               | UI framework with hooks                   |
| **Vite**                   | Fast build tool and dev server            |
| **@react-google-maps/api** | Google Maps React components              |
| **Web Audio API**          | Real-time audio capture (ScriptProcessor) |
| **WebSocket**              | Bidirectional real-time communication     |

### Backend

| Technology            | Purpose                          |
| --------------------- | -------------------------------- |
| **FastAPI**           | Async Python web framework       |
| **Uvicorn**           | ASGI server                      |
| **Google ADK 1.17.0** | Agent Development Kit for Gemini |
| **Gemini Live**       | Real-time audio streaming LLM    |
| **googlemaps**        | Python client for Maps APIs      |
| **polyline**          | Encode/decode route polylines    |
| **python-dotenv**     | Environment management           |

### Database & Auth

| Technology            | Purpose                 |
| --------------------- | ----------------------- |
| **PostgreSQL (Neon)** | Cloud-hosted database   |
| **Prisma**            | ORM for database access |
| **Google OAuth**      | Secure authentication   |
| **JWT**               | Session tokens          |

### AI & APIs

| Technology           | Purpose                       |
| -------------------- | ----------------------------- |
| **Gemini 2.5 Flash** | Native audio model for voice  |
| **Gemini 2.0 Flash** | Text model for chat           |
| **Google Maps APIs** | Directions, Places, Geocoding |
| **Serper API**       | Web search capabilities       |

---

## Core Technical Implementation

### 1. Bidirectional Audio Streaming (Gemini Live)

The application uses Google ADK's `runner.run_live()` for full-duplex audio:

```python
run_config = RunConfig(
    streaming_mode=StreamingMode.BIDI,  # Full-duplex
    response_modalities=["AUDIO"],       # Voice responses
    session_resumption=types.SessionResumptionConfig(),
)

live_events = runner.run_live(
    user_id=user_id,
    session_id=session.id,
    live_request_queue=live_request_queue,
    run_config=run_config,
)
```

### 2. Custom Function Tool with LLM Tool-Calling

The agent uses a custom tool that the LLM can invoke:

```python
def get_directions_with_stop(origin: str, destination: str, stop_place: str) -> str:
    """
    Get directions from origin to destination with an optional stop.
    Combines the stop into a single optimized route using waypoints.
    """
    # 1. Geocode origin
    # 2. Find stop via Places API nearby search
    # 3. Get directions with waypoints
    # 4. Decode/merge multi-leg polylines
    # 5. Return optimized route JSON
```

### 3. Multi-Leg Polyline Merging

When stops are added, the route has multiple legs. The system properly combines them:

```python
for leg in route['legs']:
    # Decode each leg's polyline
    leg_coords = polyline.decode(leg['overview_polyline']['points'])
    combined_coords.extend(leg_coords)

# Re-encode combined coordinates
combined_polyline = polyline.encode(combined_coords, 5)
```

### 4. Real-Time Audio Processing

Frontend captures audio at 16kHz, converts to PCM16, and streams:

```javascript
processor.onaudioprocess = (e) => {
  const inputData = e.inputBuffer.getChannelData(0);
  const pcm16 = new Int16Array(inputData.length);
  for (let i = 0; i < inputData.length; i++) {
    const s = Math.max(-1, Math.min(1, inputData[i]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  ws.send(JSON.stringify({ type: "audio", data: base64(pcm16.buffer) }));
};
```

### 5. Thread-Safe Route Caching

Multiple async tasks share route data safely:

```python
route_lock = threading.Lock()
latest_route_data = {}

# Writing
with route_lock:
    latest_route_data['current'] = result

# Reading
with route_lock:
    route_data = latest_route_data.get('current')
```

---

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- Python 3.11+
- Google Cloud account with APIs enabled:
  - Maps JavaScript API
  - Directions API
  - Places API
  - Geocoding API
- Google AI Studio API key (for Gemini)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run server
python main.py
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run dev server
npm run dev
```

### Environment Variables

**Backend (.env)**

```env
# Google APIs
GOOGLE_MAPS_API_KEY=your_maps_api_key
GOOGLE_API_KEY=your_gemini_api_key
GOOGLE_CLIENT_ID=your_oauth_client_id
GOOGLE_CLIENT_SECRET=your_oauth_secret

# Database
DATABASE_URL=postgresql://user:pass@host/db

# Models
VOICE_MODEL=gemini-2.5-flash-native-audio-preview-12-2025
TEXT_MODEL=gemini-2.0-flash

# Server
PORT=8000
FRONTEND_URL=http://localhost:5173
JWT_SECRET=your_jwt_secret
```

**Frontend (.env)**

```env
VITE_GOOGLE_MAPS_API_KEY=your_maps_api_key
VITE_BACKEND_URL=http://localhost:8000
```

---

## Screenshots

### Voice Interaction Overlay

- Glassmorphism UI design
- Animated voice bars during recording
- Real-time connection status

### Route Display

- Full-screen Google Map
- Blue polyline for route
- Green marker (start), Yellow (stops), Red (destination)
- Info box with distance, duration, and stop details

---

## Performance

| Metric                     | Value               |
| -------------------------- | ------------------- |
| Voice-to-response latency  | ~800ms - 1.2s       |
| Concurrent sessions tested | 25+                 |
| Audio sample rate (input)  | 16kHz               |
| Audio sample rate (output) | 24kHz               |
| WebSocket message format   | JSON + Base64 audio |

---

## Future Enhancements

- [ ] Multi-stop route planning (more than one waypoint)
- [ ] Turn-by-turn navigation with real-time updates
- [ ] Traffic-aware routing
- [ ] Favorite routes and places
- [ ] Offline voice command support
- [ ] Mobile app (React Native)

---

## License

This project is licensed under the MIT License.

---

## Acknowledgments

- [Google ADK](https://ai.google.dev/adk) for the Agent Development Kit
- [Gemini Live](https://ai.google.dev/gemini-api/docs/live) for real-time audio streaming
- [Google Maps Platform](https://developers.google.com/maps) for mapping APIs

---
