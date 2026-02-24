from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models import User, Trip
from app.auth import require_internal_key, get_current_user_email
from app.services.trip_parser import parse_trip_request
from app.services.amadeus import search_flights, search_hotels
from app.services.itinerary import build_itinerary_options

router = APIRouter(prefix="/trips", tags=["trips"])


class TripRequestIn(BaseModel):
    raw_request: str


class TripOut(BaseModel):
    id: str
    status: str
    raw_request: str
    parsed_spec: Optional[dict] = None
    itinerary_options: Optional[list] = None
    approved_itinerary: Optional[dict] = None
    created_at: str


def _trip_to_out(trip: Trip) -> TripOut:
    return TripOut(
        id=str(trip.id),
        status=trip.status,
        raw_request=trip.raw_request,
        parsed_spec=trip.parsed_spec,
        itinerary_options=trip.itinerary_options,
        approved_itinerary=trip.approved_itinerary,
        created_at=trip.created_at.isoformat(),
    )


@router.post("", response_model=TripOut, status_code=status.HTTP_201_CREATED)
async def create_trip(
    data: TripRequestIn,
    email: str = Depends(get_current_user_email),
    _key: str = Depends(require_internal_key),
    db: Session = Depends(get_db),
):
    """
    Parse a plain-English trip request, search for flights + hotels, and return
    2-3 itinerary options. Runs synchronously — a task queue will be added in Week 5.
    """
    # Get or lazily create the user record
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)

    # Persist the trip immediately so the user can see it even if something fails
    trip = Trip(user_id=user.id, raw_request=data.raw_request, status="parsing")
    db.add(trip)
    db.commit()
    db.refresh(trip)

    try:
        # 1. Parse the natural-language request
        parsed_spec = await parse_trip_request(data.raw_request)
        trip.parsed_spec = parsed_spec
        trip.status = "searching"
        db.commit()

        origin = parsed_spec.get("origin")
        destination = parsed_spec.get("destination")
        depart_date = parsed_spec.get("depart_date")
        return_date = parsed_spec.get("return_date")
        num_travelers = parsed_spec.get("num_travelers", 1) or 1
        cabin_class = parsed_spec.get("cabin_class", "ECONOMY") or "ECONOMY"
        budget_total = parsed_spec.get("budget_total")

        flight_offers: list = []
        hotel_offers: list = []

        # 2. Search flights
        if origin and destination and depart_date:
            try:
                flight_offers = await search_flights(
                    origin=origin,
                    destination=destination,
                    depart_date=depart_date,
                    return_date=return_date,
                    adults=num_travelers,
                    travel_class=cabin_class,
                )
            except Exception as exc:
                print(f"[trips] flight search error: {exc}")

        # 3. Search hotels
        if destination and depart_date and return_date:
            try:
                hotel_offers = await search_hotels(
                    city_code=destination,
                    check_in=depart_date,
                    check_out=return_date,
                    adults=num_travelers,
                )
            except Exception as exc:
                print(f"[trips] hotel search error: {exc}")

        # 4. Build itinerary packages
        options = build_itinerary_options(
            flight_offers=flight_offers,
            hotel_offers=hotel_offers,
            budget_total=float(budget_total) if budget_total else None,
        )

        trip.itinerary_options = options
        trip.status = "options_ready" if options else "search_failed"
        db.commit()
        db.refresh(trip)

    except Exception as exc:
        trip.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Trip processing failed: {exc}",
        )

    return _trip_to_out(trip)


@router.get("", response_model=list[TripOut])
def list_trips(
    email: str = Depends(get_current_user_email),
    _key: str = Depends(require_internal_key),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return []
    trips = (
        db.query(Trip)
        .filter(Trip.user_id == user.id)
        .order_by(Trip.created_at.desc())
        .all()
    )
    return [_trip_to_out(t) for t in trips]


@router.get("/{trip_id}", response_model=TripOut)
def get_trip(
    trip_id: str,
    email: str = Depends(get_current_user_email),
    _key: str = Depends(require_internal_key),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    trip = (
        db.query(Trip)
        .filter(Trip.id == trip_id, Trip.user_id == user.id)
        .first()
    )
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return _trip_to_out(trip)


class ApproveIn(BaseModel):
    option_index: int = 0


@router.post("/{trip_id}/approve", response_model=TripOut)
def approve_trip(
    trip_id: str,
    data: ApproveIn,
    email: str = Depends(get_current_user_email),
    _key: str = Depends(require_internal_key),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    trip = (
        db.query(Trip)
        .filter(Trip.id == trip_id, Trip.user_id == user.id)
        .first()
    )
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    if trip.status != "options_ready":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trip is not in options_ready state (current: {trip.status})",
        )

    options = trip.itinerary_options or []
    if data.option_index >= len(options):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid option_index {data.option_index} (only {len(options)} options available)",
        )

    trip.approved_itinerary = options[data.option_index]
    trip.status = "approved"
    db.commit()
    db.refresh(trip)
    return _trip_to_out(trip)
