from sqlalchemy import Column, String, DateTime, JSON, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)

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

    # Status flow: parsing → searching → options_ready → approved | search_failed | failed
    status = Column(String(50), nullable=False, default="parsing")

    # Original plain-English request from the user
    raw_request = Column(Text, nullable=False)

    # Structured spec extracted by the trip parser (Claude)
    # {origin, destination, destination_city, depart_date, return_date,
    #  budget_total, num_travelers, cabin_class, hotel_area, notes}
    parsed_spec = Column(JSON, nullable=True)

    # List of 2-3 itinerary option objects built by the itinerary service
    itinerary_options = Column(JSON, nullable=True)

    # The specific option the user approved
    approved_itinerary = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="trips")
    bookings = relationship("Booking", back_populates="trip", cascade="all, delete-orphan")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False, index=True)

    type = Column(String(50), nullable=False)   # flight | hotel | activity
    status = Column(String(50), nullable=False, default="pending")  # pending | confirmed | failed

    confirmation_number = Column(String, nullable=True)
    details = Column(JSON, nullable=True)  # carrier, PNR, hotel name, check-in, etc.

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    trip = relationship("Trip", back_populates="bookings")
