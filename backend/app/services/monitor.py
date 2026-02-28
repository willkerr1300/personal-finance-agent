"""
Trip monitoring service — flight change detection and price-drop alerts.

In mock mode (BOOKING_MOCK_MODE=true or no Amadeus credentials), this uses
realistic simulated responses so the full pipeline can be exercised without
hitting live APIs.

Called by the Celery beat task in app.tasks.monitor_tasks every hour.
"""

import logging
import random
from datetime import datetime, timedelta

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def check_flight_changes(booking: dict) -> list[dict]:
    """
    Check whether a confirmed flight booking has schedule changes or cancellations.

    Args:
        booking: Booking details dict (booking.details["flight"]).

    Returns:
        List of alert dicts:
          {alert_type, message, details: {field, old_value, new_value}}
        Empty list = no changes detected.
    """
    if settings.booking_mock_mode or not settings.amadeus_client_id:
        return _mock_flight_changes(booking)
    return await _live_flight_changes(booking)


async def check_price_drops(booking: dict, original_price_usd: float) -> list[dict]:
    """
    Check whether a cheaper fare is now available for a confirmed flight booking.

    Args:
        booking: Booking details dict (booking.details["flight"]).
        original_price_usd: Price paid at booking time.

    Returns:
        List of alert dicts with alert_type="price_drop", or empty list.
    """
    if settings.booking_mock_mode or not settings.amadeus_client_id:
        return _mock_price_drop(booking, original_price_usd)
    return await _live_price_drop(booking, original_price_usd)


# ---------------------------------------------------------------------------
# Mock implementations (no external calls)
# ---------------------------------------------------------------------------

# Seed-based so repeated calls for the same booking return consistent results
def _mock_flight_changes(booking: dict) -> list[dict]:
    carrier = booking.get("carrier", "")
    flight_number = booking.get("flight_number", "")
    seed_str = f"{carrier}{flight_number}"
    rng = random.Random(sum(ord(c) for c in seed_str))

    # ~8% chance of a schedule change per monitoring cycle
    if rng.random() > 0.08:
        return []

    change_type = rng.choice(["departure_time", "arrival_time", "gate"])
    old_time = booking.get("depart_datetime", "2026-06-01T08:00:00")
    try:
        dt = datetime.fromisoformat(old_time)
    except ValueError:
        dt = datetime(2026, 6, 1, 8, 0)

    shift_minutes = rng.choice([-30, -15, 15, 30, 45, 60, 90])
    new_dt = dt + timedelta(minutes=shift_minutes)

    if change_type == "departure_time":
        direction = "earlier" if shift_minutes < 0 else "later"
        message = (
            f"{carrier} {flight_number}: departure rescheduled "
            f"{abs(shift_minutes)} min {direction} "
            f"(now {new_dt.strftime('%H:%M')})"
        )
        return [
            {
                "alert_type": "schedule_change",
                "message": message,
                "details": {
                    "field": "departure_time",
                    "old_value": old_time,
                    "new_value": new_dt.isoformat(),
                    "carrier": carrier,
                    "flight_number": flight_number,
                },
            }
        ]

    if change_type == "arrival_time":
        new_arr_dt = new_dt + timedelta(hours=rng.randint(2, 10))
        message = (
            f"{carrier} {flight_number}: estimated arrival updated to "
            f"{new_arr_dt.strftime('%H:%M')}"
        )
        return [
            {
                "alert_type": "schedule_change",
                "message": message,
                "details": {
                    "field": "arrival_time",
                    "old_value": "",
                    "new_value": new_arr_dt.isoformat(),
                    "carrier": carrier,
                    "flight_number": flight_number,
                },
            }
        ]

    # gate change
    gates = ["A12", "B7", "C22", "D4", "E18", "F3"]
    new_gate = rng.choice(gates)
    message = f"{carrier} {flight_number}: gate changed to {new_gate}"
    return [
        {
            "alert_type": "schedule_change",
            "message": message,
            "details": {
                "field": "gate",
                "old_value": "TBD",
                "new_value": new_gate,
                "carrier": carrier,
                "flight_number": flight_number,
            },
        }
    ]


def _mock_price_drop(booking: dict, original_price_usd: float) -> list[dict]:
    carrier = booking.get("carrier", "")
    flight_number = booking.get("flight_number", "")
    seed_str = f"pd{carrier}{flight_number}"
    rng = random.Random(sum(ord(c) for c in seed_str))

    # ~12% chance of a meaningful price drop
    if rng.random() > 0.12:
        return []

    drop_pct = rng.uniform(0.08, 0.28)  # 8-28% cheaper
    new_price = round(original_price_usd * (1 - drop_pct), 2)
    savings = round(original_price_usd - new_price, 2)

    message = (
        f"Price drop alert: {carrier} {flight_number} is now "
        f"${new_price:,.2f} (was ${original_price_usd:,.2f}) — "
        f"you could save ${savings:,.2f} if your ticket is refundable."
    )
    return [
        {
            "alert_type": "price_drop",
            "message": message,
            "details": {
                "carrier": carrier,
                "flight_number": flight_number,
                "original_price_usd": original_price_usd,
                "new_price_usd": new_price,
                "savings_usd": savings,
            },
        }
    ]


# ---------------------------------------------------------------------------
# Live implementations (Amadeus API)
# ---------------------------------------------------------------------------

async def _live_flight_changes(booking: dict) -> list[dict]:
    """
    Check for schedule changes via the Amadeus Flight Delay Prediction or
    Order Management API (available in production tier).

    Falls back to empty list on any error so monitoring doesn't block.
    """
    try:
        import httpx

        carrier = booking.get("carrier", "")
        flight_number = booking.get("flight_number", "")
        depart_date = (booking.get("depart_datetime", "") or "")[:10]

        if not (carrier and flight_number and depart_date):
            return []

        token = await _get_amadeus_token()
        base = (
            "https://api.amadeus.com"
            if settings.amadeus_env == "production"
            else "https://test.api.amadeus.com"
        )

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base}/v2/schedule/flights",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "carrierCode": carrier,
                    "flightNumber": flight_number.lstrip(carrier),
                    "scheduledDepartureDate": depart_date,
                },
            )
            if resp.status_code != 200:
                return []

            data = resp.json().get("data", [])
            if not data:
                return []

            flight = data[0]
            dep_info = flight.get("flightPoints", [{}])[0]
            actual_dt = (
                dep_info.get("departure", {})
                .get("timings", [{}])[0]
                .get("value", "")
            )
            original_dt = booking.get("depart_datetime", "")

            if actual_dt and actual_dt != original_dt:
                return [
                    {
                        "alert_type": "schedule_change",
                        "message": (
                            f"{carrier} {flight_number}: departure rescheduled "
                            f"to {actual_dt[:16].replace('T', ' ')}"
                        ),
                        "details": {
                            "field": "departure_time",
                            "old_value": original_dt,
                            "new_value": actual_dt,
                            "carrier": carrier,
                            "flight_number": flight_number,
                        },
                    }
                ]
    except Exception as exc:
        logger.warning("[monitor] live flight check failed: %s", exc)

    return []


async def _live_price_drop(booking: dict, original_price_usd: float) -> list[dict]:
    """Re-search Amadeus for the same route and compare price to original."""
    try:
        import httpx

        origin = booking.get("origin", "")
        destination = booking.get("destination", "")
        depart_date = (booking.get("depart_datetime", "") or "")[:10]
        carrier = booking.get("carrier", "")
        flight_number = booking.get("flight_number", "")

        if not (origin and destination and depart_date):
            return []

        token = await _get_amadeus_token()
        base = (
            "https://api.amadeus.com"
            if settings.amadeus_env == "production"
            else "https://test.api.amadeus.com"
        )

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base}/v2/shopping/flight-offers",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "originLocationCode": origin,
                    "destinationLocationCode": destination,
                    "departureDate": depart_date,
                    "adults": 1,
                    "max": 5,
                },
            )
            if resp.status_code != 200:
                return []

            offers = resp.json().get("data", [])
            if not offers:
                return []

            cheapest = min(
                float(o.get("price", {}).get("grandTotal", original_price_usd))
                for o in offers
            )
            if cheapest < original_price_usd * 0.92:  # at least 8% cheaper
                savings = round(original_price_usd - cheapest, 2)
                return [
                    {
                        "alert_type": "price_drop",
                        "message": (
                            f"Price drop: {origin}→{destination} now available "
                            f"from ${cheapest:,.2f} (you paid ${original_price_usd:,.2f}) "
                            f"— save ${savings:,.2f} if your ticket is refundable."
                        ),
                        "details": {
                            "carrier": carrier,
                            "flight_number": flight_number,
                            "original_price_usd": original_price_usd,
                            "new_price_usd": cheapest,
                            "savings_usd": savings,
                        },
                    }
                ]
    except Exception as exc:
        logger.warning("[monitor] live price drop check failed: %s", exc)

    return []


async def _get_amadeus_token() -> str:
    import httpx

    base = (
        "https://api.amadeus.com"
        if settings.amadeus_env == "production"
        else "https://test.api.amadeus.com"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{base}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.amadeus_client_id,
                "client_secret": settings.amadeus_client_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
