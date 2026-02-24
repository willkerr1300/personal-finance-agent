"""
Itinerary builder — combines Amadeus flight + hotel search results into
2-3 curated option packages (Budget, Best Value, Premium).
"""

from typing import Optional


def _extract_flight(offer: dict) -> Optional[dict]:
    """Flatten an Amadeus flight offer into a compact dict."""
    try:
        price = float(offer["price"]["grandTotal"])
        itineraries = offer["itineraries"]

        segments: list[dict] = []
        for itin in itineraries:
            for seg in itin["segments"]:
                segments.append(
                    {
                        "from": seg["departure"]["iataCode"],
                        "departs": seg["departure"]["at"],
                        "to": seg["arrival"]["iataCode"],
                        "arrives": seg["arrival"]["at"],
                        "flight": seg["carrierCode"] + seg["number"],
                        "carrier": seg["carrierCode"],
                        "duration": seg.get("duration", ""),
                    }
                )

        outbound_segments = itineraries[0]["segments"] if itineraries else []
        outbound_stops = len(outbound_segments) - 1

        return {
            "id": offer.get("id", ""),
            "price_usd": price,
            "cabin": (
                offer["travelerPricings"][0]["fareDetailsBySegment"][0].get("cabin", "ECONOMY")
                if offer.get("travelerPricings")
                else "ECONOMY"
            ),
            "outbound_stops": outbound_stops,
            "outbound_duration": itineraries[0].get("duration", "") if itineraries else "",
            "carrier": offer.get("validatingAirlineCodes", [""])[0],
            "segments": segments,
        }
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def _extract_hotel(offer_data: dict) -> Optional[dict]:
    """Flatten an Amadeus hotel offer data block into a compact dict."""
    try:
        hotel = offer_data["hotel"]
        offers = offer_data.get("offers", [])
        if not offers:
            return None

        best = offers[0]
        price = float(best["price"]["total"])

        return {
            "hotel_id": hotel.get("hotelId", ""),
            "name": hotel.get("name", ""),
            "rating": hotel.get("rating", ""),
            "city_code": hotel.get("cityCode", ""),
            "price_total_usd": price,
            "check_in": best.get("checkInDate", ""),
            "check_out": best.get("checkOutDate", ""),
            "room_type": best.get("room", {}).get("typeEstimated", {}).get("category", ""),
            "beds": best.get("room", {}).get("typeEstimated", {}).get("beds", 1),
        }
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def build_itinerary_options(
    flight_offers: list[dict],
    hotel_offers: list[dict],
    budget_total: Optional[float] = None,
) -> list[dict]:
    """
    Build up to 3 itinerary packages from raw Amadeus results.

    Returns a list of option dicts, each with:
      label, description, flight, hotel, total_usd, within_budget
    """
    flights = [f for f in (_extract_flight(o) for o in flight_offers) if f]
    hotels = [h for h in (_extract_hotel(o) for o in hotel_offers) if h]

    if not flights or not hotels:
        return []

    flights.sort(key=lambda f: f["price_usd"])
    hotels.sort(key=lambda h: h["price_total_usd"])

    def _make_option(label: str, description: str, flight: dict, hotel: dict) -> dict:
        total = round(flight["price_usd"] + hotel["price_total_usd"], 2)
        return {
            "label": label,
            "description": description,
            "flight": flight,
            "hotel": hotel,
            "total_usd": total,
            "within_budget": budget_total is None or total <= budget_total,
        }

    options: list[dict] = []

    # Option 1 — Budget: cheapest flight + cheapest hotel
    options.append(_make_option("Budget", "Lowest cost combination", flights[0], hotels[0]))

    # Option 2 — Best Value: mid-range flight + mid-range hotel (needs ≥2 of each)
    if len(flights) >= 2 and len(hotels) >= 2:
        mid_f = flights[len(flights) // 2]
        mid_h = hotels[len(hotels) // 2]
        if mid_f != flights[0] or mid_h != hotels[0]:
            options.append(_make_option("Best Value", "Balanced price and quality", mid_f, mid_h))

    # Option 3 — Premium: direct/fastest flight + best hotel
    direct = [f for f in flights if f["outbound_stops"] == 0]
    best_flight = direct[0] if direct else flights[-1]
    best_hotel = hotels[-1]
    premium_option = _make_option("Premium", "Best flight and hotel combination", best_flight, best_hotel)
    # Only add if it differs from options already present
    if not any(
        o["flight"]["id"] == premium_option["flight"]["id"]
        and o["hotel"]["hotel_id"] == premium_option["hotel"]["hotel_id"]
        for o in options
    ):
        options.append(premium_option)

    return options[:3]
