# Travel Planner — Setup and Deployment Guide

This guide covers everything needed to get the application running locally and in production from scratch, including all required credentials, hosting configuration, and end-to-end testing steps.

---

## Table of Contents

1. [What the application does](#what-the-application-does)
2. [Required API keys and services](#required-api-keys-and-services)
3. [Local development setup](#local-development-setup)
4. [Running the full stack locally](#running-the-full-stack-locally)
5. [End-to-end testing checklist](#end-to-end-testing-checklist)
6. [Production hosting (Vercel + EC2)](#production-hosting-vercel--ec2)
7. [Troubleshooting](#troubleshooting)

---

## What the application does

A user types a plain-English trip request. The AI agent parses the request, searches for flights and hotels, presents 2–3 itinerary options, and — after user approval — navigates to airline and hotel websites with a browser automation agent to complete the actual bookings on the user's behalf. The user's saved traveler profile (passport, TSA number, loyalty numbers, seat preferences) is used on every form. A single-use virtual payment card is generated per booking so no real card number is stored on any airline or hotel site.

After booking, the system emails a consolidated confirmation and monitors confirmed trips hourly for schedule changes and price drops.

**What works without any API keys (mock mode):**
The entire pipeline — request → parse → options → approve → book → live status → confirmation email log — works with zero third-party credentials. All services have mock fallbacks. This is the easiest way to verify the app is set up correctly.

---

## Required API keys and services

### Always required (no mock alternative)

| Variable | Purpose | Where to get it |
|---|---|---|
| `INTERNAL_API_KEY` | Shared secret between Next.js and FastAPI | Generate locally (see below) |
| `ENCRYPTION_KEY` | Fernet key for encrypting passport/TSA numbers at rest | Generate locally (see below) |
| `AUTH_SECRET` | NextAuth session signing key | Generate locally (see below) |
| `GOOGLE_CLIENT_ID` | Google OAuth — user sign-in | Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Google OAuth — user sign-in | Google Cloud Console |
| `DATABASE_URL` | PostgreSQL connection string | Local Docker or managed DB |

### Optional (mock fallbacks exist)

| Variable | Purpose | Required for |
|---|---|---|
| `AMADEUS_CLIENT_ID` | Real flight and hotel search data | Live search results |
| `AMADEUS_CLIENT_SECRET` | Same | Same |
| `ANTHROPIC_API_KEY` | Claude Sonnet — trip parser, booking vision agent | AI-powered parsing; live booking |
| `STRIPE_SECRET_KEY` | Stripe Issuing — single-use virtual cards per booking | Live payment card creation |
| `BROWSERLESS_URL` | Scalable headless Chrome | Production live booking (optional even in live mode) |
| `SENDGRID_API_KEY` | Transactional email for confirmations and alerts | Sending real emails |
| `SENDGRID_FROM_EMAIL` | Sender address for emails | Sending real emails |

---

## Local development setup

### Prerequisites

- **Python 3.12** — required (psycopg2-binary wheels are not available on 3.14+)
- **Node.js 20+**
- **Docker Desktop** — must be running before any `docker` commands

Verify your Python version:
```bash
python3.12 --version   # must be 3.12.x
```

---

### Step 1: Clone the repository

```bash
git clone https://github.com/willkerr1300/travel-planner.git
cd travel-planner
```

---

### Step 2: Start infrastructure (PostgreSQL + Redis)

```bash
docker compose up -d
```

If that fails with "unknown shorthand flag":
```bash
docker-compose up -d
```

This starts three containers:

| Service | Address | Credentials |
|---|---|---|
| PostgreSQL 16 | `localhost:5432` | travelplanner / travelplanner |
| pgAdmin 4 | `http://localhost:5050` | admin@admin.com / admin |
| Redis 7 | `localhost:6379` | no auth required |

Verify containers are running:
```bash
docker compose ps
```
All three services should show `running`.

---

### Step 3: Backend setup

#### 3a. Create a virtual environment and install dependencies

```bash
cd backend
python3.12 -m venv .venv

# macOS / Linux:
source .venv/bin/activate

# Windows:
.venv\Scripts\activate

pip install -r requirements.txt
```

#### 3b. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

**Generate the required keys:**
```bash
# INTERNAL_API_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the output of each command into the corresponding variable in `.env`. The `DATABASE_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` values are pre-filled for local Docker and do not need to change.

**Minimum working `.env` for mock mode (no external APIs required):**
```
DATABASE_URL=postgresql://travelplanner:travelplanner@localhost:5432/travelplanner
INTERNAL_API_KEY=<your generated key>
ENCRYPTION_KEY=<your generated fernet key>
BOOKING_MOCK_MODE=true
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

Everything else can remain blank — mock fallbacks will handle it.

#### 3c. Run database migrations

```bash
alembic upgrade head
```

This creates all four tables: `users`, `trips`, `bookings`, `agent_logs`, `trip_alerts`.

Output should end with:
```
INFO  [alembic.runtime.migration] Running upgrade 003 -> 004, add trip_alerts table...
INFO  [alembic.runtime.migration] Running upgrade -> 004
```

> Run `alembic upgrade head` any time you pull new code — it is safe to run repeatedly and only applies unapplied migrations.

#### 3d. (Live mode only) Install Playwright browser binaries

Only needed when `BOOKING_MOCK_MODE=false`:
```bash
playwright install chromium
```

Skip this in mock mode.

---

### Step 4: Google OAuth setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create or select a project
3. Navigate to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
4. Application type: **Web application**
5. Name: anything (e.g. "Travel Planner Dev")
6. **Authorized redirect URIs** — add:
   - `http://localhost:3000/api/auth/callback/google` (local dev)
   - `https://your-production-domain.vercel.app/api/auth/callback/google` (production, add later)
7. Click **Create** and copy the **Client ID** and **Client Secret**

---

### Step 5: Frontend setup

```bash
cd ../frontend
npm install
cp env.local.example .env.local
```

Open `.env.local` and fill in:

```
AUTH_SECRET=<openssl rand -base64 32>
AUTH_URL=http://localhost:3000
GOOGLE_CLIENT_ID=<from Google Cloud Console>
GOOGLE_CLIENT_SECRET=<from Google Cloud Console>
INTERNAL_API_KEY=<same value as in backend/.env>
BACKEND_URL=http://localhost:8000
```

Generate `AUTH_SECRET`:
```bash
# macOS / Linux:
openssl rand -base64 32

# Windows (PowerShell):
[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }) -as [byte[]])
```

---

## Running the full stack locally

You need four processes running simultaneously. Use four terminal tabs or a terminal multiplexer.

**Terminal 1 — Backend API server:**
```bash
cd backend
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
uvicorn app.main:app --reload
```
API server runs at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

**Terminal 2 — Celery worker (booking queue):**
```bash
cd backend
source .venv/bin/activate
celery -A app.worker worker --loglevel=info
```
The worker must be running for bookings to execute. Without it, clicking "Book this trip" will enqueue a task that never runs.

**Terminal 3 — Celery beat (trip monitoring — optional for development):**
```bash
cd backend
source .venv/bin/activate
celery -A app.worker beat --loglevel=info
```
Beat triggers the hourly monitoring scan. Skip this in development unless you are testing the alert pipeline.

**Terminal 4 — Frontend:**
```bash
cd frontend
npm run dev
```
Frontend runs at `http://localhost:3000`.

---

## End-to-end testing checklist

Work through these steps in order to verify the full pipeline. All steps work in mock mode with no external API credentials.

### Authentication
- [ ] Open `http://localhost:3000`
- [ ] Click "Sign in with Google" — you should be redirected to Google and then back to the dashboard
- [ ] Confirm your email appears in the top-right nav

### Profile setup (required for booking)
- [ ] Navigate to `/profile`
- [ ] Fill in **First name** and **Last name** (required for passenger forms)
- [ ] Optionally add passport number, TSA number, seat preference, and a loyalty number
- [ ] Click Save — no error should appear

### Trip creation
- [ ] On the dashboard, type a trip request:
  `"Fly me to Tokyo in June for 10 days, budget $3000, hotel near Shinjuku"`
- [ ] Submit — you should be redirected to `/trips/[id]`
- [ ] Verify the page shows 3 itinerary options: Budget, Best Value, Premium
- [ ] Each card should show: flight route, departure time, carrier, cabin class, price; hotel name, stars, check-in/out, room type, price; total cost

### Approval
- [ ] Click **Choose this trip** on any option
- [ ] The button should change to "Selected" and the booking panel should appear

### Booking execution (mock mode)
- [ ] Click **Book this trip**
- [ ] The panel should immediately show "Booking in progress…" with a spinner
- [ ] Within ~30 seconds, individual booking rows (Flight, Hotel) should appear
- [ ] Each row should show a timeline of agent steps (navigate, fill passenger info, select seat, payment, confirm)
- [ ] Final state: green "Confirmed" badge and a 6-character confirmation number for each booking

### Confirmation endpoint
- [ ] Once the trip is confirmed, visit `http://localhost:8000/docs`
- [ ] Try `GET /trips/{trip_id}/confirmation` — you should get a structured JSON response with all booking details

### Trip alerts (monitoring)
- [ ] Alerts appear automatically when the monitor scan runs (hourly in production)
- [ ] To trigger manually in development:
  ```bash
  cd backend
  source .venv/bin/activate
  python -c "
  import asyncio
  from app.tasks.monitor_tasks import _async_scan_confirmed_trips
  asyncio.run(_async_scan_confirmed_trips())
  "
  ```
- [ ] Reload `/trips/[id]` — any detected schedule changes or price drops should appear as amber/green banners

### Trip modification
- [ ] On a confirmed trip's page, click **Modify this trip** to expand the panel
- [ ] Try: `"Extend my hotel by 2 nights"`
- [ ] You should see a green success message and the hotel check-out date should update

---

## Optional API integrations

### Amadeus (real flight/hotel search)

1. Sign up at [developers.amadeus.com](https://developers.amadeus.com) — free for sandbox
2. Create a **Self-Service** app
3. Copy **API Key** → `AMADEUS_CLIENT_ID`, **API Secret** → `AMADEUS_CLIENT_SECRET`
4. Leave `AMADEUS_ENV=test` for sandbox (covers all development)
5. Restart the backend — real flight data will now appear instead of mock data

### Anthropic (Claude trip parser + vision booking agent)

1. Sign in at [console.anthropic.com](https://console.anthropic.com)
2. **API Keys → Create Key**
3. Copy into `ANTHROPIC_API_KEY`
4. Restart the backend

With this set:
- Trip requests are parsed by Claude Sonnet 4.6 (instead of the rule-based fallback)
- Live booking mode uses Claude's vision API to read booking site screenshots

### Stripe Issuing (real virtual cards)

1. Sign in at [dashboard.stripe.com](https://dashboard.stripe.com)
2. Apply for **Issuing** access in the dashboard (US entities only; typically approved in 1–3 days)
3. **Developers → API Keys** → copy the **Secret key** into `STRIPE_SECRET_KEY`
4. For test mode, use `sk_test_...` keys
5. Note: Issuing requires a separate restricted key with `issuing_card_number:read` for reading raw card numbers server-side

Without Stripe configured, a mock Visa number (`4111111111111111`) is used as the virtual card.

### SendGrid (email confirmations and alerts)

1. Sign up at [sendgrid.com](https://sendgrid.com)
2. **Settings → API Keys → Create API Key** with **Mail Send** permission
3. Copy into `SENDGRID_API_KEY`
4. Set `SENDGRID_FROM_EMAIL` to an email you've verified in SendGrid (under **Sender Authentication**)

Without SendGrid configured, emails are silently skipped — booking still completes normally.

### Live booking mode

To enable real browser automation against live airline/hotel sites:

1. Set `BOOKING_MOCK_MODE=false` in `backend/.env`
2. Ensure `ANTHROPIC_API_KEY` is set (Claude vision required)
3. Run `playwright install chromium`
4. Optionally set `BROWSERLESS_URL` for a cloud headless browser (recommended for production)

**Supported sites in live mode:**
- Flights: United (`UA`), Delta (`DL`), American (`AA`), Southwest (`WN`)
- Hotels: Expedia (default), Marriott.com (only for Marriott-branded hotels when user has a Marriott loyalty number)
- Activities: not supported in live mode (simulated with confirmation number; a "not supported" badge appears)

> Live mode attempts real bookings. Use only with test/sandbox payment methods or on trips you actually intend to book.

---

## Production hosting (Vercel + EC2)

### Architecture in production

```
Browser → Vercel (Next.js) → EC2 (FastAPI + Celery + Redis + PostgreSQL)
                                         ↓
                                   Playwright / Browserless.io
```

The frontend runs on Vercel's edge network. The backend needs persistent compute for long-running booking sessions — EC2 is suitable.

---

### Frontend: Vercel

1. Push the repository to GitHub (already done)
2. Go to [vercel.com](https://vercel.com) → **Add New Project** → import from GitHub
3. Set **Root Directory** to `frontend`
4. Framework preset: **Next.js** (auto-detected)
5. Add environment variables in the Vercel dashboard (**Settings → Environment Variables**):

| Variable | Value |
|---|---|
| `AUTH_SECRET` | Same value as local (or regenerate) |
| `AUTH_URL` | `https://your-project.vercel.app` |
| `GOOGLE_CLIENT_ID` | Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console |
| `INTERNAL_API_KEY` | Same as backend |
| `BACKEND_URL` | `http://your-ec2-ip:8000` (or your EC2 domain) |

6. Deploy. Vercel automatically deploys on every push to `main`.
7. Add the Vercel URL to Google Cloud Console's **Authorized redirect URIs**:
   `https://your-project.vercel.app/api/auth/callback/google`

---

### Backend: EC2

**Recommended instance:** `t3.medium` (2 vCPU, 4GB RAM) for development/testing; `t3.large` for production with live booking mode.

#### Server setup (Ubuntu 22.04 LTS)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.12
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# Install Docker (for PostgreSQL + Redis)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu

# Log out and back in for Docker group to take effect

# Install build tools (for psycopg2-binary)
sudo apt install -y build-essential libpq-dev
```

#### Clone and configure

```bash
git clone https://github.com/willkerr1300/travel-planner.git
cd travel-planner

# Start PostgreSQL + Redis
docker compose up -d

# Backend virtualenv
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# If using live booking mode:
playwright install chromium
playwright install-deps chromium

# Configure environment
cp .env.example .env
nano .env   # fill in all values, BOOKING_MOCK_MODE=false for live
```

Set `DATABASE_URL` in `.env` to the Docker container's database:
```
DATABASE_URL=postgresql://travelplanner:travelplanner@localhost:5432/travelplanner
```

#### Run migrations

```bash
alembic upgrade head
```

#### Run services with systemd

Create `/etc/systemd/system/travelplanner-api.service`:
```ini
[Unit]
Description=Travel Planner FastAPI
After=network.target docker.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/travel-planner/backend
ExecStart=/home/ubuntu/travel-planner/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
EnvironmentFile=/home/ubuntu/travel-planner/backend/.env

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/travelplanner-worker.service`:
```ini
[Unit]
Description=Travel Planner Celery Worker
After=network.target docker.service travelplanner-api.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/travel-planner/backend
ExecStart=/home/ubuntu/travel-planner/backend/.venv/bin/celery -A app.worker worker --loglevel=info
Restart=always
EnvironmentFile=/home/ubuntu/travel-planner/backend/.env

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/travelplanner-beat.service`:
```ini
[Unit]
Description=Travel Planner Celery Beat (trip monitoring)
After=network.target docker.service travelplanner-worker.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/travel-planner/backend
ExecStart=/home/ubuntu/travel-planner/backend/.venv/bin/celery -A app.worker beat --loglevel=info
Restart=always
EnvironmentFile=/home/ubuntu/travel-planner/backend/.env

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable travelplanner-api travelplanner-worker travelplanner-beat
sudo systemctl start travelplanner-api travelplanner-worker travelplanner-beat

# Verify
sudo systemctl status travelplanner-api
```

#### EC2 security group rules

In the AWS console, add these inbound rules to the EC2 instance's security group:

| Port | Protocol | Source | Purpose |
|---|---|---|---|
| 22 | TCP | Your IP | SSH |
| 8000 | TCP | Vercel IP ranges or `0.0.0.0/0` | FastAPI (frontend → backend) |

> Port 8000 does not need to be open to the public internet if you put a reverse proxy (nginx) in front. Restrict it to Vercel's egress IPs for tighter security.

#### Optional: nginx reverse proxy with HTTPS

```bash
sudo apt install -y nginx certbot python3-certbot-nginx

# Set up a domain (e.g. api.travelplanner.example.com pointing to your EC2 IP)
sudo nano /etc/nginx/sites-available/travelplanner
```

```nginx
server {
    listen 80;
    server_name api.travelplanner.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/travelplanner /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Issue TLS certificate
sudo certbot --nginx -d api.travelplanner.example.com
```

Then set `BACKEND_URL=https://api.travelplanner.example.com` in Vercel.

---

## Troubleshooting

**Booking gets stuck in "in progress" forever**
- Celery worker is not running. Start it: `celery -A app.worker worker --loglevel=info`
- Worker can't connect to Redis. Verify Docker: `docker compose ps` → redis should be running

**"Please add your first and last name" error when booking**
- Go to `/profile` and fill in first name and last name. These are required for passenger forms.

**Login redirects to / instead of /dashboard**
- Check `AUTH_URL` in `frontend/.env.local` — must match the URL you're accessing the app on (including port for local dev)
- Verify the redirect URI in Google Cloud Console exactly matches

**`alembic upgrade head` fails with "relation already exists"**
- The database may have tables from a previous install. Either drop the DB and recreate it, or check `alembic current` to see which migrations have been applied

**`psycopg2-binary` installation fails**
- You are likely running Python 3.13 or 3.14. Install Python 3.12 specifically:
  `python3.12 -m venv .venv`

**Playwright browsers fail to install on Linux**
- Install system dependencies: `playwright install-deps chromium`
- Behind a corporate proxy: `PLAYWRIGHT_DOWNLOAD_HOST=https://playwright.azureedge.net playwright install chromium`

**Trip alerts not appearing**
- Alerts are generated by the hourly Celery beat task. Trigger manually for testing:
  ```bash
  python -c "import asyncio; from app.tasks.monitor_tasks import _async_scan_confirmed_trips; asyncio.run(_async_scan_confirmed_trips())"
  ```

**API returns 401 Unauthorized**
- The `INTERNAL_API_KEY` in `frontend/.env.local` must exactly match the one in `backend/.env`

---

## All services running — quick reference

| Service | Command | URL |
|---|---|---|
| Docker (DB + Redis) | `docker compose up -d` | postgres:5432, redis:6379 |
| FastAPI backend | `uvicorn app.main:app --reload` | http://localhost:8000 |
| API docs | (auto, from FastAPI) | http://localhost:8000/docs |
| Celery worker | `celery -A app.worker worker` | (background process) |
| Celery beat | `celery -A app.worker beat` | (background process) |
| Next.js frontend | `npm run dev` | http://localhost:3000 |
| pgAdmin | (via Docker) | http://localhost:5050 |
