from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Trip
from app.schemas import ShareTripResponse, TripCreateRequest, TripOut
from app.services.auth import AuthService


router = APIRouter()


@router.get("/trips", response_model=list[TripOut])
def list_trips(request: Request, db: Session = Depends(get_db)):
    service = AuthService(db)
    user = service.require_user(request)
    return db.scalars(select(Trip).where(Trip.user_id == user.id).order_by(Trip.created_at.desc())).all()


@router.post("/trips", response_model=TripOut)
def create_trip(payload: TripCreateRequest, request: Request, db: Session = Depends(get_db)):
    service = AuthService(db)
    user = service.require_user(request)
    return service.save_trip(user, payload)


@router.get("/trips/{trip_id}", response_model=TripOut)
def get_trip(trip_id: str, request: Request, db: Session = Depends(get_db)):
    service = AuthService(db)
    user = service.require_user(request)
    trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.user_id == user.id))
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


@router.delete("/trips/{trip_id}")
def delete_trip(trip_id: str, request: Request, db: Session = Depends(get_db)):
    service = AuthService(db)
    user = service.require_user(request)
    trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.user_id == user.id))
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    db.delete(trip)
    db.commit()
    return {"status": "deleted"}


@router.post("/trips/{trip_id}/share", response_model=ShareTripResponse)
def share_trip(trip_id: str, request: Request, db: Session = Depends(get_db)):
    service = AuthService(db)
    user = service.require_user(request)
    trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.user_id == user.id))
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    share_slug = service.share_trip(trip)
    base_url = request.headers.get("origin") or request.headers.get("referer") or ""
    base_url = base_url.rstrip("/")
    return ShareTripResponse(share_slug=share_slug, share_url=f"{base_url}/share/{share_slug}")


@router.get("/share/{slug}", response_model=TripOut)
def get_shared_trip(slug: str, db: Session = Depends(get_db)):
    trip = db.scalar(select(Trip).where(Trip.share_slug == slug))
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared trip not found")
    return trip
