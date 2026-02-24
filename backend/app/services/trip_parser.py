"""
Trip spec parser — turns a plain-English trip request into a structured dict.

Primary: uses the Claude API (claude-sonnet-4-6) when ANTHROPIC_API_KEY is set.
Fallback: a lightweight rule-based parser so developers can run without an API key.
"""

import json
import re
from datetime import date, timedelta
from typing import Optional

from app.config import settings

# ---------------------------------------------------------------------------
# Claude-based parser
# ---------------------------------------------------------------------------

_PARSE_PROMPT = """\
You are a travel booking assistant. Parse the user's trip request into a JSON object.

Extract these fields:
- origin: IATA airport code (3 letters, e.g. "JFK"). Infer from city names. null if not mentioned.
- destination: IATA airport code (3 letters). Required.
- destination_city: full city name, e.g. "Tokyo"
- depart_date: ISO date YYYY-MM-DD. If only a month is given, use the first Friday of that month in the next 12 months from today.
- return_date: ISO date YYYY-MM-DD. Calculate from depart_date + duration if given. null for one-way.
- budget_total: integer USD. null if not specified.
- num_travelers: integer. Default 1.
- cabin_class: "ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", or "FIRST". Default "ECONOMY".
- hotel_area: preferred neighborhood or area for the hotel, or null.
- notes: any other constraints as a short string, or null.

Today is {today}. Return ONLY the raw JSON object, no markdown fences, no explanation.

User request: {request}"""


async def _parse_with_claude(raw_request: str) -> dict:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    today = date.today().isoformat()
    prompt = _PARSE_PROMPT.format(today=today, request=raw_request)

    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    # Strip markdown code fences if the model wraps the JSON anyway
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Rule-based fallback parser
# ---------------------------------------------------------------------------

# Common city → IATA airport code mappings
_CITY_TO_IATA: dict[str, str] = {
    "new york": "JFK", "nyc": "JFK", "jfk": "JFK",
    "los angeles": "LAX", "la": "LAX", "lax": "LAX",
    "chicago": "ORD", "ord": "ORD",
    "san francisco": "SFO", "sf": "SFO", "sfo": "SFO",
    "miami": "MIA", "mia": "MIA",
    "dallas": "DFW", "dfw": "DFW",
    "seattle": "SEA", "sea": "SEA",
    "boston": "BOS", "bos": "BOS",
    "london": "LHR", "lhr": "LHR",
    "paris": "CDG", "cdg": "CDG",
    "tokyo": "TYO", "tyo": "TYO",
    "osaka": "KIX", "kix": "KIX",
    "rome": "FCO", "fco": "FCO",
    "barcelona": "BCN", "bcn": "BCN",
    "madrid": "MAD", "mad": "MAD",
    "amsterdam": "AMS", "ams": "AMS",
    "bangkok": "BKK", "bkk": "BKK",
    "sydney": "SYD", "syd": "SYD",
    "dubai": "DXB", "dxb": "DXB",
    "singapore": "SIN", "sin": "SIN",
    "hong kong": "HKG", "hkg": "HKG",
    "seoul": "ICN", "icn": "ICN",
    "mexico city": "MEX", "mex": "MEX",
    "toronto": "YYZ", "yyz": "YYZ",
    "vancouver": "YVR", "yvr": "YVR",
    "cancun": "CUN", "cun": "CUN",
    "bali": "DPS", "dps": "DPS",
    "berlin": "BER", "ber": "BER",
    "munich": "MUC", "muc": "MUC",
    "zurich": "ZRH", "zrh": "ZRH",
    "vienna": "VIE", "vie": "VIE",
    "istanbul": "IST", "ist": "IST",
    "cairo": "CAI", "cai": "CAI",
    "cape town": "CPT", "cpt": "CPT",
}

_MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def _first_friday_of_month(year: int, month: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != 4:  # 4 = Friday
        d += timedelta(days=1)
    return d


def _parse_with_rules(raw_request: str) -> dict:
    text = raw_request.lower()
    today = date.today()

    # --- destination ---
    destination: Optional[str] = None
    destination_city: Optional[str] = None
    for city, code in _CITY_TO_IATA.items():
        if city in text:
            destination = code
            destination_city = city.title()
            break

    # --- origin --- (look for "from X")
    origin: Optional[str] = None
    from_match = re.search(r"\bfrom\s+([a-z ]+?)(?:\s+to|\s+in|\s+for|,|$)", text)
    if from_match:
        from_city = from_match.group(1).strip()
        origin = _CITY_TO_IATA.get(from_city)

    # --- month ---
    depart_date: Optional[str] = None
    return_date: Optional[str] = None
    for month_name, month_num in _MONTH_NAMES.items():
        if month_name in text:
            year = today.year
            # If that month has already passed this year, use next year
            if month_num < today.month or (month_num == today.month and today.day > 15):
                year += 1
            depart_date = _first_friday_of_month(year, month_num).isoformat()
            break

    # --- explicit date like "October 15" or "Oct 15" ---
    date_match = re.search(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b", text
    )
    if date_match:
        month_num = _MONTH_NAMES.get(date_match.group(1))
        day = int(date_match.group(2))
        if month_num:
            year = today.year
            candidate = date(year, month_num, day)
            if candidate < today:
                candidate = date(year + 1, month_num, day)
            depart_date = candidate.isoformat()

    # --- duration (e.g. "10 days", "2 weeks") ---
    duration_days: Optional[int] = None
    days_match = re.search(r"(\d+)\s+days?", text)
    weeks_match = re.search(r"(\d+)\s+weeks?", text)
    if days_match:
        duration_days = int(days_match.group(1))
    elif weeks_match:
        duration_days = int(weeks_match.group(1)) * 7

    if depart_date and duration_days:
        dep = date.fromisoformat(depart_date)
        return_date = (dep + timedelta(days=duration_days)).isoformat()

    # --- budget (e.g. "under $3,000", "$2500", "3000") ---
    budget_total: Optional[int] = None
    budget_match = re.search(r"\$[\s]?([\d,]+)", text)
    if budget_match:
        budget_total = int(budget_match.group(1).replace(",", ""))
    else:
        under_match = re.search(r"under\s+([\d,]+)", text)
        if under_match:
            budget_total = int(under_match.group(1).replace(",", ""))

    # --- travelers ---
    num_travelers = 1
    travelers_match = re.search(r"(\d+)\s+(?:people|travelers?|passengers?|adults?)", text)
    if travelers_match:
        num_travelers = int(travelers_match.group(1))

    # --- cabin class ---
    cabin_class = "ECONOMY"
    if "business class" in text or "business seat" in text:
        cabin_class = "BUSINESS"
    elif "first class" in text:
        cabin_class = "FIRST"
    elif "premium economy" in text:
        cabin_class = "PREMIUM_ECONOMY"

    # --- hotel area (look for "near X" or "in X area") ---
    hotel_area: Optional[str] = None
    area_match = re.search(r"\bnear\s+([a-z ]+?)(?:\s*,|\s*\.|\s+and|\s+under|\s+budget|$)", text)
    if area_match:
        hotel_area = area_match.group(1).strip().title()

    return {
        "origin": origin,
        "destination": destination,
        "destination_city": destination_city,
        "depart_date": depart_date,
        "return_date": return_date,
        "budget_total": budget_total,
        "num_travelers": num_travelers,
        "cabin_class": cabin_class,
        "hotel_area": hotel_area,
        "notes": None,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def parse_trip_request(raw_request: str) -> dict:
    """Parse a plain-English trip request into a structured spec dict."""
    if settings.anthropic_api_key:
        return await _parse_with_claude(raw_request)
    return _parse_with_rules(raw_request)
