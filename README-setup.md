# Developer Setup Guide

## What's been built

### Week 1–2 — Auth + traveler profile

- **Google OAuth 2.0** via NextAuth 5 (server-side session, JWT strategy)
- **Protected routes** — `/dashboard` and `/profile` redirect to `/` when unauthenticated
- **Traveler profile** — users store passport number, TSA Known Traveler number, seat and meal preferences, and loyalty program numbers once; the agent reuses this on every booking
- **Application-layer encryption** — passport and TSA numbers are encrypted with Fernet before being written to the database; raw values are never stored in plaintext
- **Internal API key** — all Next.js → FastAPI calls require a shared secret in the `x-api-key` header; FastAPI is never exposed directly to the browser

### Week 3–4 — Search layer

- **Natural-language trip spec parser** — uses the Claude API to turn a plain-English request ("fly me to Tokyo in October, 10 days, under $3,000") into a structured spec (`origin`, `destination`, `depart_date`, `return_date`, `budget_total`, etc.). Falls back to a built-in rule-based parser when no Anthropic key is set.
- **Amadeus flight search** — queries the Amadeus v2 Flight Offers Search API for real flight options. Falls back to realistic mock data when no Amadeus credentials are set.
- **Amadeus hotel search** — queries the Amadeus v3 Hotel Offers API. Same mock fallback applies.
- **Itinerary builder** — packages search results into 3 curated options: Budget, Best Value, and Premium, each with a total cost breakdown.
- **Trip approval** — user picks one option; it's persisted as `approved_itinerary` on the trip. Actual booking execution is Week 5–7.
- **Dashboard** — replaces the placeholder with a live trip request form and a list of past trips with status badges.
- **`/trips/[id]` page** — shows the 3 itinerary option cards with flight and hotel details. "Choose this trip" locks in the selection.
- **`trips` and `bookings` tables** — added via Alembic migration 002. `bookings` is empty for now but will be populated in Week 5.

---

## Prerequisites

- Node.js 20+
- Python 3.12 (required — `psycopg2-binary` wheels are not available for 3.14+)
- Docker Desktop (must be running before any `docker` commands)

---

## 1. Start the database

From the project root:

```bash
docker compose up -d
```

If that fails with "unknown shorthand flag", use the v1 CLI:

```bash
docker-compose up -d
```

PostgreSQL is now running on `localhost:5432`.
pgAdmin is available at `http://localhost:5050` (admin@admin.com / admin).

---

## 2. Backend

### 2a. Install dependencies

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2b. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | How to get it | Required? |
|---|---|---|
| `DATABASE_URL` | Pre-filled for local Docker | Yes |
| `INTERNAL_API_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` — must match frontend | Yes |
| `ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | Yes |
| `AMADEUS_CLIENT_ID` | Free sandbox at [developers.amadeus.com](https://developers.amadeus.com) — register, create an app, copy the key | No — mock data used if empty |
| `AMADEUS_CLIENT_SECRET` | Same as above | No — mock data used if empty |
| `AMADEUS_ENV` | `test` for sandbox (default), `production` for live | No |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | No — rule-based parser used if empty |

**Getting Amadeus sandbox credentials (manual step):**
1. Go to [developers.amadeus.com](https://developers.amadeus.com) and sign up
2. Create a new app (Self-Service)
3. Copy the **API Key** (`AMADEUS_CLIENT_ID`) and **API Secret** (`AMADEUS_CLIENT_SECRET`)
4. Leave `AMADEUS_ENV=test` — the sandbox is free and covers all development

**Getting an Anthropic API key (manual step):**
1. Go to [console.anthropic.com](https://console.anthropic.com) and sign in
2. Navigate to **API Keys** → **Create Key**
3. Copy the key into `ANTHROPIC_API_KEY`
4. If left empty the built-in rule-based parser handles basic requests like "fly me to Tokyo in October, 10 days, under $3,000"

### 2c. Run migrations

**First time (Week 1–2 only):**
```bash
alembic upgrade head
```

**Upgrading from Week 1–2 to Week 3–4** (adds `trips` and `bookings` tables):
```bash
alembic upgrade head
```

> `alembic upgrade head` is idempotent — it only runs migrations that haven't been applied yet. Run it whenever you pull new code.

### 2d. Start the API server

```bash
uvicorn app.main:app --reload
```

**Troubleshooting:**
If `pip install` fails on `psycopg2-binary` with "pg_config executable not found", you are likely using Python 3.14. Install Python 3.12 (`brew install python@3.12` on macOS, or download from python.org) and recreate the venv with `python3.12 -m venv .venv`.

---

## 3. Frontend

### 3a. Install dependencies

```bash
cd frontend
npm install
```

### 3b. Configure environment

```bash
cp env.local.example .env.local
```

Edit `.env.local`:

| Variable | Where to get it | Who sets it |
|---|---|---|
| `AUTH_SECRET` | `openssl rand -base64 32` | Each developer generates their own |
| `AUTH_URL` | `http://localhost:3000` | Same for everyone locally |
| `GOOGLE_CLIENT_ID` | Google Cloud Console (see below) | Shared dev client or individual |
| `GOOGLE_CLIENT_SECRET` | Same as above | Same as above |
| `INTERNAL_API_KEY` | Same value as in `backend/.env` | Must match backend |
| `BACKEND_URL` | `http://localhost:8000` | Same for everyone locally |

**Google OAuth setup (manual step):**
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → **APIs & Services** → **Credentials** → **Create OAuth 2.0 Client ID**
3. Application type: **Web application**
4. Authorized redirect URI: `http://localhost:3000/api/auth/callback/google`
5. Copy Client ID and Secret into `.env.local`

### 3c. Start the dev server

```bash
npm run dev
```

---

## What's running

| Service | URL |
|---|---|
| Next.js frontend | http://localhost:3000 |
| FastAPI backend | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| pgAdmin | http://localhost:5050 |

---

## How the trip search flow works

1. User types a request on `/dashboard` — e.g. _"Fly me to Tokyo in October, 10 days, under $3,000, hotel near Shinjuku"_
2. Next.js POSTs to `/api/trips` → backend parses the spec (Claude API or rule-based fallback)
3. Backend searches Amadeus for flights and hotels (or returns mock data if no credentials)
4. Itinerary builder packages the results into up to 3 options (Budget / Best Value / Premium)
5. User is redirected to `/trips/[id]` where they can compare options and click **Choose this trip**
6. Choosing an option sets `status = approved` — actual booking execution is Week 5–7

> **No API keys? No problem.** The backend includes realistic mock flight and hotel data. The full frontend flow — request → parse → itinerary cards → approve — works end-to-end without Amadeus or Anthropic credentials.

---

## New API endpoints (Week 3–4)

| Method | Path | Description |
|---|---|---|
| `POST` | `/trips` | Parse request, search, return itinerary options |
| `GET` | `/trips` | List all trips for the current user |
| `GET` | `/trips/{id}` | Get a single trip with options |
| `POST` | `/trips/{id}/approve` | Approve an itinerary option (`option_index: 0/1/2`) |

All endpoints require the same `x-api-key` and `x-user-email` headers as the profile endpoints.
Full interactive docs at **http://localhost:8000/docs**.

---

## Project structure (Week 3–4 additions highlighted)

```
backend/
  app/
    routers/
      profile.py
      trips.py          ← NEW: search + approval endpoints
    services/           ← NEW directory
      amadeus.py        ← NEW: Amadeus API client + mock fallback
      trip_parser.py    ← NEW: Claude / rule-based spec parser
      itinerary.py      ← NEW: itinerary option builder
    main.py             ← updated: registers trips router
    models.py           ← updated: adds Trip + Booking models
    config.py           ← updated: adds Amadeus + Anthropic settings
  alembic/
    versions/
      001_create_users_table.py
      002_create_trips_and_bookings.py   ← NEW migration
  requirements.txt      ← updated: adds httpx, anthropic
  .env.example          ← updated: adds new env vars

frontend/
  app/
    api/
      trips/
        route.ts              ← NEW: list + create trips
        [id]/
          route.ts            ← NEW: get trip
          approve/
            route.ts          ← NEW: approve itinerary
    dashboard/page.tsx        ← updated: live trip form + trips list
    trips/
      [id]/page.tsx           ← NEW: itinerary options view
  components/
    TripRequestForm.tsx       ← NEW: natural-language input
    ItineraryCard.tsx         ← NEW: option display card
```
