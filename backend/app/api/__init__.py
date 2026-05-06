from fastapi import APIRouter

from app.api import auth, gemini, places, routes, trips


api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(trips.router, tags=["trips"])
api_router.include_router(places.router, tags=["places"])
api_router.include_router(routes.router, tags=["routes"])
api_router.include_router(gemini.router, tags=["gemini"])
