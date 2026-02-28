"""
Trip modification service — apply natural-language change requests to confirmed bookings.

Supported modification types:
  - Hotel stay extension / shortening (e.g. "extend my hotel by 2 nights")
  - Seat upgrade request (e.g. "upgrade to business class")
  - Hotel room upgrade (e.g. "upgrade to a suite")

In mock mode the modifications are simulated; in live mode the booking agent
navigates the site and makes the change.

Usage:
    result = await apply_modification(trip, bookings, "extend my hotel by one night")
"""

import logging
import re
from datetime import date, timedelta
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def apply_modification(
    trip,           # app.models.Trip ORM object
    bookings: list, # list of app.models.Booking ORM objects
    request: str,   # plain-English modification request
    db,             # SQLAlchemy Session
) -> dict:
    """
    Parse a natural-language modification request and apply it to the trip's
    confirmed bookings.

    Returns:
        {
            "success": bool,
            "modification_type": str,
            "message": str,
            "updated_details": dict | None,
        }
    """
    parsed = _parse_modification_request(request)

    if parsed["type"] == "hotel_extend":
        return await _modify_hotel_extend(trip, bookings, parsed["nights"], db)

    if parsed["type"] == "hotel_shorten":
        return await _modify_hotel_shorten(trip, bookings, parsed["nights"], db)

    if parsed["type"] == "seat_upgrade":
        return await _modify_seat_upgrade(trip, bookings, parsed["cabin"], db)

    if parsed["type"] == "room_upgrade":
        return await _modify_room_upgrade(trip, bookings, parsed["room_type"], db)

    return {
        "success": False,
        "modification_type": "unknown",
        "message": (
            "Could not understand that modification request. "
            "Try: 'extend my hotel by 2 nights', 'upgrade to business class', "
            "or 'upgrade to a suite'."
        ),
        "updated_details": None,
    }


# ---------------------------------------------------------------------------
# Natural-language parser
# ---------------------------------------------------------------------------

def _parse_modification_request(request: str) -> dict:
    r = request.lower().strip()

    # Hotel extension: "extend hotel by N night(s)" / "add N more nights"
    m = re.search(
        r"(?:extend|add|extra|more)\s+(?:my\s+)?(?:hotel(?:\s+stay)?\s+)?(?:by\s+)?(\w+|\d+)\s+(?:more\s+)?night",
        r,
    )
    if m:
        nights = _word_to_int(m.group(1))
        return {"type": "hotel_extend", "nights": nights or 1}

    # Hotel shortening: "shorten/reduce hotel by N night(s)"
    m = re.search(
        r"(?:shorten|reduce|cut|fewer)\s+(?:my\s+)?(?:hotel(?:\s+stay)?\s+)?(?:by\s+)?(\w+|\d+)\s+night",
        r,
    )
    if m:
        nights = _word_to_int(m.group(1))
        return {"type": "hotel_shorten", "nights": nights or 1}

    # Seat / flight class upgrade
    if re.search(r"(business\s+class|first\s+class|premium\s+economy)", r):
        if "business" in r:
            cabin = "BUSINESS"
        elif "first" in r:
            cabin = "FIRST"
        else:
            cabin = "PREMIUM_ECONOMY"
        return {"type": "seat_upgrade", "cabin": cabin}

    # Room upgrade
    if re.search(r"(suite|upgrade\s+(?:my\s+)?(?:hotel\s+)?room|better\s+room|king\s+room)", r):
        if "suite" in r:
            room_type = "suite"
        elif "king" in r:
            room_type = "king"
        else:
            room_type = "deluxe"
        return {"type": "room_upgrade", "room_type": room_type}

    return {"type": "unknown"}


_WORD_MAP = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "a": 1, "an": 1,
}


def _word_to_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except ValueError:
        return _WORD_MAP.get(s.lower())


# ---------------------------------------------------------------------------
# Modification handlers
# ---------------------------------------------------------------------------

async def _modify_hotel_extend(trip, bookings, nights: int, db) -> dict:
    hotel_booking = _find_booking(bookings, "hotel")
    if not hotel_booking:
        return _err("No confirmed hotel booking found on this trip.")

    details = hotel_booking.details or {}
    hotel = details.get("hotel", {})
    check_out_str = hotel.get("check_out", "")

    try:
        check_out = date.fromisoformat(check_out_str)
    except ValueError:
        return _err(f"Could not parse hotel check-out date: {check_out_str!r}")

    new_check_out = check_out + timedelta(days=nights)

    if settings.booking_mock_mode:
        updated = _mock_hotel_date_change(hotel, "check_out", new_check_out.isoformat())
    else:
        updated = await _live_hotel_modify(
            hotel_booking, hotel,
            field="check_out",
            new_value=new_check_out.isoformat(),
            nights_delta=nights,
        )
        if not updated:
            return _err("Live hotel modification failed. Please contact the hotel directly.")

    hotel_booking.details = {**details, "hotel": updated}
    db.commit()

    price_per_night = hotel.get("price_per_night_usd", 0)
    extra_cost = round(price_per_night * nights, 2)

    return {
        "success": True,
        "modification_type": "hotel_extend",
        "message": (
            f"Hotel check-out extended by {nights} night(s) to {new_check_out.isoformat()}."
            + (f" Estimated extra cost: ${extra_cost:,.2f}." if extra_cost else "")
        ),
        "updated_details": updated,
    }


async def _modify_hotel_shorten(trip, bookings, nights: int, db) -> dict:
    hotel_booking = _find_booking(bookings, "hotel")
    if not hotel_booking:
        return _err("No confirmed hotel booking found on this trip.")

    details = hotel_booking.details or {}
    hotel = details.get("hotel", {})
    check_out_str = hotel.get("check_out", "")
    check_in_str = hotel.get("check_in", "")

    try:
        check_out = date.fromisoformat(check_out_str)
        check_in = date.fromisoformat(check_in_str)
    except ValueError:
        return _err("Could not parse hotel dates.")

    new_check_out = check_out - timedelta(days=nights)
    if new_check_out <= check_in:
        return _err("Cannot shorten the stay — that would result in a zero or negative duration.")

    if settings.booking_mock_mode:
        updated = _mock_hotel_date_change(hotel, "check_out", new_check_out.isoformat())
    else:
        updated = await _live_hotel_modify(
            hotel_booking, hotel,
            field="check_out",
            new_value=new_check_out.isoformat(),
            nights_delta=-nights,
        )
        if not updated:
            return _err("Live hotel modification failed. Please contact the hotel directly.")

    hotel_booking.details = {**details, "hotel": updated}
    db.commit()

    return {
        "success": True,
        "modification_type": "hotel_shorten",
        "message": f"Hotel check-out moved up by {nights} night(s) to {new_check_out.isoformat()}.",
        "updated_details": updated,
    }


async def _modify_seat_upgrade(trip, bookings, cabin: str, db) -> dict:
    flight_booking = _find_booking(bookings, "flight")
    if not flight_booking:
        return _err("No confirmed flight booking found on this trip.")

    details = flight_booking.details or {}
    flight = details.get("flight", {})
    current_cabin = flight.get("cabin", "ECONOMY")

    if current_cabin == cabin:
        return _err(f"Flight is already booked in {cabin}.")

    if settings.booking_mock_mode:
        updated_flight = {**flight, "cabin": cabin}
        cabin_premiums = {"PREMIUM_ECONOMY": 350, "BUSINESS": 1200, "FIRST": 2500}
        upgrade_cost = cabin_premiums.get(cabin, 0) - cabin_premiums.get(current_cabin, 0)
    else:
        return _err(
            "Live seat upgrades require contacting the airline directly. "
            "Please call the carrier to request an upgrade."
        )

    flight_booking.details = {**details, "flight": updated_flight}
    db.commit()

    cabin_label = cabin.replace("_", " ").title()
    return {
        "success": True,
        "modification_type": "seat_upgrade",
        "message": (
            f"Cabin upgraded from {current_cabin.replace('_', ' ').title()} "
            f"to {cabin_label}. Estimated upgrade cost: ${upgrade_cost:,}."
        ),
        "updated_details": updated_flight,
    }


async def _modify_room_upgrade(trip, bookings, room_type: str, db) -> dict:
    hotel_booking = _find_booking(bookings, "hotel")
    if not hotel_booking:
        return _err("No confirmed hotel booking found on this trip.")

    details = hotel_booking.details or {}
    hotel = details.get("hotel", {})
    current_room = hotel.get("room_type", "Standard Room")

    if settings.booking_mock_mode:
        type_map = {"suite": "Junior Suite", "king": "King Room", "deluxe": "Deluxe Room"}
        new_room = type_map.get(room_type, "Upgraded Room")
        cost_map = {"suite": 150, "king": 50, "deluxe": 80}
        extra_per_night = cost_map.get(room_type, 60)
        nights_str = hotel.get("check_out", ""), hotel.get("check_in", "")
        try:
            nights = (date.fromisoformat(nights_str[0]) - date.fromisoformat(nights_str[1])).days
        except ValueError:
            nights = 1
        extra_total = extra_per_night * max(nights, 1)
        updated_hotel = {**hotel, "room_type": new_room}
    else:
        return _err(
            "Live room upgrades require contacting the hotel directly. "
            "Please call the property or use their app to request a room change."
        )

    hotel_booking.details = {**details, "hotel": updated_hotel}
    db.commit()

    return {
        "success": True,
        "modification_type": "room_upgrade",
        "message": (
            f"Room upgraded from {current_room!r} to {new_room!r}. "
            f"Estimated extra cost: ${extra_total:,.2f}."
        ),
        "updated_details": updated_hotel,
    }


# ---------------------------------------------------------------------------
# Live booking-agent based hotel date modification
# ---------------------------------------------------------------------------

async def _live_hotel_modify(booking, hotel: dict, field: str, new_value: str, nights_delta: int):
    """Use the booking agent to modify hotel dates on the booking site."""
    try:
        from app.services.booking_agent import BookingAgent
        import sqlite3  # not used, just importing to confirm DB availability

        # We can't pass a real DB session here, so we just signal not supported
        raise NotImplementedError("Live hotel modification via browser agent not yet implemented.")
    except Exception as exc:
        logger.warning("[modification] live hotel modify failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_booking(bookings, btype: str):
    for b in bookings:
        if b.type == btype and b.status == "confirmed":
            return b
    return None


def _mock_hotel_date_change(hotel: dict, field: str, new_value: str) -> dict:
    return {**hotel, field: new_value}


def _err(message: str) -> dict:
    return {
        "success": False,
        "modification_type": "error",
        "message": message,
        "updated_details": None,
    }
