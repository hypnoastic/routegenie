import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from websockets.exceptions import ConnectionClosed

from app.api import api_router
from app.config import get_settings
from app.db import get_db
from app.services.auth import AuthService
from app.services.gemini_live import run_live_session


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    previous_exception_handler = loop.get_exception_handler()

    def ignore_google_live_close_noise(loop, context):
        message = str(context.get("message") or "")
        exception = context.get("exception")
        if message.startswith("ConnectionClosedError exception in shielded future") or isinstance(exception, ConnectionClosed):
            return
        if previous_exception_handler:
            previous_exception_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(ignore_google_live_close_noise)
    yield
    loop.set_exception_handler(previous_exception_handler)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/")
def root():
    return {"message": settings.app_name, "status": "running"}


@app.get("/health")
def health():
    return {"status": "healthy", "missing_config": settings.runtime_validation_errors()}


@app.websocket("/ws/live")
async def live_websocket(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    user = AuthService(db).current_user_from_token(websocket.cookies.get(settings.session_cookie_name))
    try:
        await run_live_session(websocket, db, user)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
        await websocket.close(code=1011)
