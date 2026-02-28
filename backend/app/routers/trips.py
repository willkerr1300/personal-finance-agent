from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models import User, Trip, Booking, AgentLog, TripAlert
from app.auth import require_internal_key, get_current_user_email
from app.services.trip_parser import parse_trip_request
from app.services.amadeus import search_flights, search_hotels, search_activities
from app.services.confirmation import build_confirmation
from app.services.itinerary import build_itinerary_options

router = APIRouter(prefix="/trips", tags=["trips"])


# ---------------------------------------------------------------------------
# Shared output models
# ---------------------------------------------------------------------------

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


class AgentLogOut(BaseModel):
    step: str
    action: str
    result: str
    error_message: Optional[str] = None
    created_at: str


class BookingOut(BaseModel):
    id: str
    type: str
    status: str
    confirmation_number: Optional[str] = None
    details: Optional[dict] = None
    logs: list[AgentLogOut] = []
    created_at: str


class BookOut(BaseModel):
    trip_id: str
    status: str
    bookings: list[dict]


class AlertOut(BaseModel):
    id: str
    alert_type: str
    message: str
    details: Optional[dict] = None
    is_read: bool
    created_at: str


class ModifyIn(BaseModel):
    request: str  # plain-English: "extend my hotel by 2 nights"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _log_to_out(log: AgentLog) -> AgentLogOut:
    return AgentLogOut(
        step=log.step,
        action=log.action,
        result=log.result,
        error_message=log.error_message,
        created_at=log.created_at.isoformat(),
    )


def _booking_to_out(booking: Booking) -> BookingOut:
    return BookingOut(
        id=str(booking.id),
        type=booking.type,
        status=booking.status,
        confirmation_number=booking.confirmation_number,
        details=booking.details,
        logs=[_log_to_out(l) for l in (booking.agent_logs or [])],
        created_at=booking.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Trip CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=TripOut, status_code=status.HTTP_201_CREATED)
async def create_trip(
    data: TripRequestIn,
    email: str = Depends(get_current_user_email),
    _key: str = Depends(require_internal_key),
    db: Session = Depends(get_db),
):
    """
    Parse a plain-English trip request, search for flights + hotels, and return
    2-3 itinerary options.
    """
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)

    trip = Trip(user_id=user.id, raw_request=data.raw_request, status="parsing")
    db.add(trip)
    db.commit()
    db.refresh(trip)

    try:
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
        activity_offers: list = []

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

        if destination and depart_date:
            try:
                activity_offers = await search_activities(
                    city_code=destination,
                    start_date=depart_date,
                    end_date=return_date or depart_date,
                    adults=num_travelers,
                )
            except Exception as exc:
                print(f"[trips] activity search error: {exc}")

        options = build_itinerary_options(
            flight_offers=flight_offers,
            hotel_offers=hotel_offers,
            budget_total=float(budget_total) if budget_total else None,
            activity_offers=activity_offers,
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
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return _trip_to_out(trip)


# ---------------------------------------------------------------------------
# Approve an itinerary option
# ---------------------------------------------------------------------------

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
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
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


# ---------------------------------------------------------------------------
# Trigger booking execution
# ---------------------------------------------------------------------------

@router.post("/{trip_id}/book", response_model=BookOut, status_code=status.HTTP_202_ACCEPTED)
def book_trip(
    trip_id: str,
    email: str = Depends(get_current_user_email),
    _key: str = Depends(require_internal_key),
    db: Session = Depends(get_db),
):
    """
    Start async booking for an approved trip. Creates Booking records, enqueues
    the Celery task, and returns immediately with 202 Accepted.

    The frontend polls GET /trips/{id}/bookings for live progress.
    """
    from app.tasks.booking_tasks import execute_trip_bookings

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    if trip.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trip must be approved before booking (current status: {trip.status})",
        )

    # Require at minimum first + last name for passenger forms
    if not user.first_name or not user.last_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please add your first and last name in your profile before booking.",
        )

    approved = trip.approved_itinerary or {}

    # Create one Booking record per component (flight + hotel)
    created_bookings = []

    if approved.get("flight"):
        flight_booking = Booking(
            trip_id=trip.id,
            type="flight",
            status="pending",
            details={"flight": approved["flight"]},
        )
        db.add(flight_booking)
        created_bookings.append(flight_booking)

    if approved.get("hotel"):
        hotel_booking = Booking(
            trip_id=trip.id,
            type="hotel",
            status="pending",
            details={"hotel": approved["hotel"]},
        )
        db.add(hotel_booking)
        created_bookings.append(hotel_booking)

    for activity in approved.get("activities", []):
        activity_booking = Booking(
            trip_id=trip.id,
            type="activity",
            status="pending",
            details={"activity": activity},
        )
        db.add(activity_booking)
        created_bookings.append(activity_booking)

    trip.status = "booking"
    db.commit()
    for b in created_bookings:
        db.refresh(b)

    # Enqueue the Celery task — runs asynchronously
    execute_trip_bookings.delay(str(trip.id))

    return BookOut(
        trip_id=str(trip.id),
        status="booking",
        bookings=[{"id": str(b.id), "type": b.type, "status": b.status} for b in created_bookings],
    )


# ---------------------------------------------------------------------------
# Get booking status (polled by the frontend)
# ---------------------------------------------------------------------------

@router.get("/{trip_id}/bookings", response_model=list[BookingOut])
def list_bookings(
    trip_id: str,
    email: str = Depends(get_current_user_email),
    _key: str = Depends(require_internal_key),
    db: Session = Depends(get_db),
):
    """Return all bookings for a trip, each with their agent log entries."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    bookings = db.query(Booking).filter(Booking.trip_id == trip_id).all()
    return [_booking_to_out(b) for b in bookings]


# ---------------------------------------------------------------------------
# Consolidated confirmation (available once trip.status == "confirmed")
# ---------------------------------------------------------------------------

@router.get("/{trip_id}/confirmation")
def get_confirmation(
    trip_id: str,
    email: str = Depends(get_current_user_email),
    _key: str = Depends(require_internal_key),
    db: Session = Depends(get_db),
):
    """
    Return a structured confirmation dict for a confirmed trip.
    Includes PNR, hotel check-in/out, and activity names.
    """
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    if trip.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Trip is not confirmed yet (current status: {trip.status})",
        )

    bookings = db.query(Booking).filter(Booking.trip_id == trip_id).all()
    return build_confirmation(trip, bookings)


# ---------------------------------------------------------------------------
# Trip alerts (schedule changes, price drops)
# ---------------------------------------------------------------------------

@router.get("/{trip_id}/alerts", response_model=list[AlertOut])
def list_alerts(
    trip_id: str,
    email: str = Depends(get_current_user_email),
    _key: str = Depends(require_internal_key),
    db: Session = Depends(get_db),
):
    """Return all monitoring alerts for a confirmed trip, newest first."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    alerts = (
        db.query(TripAlert)
        .filter(TripAlert.trip_id == trip_id)
        .order_by(TripAlert.created_at.desc())
        .all()
    )
    return [
        AlertOut(
            id=str(a.id),
            alert_type=a.alert_type,
            message=a.message,
            details=a.details,
            is_read=a.is_read,
            created_at=a.created_at.isoformat(),
        )
        for a in alerts
    ]


@router.post("/{trip_id}/alerts/{alert_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_alert_read(
    trip_id: str,
    alert_id: str,
    email: str = Depends(get_current_user_email),
    _key: str = Depends(require_internal_key),
    db: Session = Depends(get_db),
):
    """Mark a single alert as read."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    alert = db.query(TripAlert).filter(TripAlert.id == alert_id, TripAlert.trip_id == trip_id).first()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert.is_read = True
    db.commit()


# ---------------------------------------------------------------------------
# Trip modification
# ---------------------------------------------------------------------------

@router.post("/{trip_id}/modify")
async def modify_trip(
    trip_id: str,
    data: ModifyIn,
    email: str = Depends(get_current_user_email),
    _key: str = Depends(require_internal_key),
    db: Session = Depends(get_db),
):
    """
    Apply a natural-language modification to a confirmed trip.

    Examples:
      - "extend my hotel by 2 nights"
      - "upgrade to business class"
      - "upgrade my room to a suite"
    """
    from app.services.modification import apply_modification

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    if trip.status not in ("confirmed", "booking_failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Modifications are only allowed on confirmed trips (current status: {trip.status})",
        )

    bookings = db.query(Booking).filter(Booking.trip_id == trip_id).all()
    result = await apply_modification(trip, bookings, data.request, db)
    return result
