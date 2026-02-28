"""
Celery beat periodic task — trip monitoring.

Runs every hour. For each confirmed trip, checks:
  1. Flight schedule changes (gate, time, cancellation)
  2. Price drops on confirmed flight bookings

Alerts are written to the trip_alerts table and, if new, emailed to the user.

Start the beat scheduler alongside the worker:
    celery -A app.worker worker --beat --loglevel=info

Or as a separate process:
    celery -A app.worker beat --loglevel=info
"""

import asyncio
import logging

from app.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.monitor_tasks.scan_confirmed_trips")
def scan_confirmed_trips() -> None:
    """Celery entry point — delegates to the async implementation."""
    try:
        asyncio.run(_async_scan_confirmed_trips())
    except Exception as exc:
        logger.error("[monitor_tasks] scan failed: %s", exc, exc_info=True)


async def _async_scan_confirmed_trips() -> None:
    from app.database import SessionLocal
    from app.models import Booking, Trip, TripAlert, User
    from app.services.monitor import check_flight_changes, check_price_drops
    from app.services.email import send_alert_email

    db = SessionLocal()
    try:
        confirmed_trips = (
            db.query(Trip).filter(Trip.status == "confirmed").all()
        )
        logger.info("[monitor] scanning %d confirmed trip(s)", len(confirmed_trips))

        for trip in confirmed_trips:
            user = db.query(User).filter(User.id == trip.user_id).first()
            if not user:
                continue

            flight_bookings = (
                db.query(Booking)
                .filter(
                    Booking.trip_id == trip.id,
                    Booking.type == "flight",
                    Booking.status == "confirmed",
                )
                .all()
            )

            new_alerts: list[TripAlert] = []

            for booking in flight_bookings:
                details = booking.details or {}
                flight = details.get("flight", {})

                # --- Schedule changes ---
                changes = await check_flight_changes(flight)
                for change in changes:
                    if not _alert_already_exists(db, trip.id, change):
                        alert = TripAlert(
                            trip_id=trip.id,
                            alert_type=change["alert_type"],
                            message=change["message"],
                            details=change.get("details", {}),
                        )
                        db.add(alert)
                        new_alerts.append(alert)

                # --- Price drops ---
                original_price = float(flight.get("price_usd", 0) or 0)
                if original_price > 0:
                    drops = await check_price_drops(flight, original_price)
                    for drop in drops:
                        if not _alert_already_exists(db, trip.id, drop):
                            alert = TripAlert(
                                trip_id=trip.id,
                                alert_type=drop["alert_type"],
                                message=drop["message"],
                                details=drop.get("details", {}),
                            )
                            db.add(alert)
                            new_alerts.append(alert)

            if new_alerts:
                db.commit()
                for alert in new_alerts:
                    db.refresh(alert)

                # Email user about new alerts (best-effort)
                try:
                    spec = trip.parsed_spec or {}
                    destination = spec.get("destination_city") or spec.get("destination", "your trip")
                    user_name = (
                        f"{user.first_name or ''} {user.last_name or ''}".strip()
                        or user.email
                    )
                    await send_alert_email(
                        user_email=user.email,
                        user_name=user_name,
                        destination=destination,
                        alerts=[{"alert_type": a.alert_type, "message": a.message} for a in new_alerts],
                    )
                except Exception as exc:
                    logger.warning("[monitor_tasks] alert email failed for trip %s: %s", trip.id, exc)

        logger.info("[monitor] scan complete — %d trip(s) checked", len(confirmed_trips))

    finally:
        db.close()


def _alert_already_exists(db, trip_id, alert_dict: dict) -> bool:
    """
    Deduplicate by (trip_id, alert_type, message).
    Prevents re-alerting the same schedule change on every scan cycle.
    """
    from app.models import TripAlert

    return (
        db.query(TripAlert)
        .filter(
            TripAlert.trip_id == trip_id,
            TripAlert.alert_type == alert_dict["alert_type"],
            TripAlert.message == alert_dict["message"],
        )
        .first()
        is not None
    )
