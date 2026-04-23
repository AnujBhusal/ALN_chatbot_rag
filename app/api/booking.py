from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.session import get_db
from app.db import models
from app.services.memory import MemoryService

router = APIRouter(prefix="/booking", tags=["Booking"])

# Optional: use Redis for quick lookup
memory = MemoryService()


class BookingRequest(BaseModel):
    name: str
    email: EmailStr
    date: str  # YYYY-MM-DD
    time: str  # HH:MM (24-hour)


class BookingResponse(BaseModel):
    message: str
    booking_id: int


@router.post("/create", response_model=BookingResponse)
async def create_booking(request: BookingRequest, db: Session = Depends(get_db)) -> BookingResponse:
    """
    Create an interview booking.
    """
    # Validate date/time
    try:
        dt = datetime.strptime(f"{request.date} {request.time}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date or time format.")

    # Optional: Check Redis if slot is already booked
    slot_key = f"booking:{request.date}:{request.time}"
    if memory.redis_client:
        try:
            if memory.redis_client.get(slot_key):
                raise HTTPException(status_code=400, detail="Time slot already booked.")
        except Exception:
            pass  # If Redis fails, continue anyway

    # Save in Postgres
    booking = models.Booking(name=request.name, email=request.email, datetime=dt)
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Save in Redis for quick lookup (optional)
    if memory.redis_client:
        try:
            memory.redis_client.set(slot_key, booking.id, ex=86400)
        except Exception:
            pass  # If Redis fails, continue anyway

    return BookingResponse(message="Booking confirmed", booking_id=booking.id)
