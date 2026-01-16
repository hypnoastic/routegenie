# Route Genie

Route Genie is a real-time, voice-first route planning assistant built using the Google Agent Development Kit (ADK) and the Gemini Live speech-to-speech model. The system supports bidirectional audio streaming over WebSockets and enables users to search locations, add stops, and modify routes using natural spoken language, without any intermediate text-based interaction.

---

## Overview

Route Genie allows users to interact with a conversational AI agent entirely through voice. Audio from the client is streamed directly to the Gemini Live model, which responds with synthesized speech in real time. The agent is equipped with map-related tools that allow it to search for places, add and reorder stops, and resolve locations mentioned conversationally.

There is no speech-to-text or text-to-speech conversion layer in the application. The interaction loop is purely speech-to-speech.

---

## Key Capabilities

- Real-time bidirectional audio streaming over WebSockets
- Direct speech-to-speech interaction using Gemini Live
- Agent orchestration using Google Agent Development Kit (ADK)
- Tool-based integration with mapping services
- Natural language route planning and modification
- Continuous conversational context across turns

---

## Application Architecture

The system is organized around a persistent audio streaming loop between the client and the backend, with the backend acting as a bridge between the user and the Gemini Live agent.

### High-Level Architecture Diagram

```text
Client (Browser / App)
   │
   │  WebSocket (Bidirectional Audio + Events)
   ▼
Backend Server
   │
   ├─ Google Agent Development Kit (ADK)
   │     └─ Agent Orchestration and Tool Routing
   │
   ├─ Gemini Live Model (Streaming)
   │     └─ Speech ↔ Speech (Direct Audio In / Audio Out)
   │
   └─ Maps Tools
         ├─ Place Search
         ├─ Route Planning
         └─ Stop Management
```

## Detailed Data Flow

### 1. Audio Input

- The client captures microphone audio using the Web Audio API.
- Audio frames are sent continuously over a WebSocket connection to the backend server.

### 2. Streaming to Gemini Live

- The backend forwards audio frames directly to an active Gemini Live streaming session.
- The model processes incoming speech and maintains conversational context.

### 3. Agent Reasoning and Tool Use

- The ADK agent interprets model intents and decides when to invoke tools.
- Tool calls are executed by the backend using Maps and Places APIs.
- Results are injected back into the agent context during the same streaming session.

### 4. Audio Output

- Gemini Live generates spoken responses as audio chunks.
- Audio chunks are streamed back to the client over WebSocket.
- The client plays audio immediately to maintain real-time interaction.

---

## Agent Tool Layer

The agent is configured with structured tools that can be invoked dynamically by the model.

### Supported Tool Categories

- Place Search  
  Finds locations based on conversational descriptions.

- Route Construction  
  Builds and updates routes between multiple stops.

- Stop Management  
  Adds, removes, and reorders intermediate locations.

- Location Resolution  
  Converts vague references into concrete geographic points.

All tool execution happens on the backend and does not interrupt the audio stream.

---

## Streaming Characteristics

- Full-duplex audio streaming
- Low-latency conversational turn-taking
- Continuous session state across tool calls
- No intermediate text transcripts

---

## Security and Reliability Considerations

- WebSocket authentication should be enforced in production
- API credentials must remain server-side only
- Session isolation per connected client
- Graceful reconnection handling for network drops

---

## Limitations

- Performance depends on network latency and bandwidth
- Requires access to Gemini Live streaming endpoints
- Mapping accuracy depends on third-party APIs

---

## Future Enhancements

- Visual route preview synchronized with voice
- Turn-by-turn spoken navigation
- Mobile-native clients
- Multi-language speech support
- Offline route caching

---

## Author

Yash Kumar  
B.Tech CSE (AI), Newton School of Technology

