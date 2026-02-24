"""
Amadeus API client for flight and hotel search.

When AMADEUS_CLIENT_ID is not set, all search functions return realistic mock
data so developers can work on the full UI flow without needing API credentials.
"""

import time
from typing import Optional

import httpx

from app.config import settings

_AMADEUS_HOSTS = {
    "test": "https://test.api.amadeus.com",
    "production": "https://api.amadeus.com",
}

_token: Optional[str] = None
_token_expires_at: float = 0.0


async def _get_token() -> str:
    global _token, _token_expires_at
    if _token and time.time() < _token_expires_at - 60:
        return _token

    base = _AMADEUS_HOSTS.get(settings.amadeus_env, _AMADEUS_HOSTS["test"])
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.amadeus_client_id,
                "client_secret": settings.amadeus_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _token = data["access_token"]
        _token_expires_at = time.time() + data["expires_in"]
        return _token


# ---------------------------------------------------------------------------
# Mock data — returned when AMADEUS_CLIENT_ID is not configured
# ---------------------------------------------------------------------------

def _mock_flights(origin: str, destination: str, depart_date: str, return_date: Optional[str]) -> list[dict]:
    """Return a set of mock Amadeus-shaped flight offer objects."""
    return [
        {
            "id": "1",
            "itineraries": [
                {
                    "duration": "PT14H30M",
                    "segments": [
                        {
                            "departure": {"iataCode": origin, "at": f"{depart_date}T10:00:00"},
                            "arrival": {"iataCode": destination, "at": f"{depart_date}T14:30:00"},
                            "carrierCode": "UA",
                            "number": "837",
                            "duration": "PT14H30M",
                        }
                    ],
                },
                *(
                    [
                        {
                            "duration": "PT13H55M",
                            "segments": [
                                {
                                    "departure": {"iataCode": destination, "at": f"{return_date}T16:00:00"},
                                    "arrival": {"iataCode": origin, "at": f"{return_date}T11:55:00"},
                                    "carrierCode": "UA",
                                    "number": "838",
                                    "duration": "PT13H55M",
                                }
                            ],
                        }
                    ]
                    if return_date else []
                ),
            ],
            "price": {"grandTotal": "780.00", "currency": "USD"},
            "validatingAirlineCodes": ["UA"],
            "travelerPricings": [
                {"fareDetailsBySegment": [{"cabin": "ECONOMY"}]}
            ],
        },
        {
            "id": "2",
            "itineraries": [
                {
                    "duration": "PT15H20M",
                    "segments": [
                        {
                            "departure": {"iataCode": origin, "at": f"{depart_date}T13:00:00"},
                            "arrival": {"iataCode": "ORD", "at": f"{depart_date}T15:00:00"},
                            "carrierCode": "AA",
                            "number": "101",
                            "duration": "PT2H00M",
                        },
                        {
                            "departure": {"iataCode": "ORD", "at": f"{depart_date}T17:00:00"},
                            "arrival": {"iataCode": destination, "at": f"{depart_date}T20:20:00"},
                            "carrierCode": "AA",
                            "number": "169",
                            "duration": "PT13H20M",
                        },
                    ],
                },
                *(
                    [
                        {
                            "duration": "PT14H10M",
                            "segments": [
                                {
                                    "departure": {"iataCode": destination, "at": f"{return_date}T18:00:00"},
                                    "arrival": {"iataCode": origin, "at": f"{return_date}T18:10:00"},
                                    "carrierCode": "AA",
                                    "number": "170",
                                    "duration": "PT14H10M",
                                }
                            ],
                        }
                    ]
                    if return_date else []
                ),
            ],
            "price": {"grandTotal": "850.00", "currency": "USD"},
            "validatingAirlineCodes": ["AA"],
            "travelerPricings": [
                {"fareDetailsBySegment": [{"cabin": "ECONOMY"}]}
            ],
        },
        {
            "id": "3",
            "itineraries": [
                {
                    "duration": "PT13H50M",
                    "segments": [
                        {
                            "departure": {"iataCode": origin, "at": f"{depart_date}T17:00:00"},
                            "arrival": {"iataCode": destination, "at": f"{depart_date}T20:50:00"},
                            "carrierCode": "JL",
                            "number": "006",
                            "duration": "PT13H50M",
                        }
                    ],
                },
                *(
                    [
                        {
                            "duration": "PT14H00M",
                            "segments": [
                                {
                                    "departure": {"iataCode": destination, "at": f"{return_date}T11:30:00"},
                                    "arrival": {"iataCode": origin, "at": f"{return_date}T11:30:00"},
                                    "carrierCode": "JL",
                                    "number": "007",
                                    "duration": "PT14H00M",
                                }
                            ],
                        }
                    ]
                    if return_date else []
                ),
            ],
            "price": {"grandTotal": "1120.00", "currency": "USD"},
            "validatingAirlineCodes": ["JL"],
            "travelerPricings": [
                {"fareDetailsBySegment": [{"cabin": "ECONOMY"}]}
            ],
        },
    ]


def _mock_hotels(city_code: str, check_in: str, check_out: str) -> list[dict]:
    """Return mock Amadeus-shaped hotel offer objects."""
    return [
        {
            "hotel": {
                "hotelId": "MOCK001",
                "name": "Dormy Inn Shinjuku",
                "rating": "3",
                "cityCode": city_code,
            },
            "offers": [
                {
                    "checkInDate": check_in,
                    "checkOutDate": check_out,
                    "price": {"total": "620.00", "currency": "USD"},
                    "room": {"typeEstimated": {"category": "STANDARD_ROOM", "beds": 1}},
                }
            ],
        },
        {
            "hotel": {
                "hotelId": "MOCK002",
                "name": "Shinjuku Granbell Hotel",
                "rating": "4",
                "cityCode": city_code,
            },
            "offers": [
                {
                    "checkInDate": check_in,
                    "checkOutDate": check_out,
                    "price": {"total": "1050.00", "currency": "USD"},
                    "room": {"typeEstimated": {"category": "DELUXE_ROOM", "beds": 1}},
                }
            ],
        },
        {
            "hotel": {
                "hotelId": "MOCK003",
                "name": "Park Hyatt Tokyo",
                "rating": "5",
                "cityCode": city_code,
            },
            "offers": [
                {
                    "checkInDate": check_in,
                    "checkOutDate": check_out,
                    "price": {"total": "2850.00", "currency": "USD"},
                    "room": {"typeEstimated": {"category": "PARK_DELUXE_ROOM", "beds": 1}},
                }
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Public search functions
# ---------------------------------------------------------------------------

async def search_flights(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: Optional[str] = None,
    adults: int = 1,
    travel_class: str = "ECONOMY",
    max_results: int = 5,
) -> list[dict]:
    """Return Amadeus flight offer objects. Falls back to mock data if credentials are absent."""
    if not settings.amadeus_client_id:
        return _mock_flights(origin, destination, depart_date, return_date)

    token = await _get_token()
    base = _AMADEUS_HOSTS.get(settings.amadeus_env, _AMADEUS_HOSTS["test"])

    params: dict = {
        "originLocationCode": origin,
        "destinationLocationCode": destination,
        "departureDate": depart_date,
        "adults": adults,
        "travelClass": travel_class,
        "max": max_results,
        "currencyCode": "USD",
    }
    if return_date:
        params["returnDate"] = return_date

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{base}/v2/shopping/flight-offers",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])


async def search_hotels(
    city_code: str,
    check_in: str,
    check_out: str,
    adults: int = 1,
    max_results: int = 5,
) -> list[dict]:
    """Return Amadeus hotel offer objects. Falls back to mock data if credentials are absent."""
    if not settings.amadeus_client_id:
        return _mock_hotels(city_code, check_in, check_out)

    token = await _get_token()
    base = _AMADEUS_HOSTS.get(settings.amadeus_env, _AMADEUS_HOSTS["test"])

    async with httpx.AsyncClient() as client:
        # Step 1: get hotel IDs for the city
        hotels_resp = await client.get(
            f"{base}/v1/reference-data/locations/hotels/by-city",
            params={"cityCode": city_code, "radius": 10, "radiusUnit": "KM", "hotelSource": "ALL"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        hotels_resp.raise_for_status()
        hotels = hotels_resp.json().get("data", [])
        if not hotels:
            return []

        hotel_ids = [h["hotelId"] for h in hotels[:20]]

        # Step 2: fetch availability + pricing
        offers_resp = await client.get(
            f"{base}/v3/shopping/hotel-offers",
            params={
                "hotelIds": ",".join(hotel_ids),
                "checkInDate": check_in,
                "checkOutDate": check_out,
                "adults": adults,
                "currency": "USD",
                "bestRateOnly": "true",
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=25,
        )
        if offers_resp.status_code != 200:
            return []
        return offers_resp.json().get("data", [])[:max_results]
