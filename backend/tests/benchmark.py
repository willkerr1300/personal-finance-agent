"""
Performance benchmark for Travel Planner backend services.

Tests the following without requiring a live database or external APIs:
  1. Rule-based trip parser (parse_trip_request)
  2. Itinerary builder (build_itinerary_options)
  3. Mock booking agent (BookingAgent.run in BOOKING_MOCK_MODE)
  4. Modification parser (_parse_modification_request)
  5. Monitor mock functions (check_flight_changes, check_price_drops)

Run from the backend directory:
    python -m tests.benchmark

Or with PYTHONPATH set:
    cd backend && python tests/benchmark.py
"""

import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

# Ensure backend/app is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# Force mock mode so no external services are needed
os.environ.setdefault("DATABASE_URL", "postgresql://travelplanner:travelplanner@localhost:5432/travelplanner")
os.environ.setdefault("INTERNAL_API_KEY", "benchmark-key")
os.environ.setdefault("ENCRYPTION_KEY", "P5Hp8j8BsNmBFLqQpwXOXp8URO5cPbSJeJi8NJGwrgs=")
os.environ.setdefault("BOOKING_MOCK_MODE", "true")
os.environ.setdefault("AMADEUS_CLIENT_ID", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("STRIPE_SECRET_KEY", "")
os.environ.setdefault("SENDGRID_API_KEY", "")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")


# ---------------------------------------------------------------------------
# Timer utility
# ---------------------------------------------------------------------------

def bench(label: str, fn, iterations: int = 50) -> dict:
    """Run `fn()` `iterations` times and return timing stats in milliseconds."""
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        result = fn()
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)

    stats = {
        "label": label,
        "iterations": iterations,
        "mean_ms": round(statistics.mean(times), 2),
        "median_ms": round(statistics.median(times), 2),
        "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 2),
        "p99_ms": round(sorted(times)[int(len(times) * 0.99)], 2),
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
    }
    return stats


async def abench(label: str, afn, iterations: int = 30) -> dict:
    """Async variant of bench()."""
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await afn()
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)

    stats = {
        "label": label,
        "iterations": iterations,
        "mean_ms": round(statistics.mean(times), 2),
        "median_ms": round(statistics.median(times), 2),
        "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 2),
        "p99_ms": round(sorted(times)[int(len(times) * 0.99)], 2),
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
    }
    return stats


def print_result(stats: dict) -> None:
    print(
        f"  {stats['label']:<50} "
        f"mean={stats['mean_ms']:>7.1f}ms  "
        f"p50={stats['median_ms']:>7.1f}ms  "
        f"p95={stats['p95_ms']:>7.1f}ms  "
        f"p99={stats['p99_ms']:>7.1f}ms  "
        f"(n={stats['iterations']})"
    )


# ---------------------------------------------------------------------------
# Benchmark implementations
# ---------------------------------------------------------------------------

SAMPLE_REQUESTS = [
    "Fly me to Tokyo in June for 10 days, budget $3000, hotel near Shinjuku",
    "I need flights from NYC to London next March, business class, 7 nights, $5000",
    "Weekend trip to Miami in August, budget $1200",
    "Family vacation to Paris in July, 4 people, 2 weeks, $10000 budget",
    "Quick trip to Chicago next Friday returning Sunday, under $800",
]

SAMPLE_FLIGHTS = [
    {"carrier": "UA", "flight_number": "UA123", "price_usd": 850,
     "origin": "LAX", "destination": "NRT", "cabin": "ECONOMY",
     "depart_datetime": "2026-06-15T10:30:00", "stops": 0, "duration_minutes": 600},
    {"carrier": "DL", "flight_number": "DL456", "price_usd": 720,
     "origin": "JFK", "destination": "LHR", "cabin": "ECONOMY",
     "depart_datetime": "2026-07-01T08:00:00", "stops": 0, "duration_minutes": 420},
    {"carrier": "AA", "flight_number": "AA789", "price_usd": 1200,
     "origin": "ORD", "destination": "CDG", "cabin": "BUSINESS",
     "depart_datetime": "2026-08-10T14:00:00", "stops": 1, "duration_minutes": 540},
]

SAMPLE_HOTELS = [
    {"name": "Park Hyatt Tokyo", "stars": 5, "price_per_night_usd": 420,
     "price_total_usd": 4200, "check_in": "2026-06-15", "check_out": "2026-06-25",
     "room_type": "Deluxe King", "city_code": "TYO"},
    {"name": "Premier Inn London City", "stars": 3, "price_per_night_usd": 180,
     "price_total_usd": 1260, "check_in": "2026-07-01", "check_out": "2026-07-08",
     "room_type": "Standard", "city_code": "LON"},
]

MODIFICATION_REQUESTS = [
    "extend my hotel by 2 nights",
    "extend hotel stay by one night",
    "add 3 more nights to my hotel",
    "upgrade to business class",
    "upgrade to first class",
    "upgrade my room to a suite",
    "shorten my hotel by 1 night",
    "reduce hotel stay by two nights",
]


async def run_benchmarks():
    results = []
    all_stats = []

    print("\n" + "=" * 90)
    print("  TRAVEL PLANNER — PERFORMANCE BENCHMARK")
    print("=" * 90)

    # ------------------------------------------------------------------
    # 1. Rule-based trip parser
    # ------------------------------------------------------------------
    print("\n[1] Trip Parser (rule-based, no Claude API)")
    try:
        from app.services.trip_parser import _parse_with_rules

        for req in SAMPLE_REQUESTS[:3]:
            stats = bench(f"parse: {req[:45]}...", lambda r=req: _parse_with_rules(r))
            print_result(stats)
            all_stats.append(stats)

        # Aggregate
        means = [s["mean_ms"] for s in all_stats[-3:]]
        p95s = [s["p95_ms"] for s in all_stats[-3:]]
        agg = {
            "label": "RULE-BASED PARSER (aggregate)",
            "mean_ms": round(statistics.mean(means), 2),
            "p95_ms": round(max(p95s), 2),
        }
        results.append(agg)
        print(f"\n  --> Parser mean: {agg['mean_ms']}ms | p95: {agg['p95_ms']}ms")
    except Exception as e:
        print(f"  [SKIP] {e}")

    # ------------------------------------------------------------------
    # 2. Itinerary builder
    # ------------------------------------------------------------------
    print("\n[2] Itinerary Builder (build_itinerary_options)")
    try:
        from app.services.itinerary import build_itinerary_options
        from app.services.amadeus import _mock_flights, _mock_hotels, _mock_activities

        flights = _mock_flights("LAX", "NRT", "2026-06-15", "ECONOMY")
        hotels = _mock_hotels("TYO", "2026-06-15", "2026-06-25")
        activities = _mock_activities("TYO", "2026-06-15", "2026-06-25")

        stats = bench(
            "build_itinerary_options (3 flights, 3 hotels, 3 acts)",
            lambda: build_itinerary_options(flights, hotels, 3000.0, activities),
            iterations=200,
        )
        print_result(stats)
        all_stats.append(stats)
        results.append({"label": "ITINERARY BUILDER", "mean_ms": stats["mean_ms"], "p95_ms": stats["p95_ms"]})
        print(f"\n  --> Itinerary builder mean: {stats['mean_ms']}ms | p95: {stats['p95_ms']}ms")
    except Exception as e:
        print(f"  [SKIP] {e}")

    # ------------------------------------------------------------------
    # 3. Modification parser
    # ------------------------------------------------------------------
    print("\n[3] Modification Parser (_parse_modification_request)")
    try:
        from app.services.modification import _parse_modification_request

        mod_stats = []
        for req in MODIFICATION_REQUESTS:
            s = bench(f"modify: {req}", lambda r=req: _parse_modification_request(r), iterations=500)
            print_result(s)
            mod_stats.append(s)

        means = [s["mean_ms"] for s in mod_stats]
        p95s = [s["p95_ms"] for s in mod_stats]
        agg = {
            "label": "MODIFICATION PARSER (aggregate)",
            "mean_ms": round(statistics.mean(means), 2),
            "p95_ms": round(max(p95s), 2),
        }
        results.append(agg)
        print(f"\n  --> Modification parser mean: {agg['mean_ms']}ms | p95: {agg['p95_ms']}ms")
    except Exception as e:
        print(f"  [SKIP] {e}")

    # ------------------------------------------------------------------
    # 4. Monitor: mock flight change detection
    # ------------------------------------------------------------------
    print("\n[4] Trip Monitor — mock flight change detection")
    try:
        from app.services.monitor import check_flight_changes, check_price_drops

        flight_stats = []
        for f in SAMPLE_FLIGHTS:
            s = await abench(
                f"check_flight_changes: {f['carrier']}{f['flight_number']}",
                lambda fl=f: check_flight_changes(fl),
                iterations=100,
            )
            print_result(s)
            flight_stats.append(s)

        price_stats = []
        for f in SAMPLE_FLIGHTS:
            s = await abench(
                f"check_price_drops: {f['carrier']}{f['flight_number']}",
                lambda fl=f: check_price_drops(fl, fl["price_usd"]),
                iterations=100,
            )
            print_result(s)
            price_stats.append(s)

        all_monitor = flight_stats + price_stats
        means = [s["mean_ms"] for s in all_monitor]
        p95s = [s["p95_ms"] for s in all_monitor]
        agg = {
            "label": "MONITOR SERVICE (aggregate)",
            "mean_ms": round(statistics.mean(means), 2),
            "p95_ms": round(max(p95s), 2),
        }
        results.append(agg)
        print(f"\n  --> Monitor mean: {agg['mean_ms']}ms | p95: {agg['p95_ms']}ms")
    except Exception as e:
        print(f"  [SKIP] {e}")

    # ------------------------------------------------------------------
    # 5. Mock booking agent (simulates full booking flow)
    # ------------------------------------------------------------------
    print("\n[5] Mock Booking Agent (simulate full flight booking)")
    try:
        import uuid
        from unittest.mock import MagicMock
        from app.services.booking_agent import BookingAgent

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        itinerary = {
            "flight": SAMPLE_FLIGHTS[0],
            "hotel": SAMPLE_HOTELS[0],
        }
        traveler = {
            "first_name": "John", "last_name": "Doe",
            "date_of_birth": "1990-01-15", "phone": "+1-555-0100",
            "email": "john@example.com", "seat_preference": "aisle",
            "meal_preference": "standard", "loyalty_numbers": [],
            "passport_number": "US123456", "tsa_number": "123456789",
        }
        virtual_card = {
            "card_id": "ic_test_123",
            "card_number": "4111111111111111",
            "exp_month": 12, "exp_year": 2027,
            "cvc": "123", "card_type": "mock",
        }

        booking_agent_stats = []
        for btype in ("flight", "hotel"):
            s = await abench(
                f"BookingAgent.run (mock, {btype})",
                lambda bt=btype: BookingAgent(booking_id=str(uuid.uuid4()), db=mock_db).run(
                    booking_type=bt,
                    itinerary=itinerary,
                    traveler=traveler,
                    virtual_card=virtual_card,
                ),
                iterations=20,
            )
            print_result(s)
            booking_agent_stats.append(s)

        means = [s["mean_ms"] for s in booking_agent_stats]
        p95s = [s["p95_ms"] for s in booking_agent_stats]
        agg = {
            "label": "BOOKING AGENT mock (aggregate)",
            "mean_ms": round(statistics.mean(means), 2),
            "p95_ms": round(max(p95s), 2),
        }
        results.append(agg)
        print(f"\n  --> Booking agent mean: {agg['mean_ms']}ms | p95: {agg['p95_ms']}ms")
    except Exception as e:
        print(f"  [SKIP] {e}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 90)
    print("  SUMMARY")
    print("=" * 90)
    for r in results:
        print(f"  {r['label']:<50} mean={r['mean_ms']:>8.2f}ms   p95={r['p95_ms']:>8.2f}ms")

    print("\n" + "=" * 90)

    return results


if __name__ == "__main__":
    asyncio.run(run_benchmarks())
