from sqlalchemy import Column, String, DateTime, JSON, Text, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)

    # Personal info — needed by the booking agent to fill passenger forms
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    date_of_birth = Column(String(10), nullable=True)  # YYYY-MM-DD, plaintext
    phone = Column(String(30), nullable=True)

    # Encrypted at the application layer using Fernet before writing to DB
    passport_number_enc = Column(String, nullable=True)
    tsa_known_traveler_enc = Column(String, nullable=True)

    # Plain-text preferences — not sensitive
    seat_preference = Column(String(50), nullable=True)
    meal_preference = Column(String(50), nullable=True)

    # JSON array of {program: str, number: str}
    loyalty_numbers = Column(JSON, nullable=True, default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    trips = relationship("Trip", back_populates="user", cascade="all, delete-orphan")


class Trip(Base):
    __tablename__ = "trips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Status flow: parsing → searching → options_ready → approved →
    #              booking → confirmed | booking_failed | failed
    status = Column(String(50), nullable=False, default="parsing")

    # Original plain-English request from the user
    raw_request = Column(Text, nullable=False)

    # Structured spec extracted by the trip parser (Claude)
    parsed_spec = Column(JSON, nullable=True)

    # List of 2-3 itinerary option objects built by the itinerary service
    itinerary_options = Column(JSON, nullable=True)

    # The specific option the user approved
    approved_itinerary = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="trips")
    bookings = relationship("Booking", back_populates="trip", cascade="all, delete-orphan")
    alerts = relationship("TripAlert", back_populates="trip", cascade="all, delete-orphan",
                          order_by="TripAlert.created_at.desc()")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False, index=True)

    type = Column(String(50), nullable=False)   # flight | hotel | activity
    # pending → in_progress → confirmed | failed | unsupported
    status = Column(String(50), nullable=False, default="pending")

    confirmation_number = Column(String, nullable=True)
    details = Column(JSON, nullable=True)  # carrier, PNR, hotel name, check-in, etc.

    # Stripe Issuing card ID — kept so we can void the card if booking fails
    virtual_card_id = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    trip = relationship("Trip", back_populates="bookings")
    agent_logs = relationship("AgentLog", back_populates="booking", cascade="all, delete-orphan",
                              order_by="AgentLog.created_at")


class AgentLog(Base):
    """Step-by-step log of the booking agent's actions for one booking."""
    __tablename__ = "agent_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, index=True)

    # e.g. "navigate", "fill_passenger", "select_seat", "payment", "confirm"
    step = Column(String(100), nullable=False)
    # Human-readable description of the action taken
    action = Column(Text, nullable=False)
    # "success" | "in_progress" | "error"
    result = Column(String(20), nullable=False)

    # Base64-encoded PNG screenshot at this step (only stored for errors + final confirm)
    screenshot_b64 = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    booking = relationship("Booking", back_populates="agent_logs")


class TripAlert(Base):
    """Schedule change or price-drop alert for a confirmed trip."""
    __tablename__ = "trip_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True)

    # "schedule_change" | "price_drop" | "cancellation"
    alert_type = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    is_read = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    trip = relationship("Trip", back_populates="alerts")
