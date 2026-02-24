# Setup — Week 1–2

## Prerequisites
- Node.js 20+
- Python 3.12+
- Docker Desktop

**Before starting:** Open Docker Desktop and wait until it is running (whale icon in the menu bar). Otherwise `docker` commands will fail.

---

## 1. Start the database

From the project root:

```bash
docker compose up -d
```

If that fails with "unknown shorthand flag" or "compose: command not found", try the standalone Compose (v1) instead:

```bash
docker-compose up -d
```

PostgreSQL is now running on `localhost:5432`.
pgAdmin is available at `http://localhost:5050` (admin@admin.com / admin).

---

## 2. Frontend

```bash
cd frontend
cp env.local.example .env.local
```

Edit `.env.local` and fill in:

| Variable | Where to get it | Who sets it |
|---|---|---|
| `AUTH_SECRET` | Run `openssl rand -base64 32` | **Each developer** — generate your own; keep it secret |
| `AUTH_URL` | `http://localhost:3000` (default) | Same for everyone when running locally — required for PKCE cookies |
| `GOOGLE_CLIENT_ID` | Google Cloud Console → APIs & Services → Credentials | **Shared or per-dev** — one team "local dev" OAuth client is fine (redirect is localhost); or create your own |
| `GOOGLE_CLIENT_SECRET` | Same as above | Same as above |
| `INTERNAL_API_KEY` | Long random string — must match backend `.env` | **Agree as a team** — use one shared dev value so frontend and backend match, or each dev generates one and sets it in both places |
| `BACKEND_URL` | `http://localhost:8000` (default) | Same for everyone when running locally |

**Google OAuth setup (manual step):**
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → APIs & Services → Credentials → Create OAuth 2.0 Client ID
3. Application type: **Web application**
4. Authorized redirect URI: `http://localhost:3000/api/auth/callback/google`
5. Copy the Client ID and Secret into `.env.local`

Then start the dev server:

```bash
npm install
npm run dev
```

---

## 3. Backend

Use **Python 3.12** (required for `psycopg2-binary` wheels). Python 3.14 is not yet supported by some dependencies.

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | How to generate | Who sets it |
|---|---|---|
| `DATABASE_URL` | Already set for local Docker | Same for everyone when using local Docker |
| `INTERNAL_API_KEY` | Same value you set in the frontend `.env.local` | Agree as a team (must match frontend) or each dev sets the same value in both frontend and backend |
| `ENCRYPTION_KEY` | Run `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | **Each developer** for local dev; use a shared key only if you share one dev database and need to read the same encrypted data |

Run the migration to create the database tables:

```bash
alembic upgrade head
```

Start the API server:

```bash
uvicorn app.main:app --reload
```

**If `pip install` fails on `psycopg2-binary` with "pg_config executable not found":** you are likely using Python 3.14 (or another version without pre-built wheels). Use Python 3.12: install it (e.g. `brew install python@3.12`), then create the venv with `python3.12 -m venv .venv`.

---

## What's running

| Service | URL |
|---|---|
| Next.js frontend | http://localhost:3000 |
| FastAPI backend | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| pgAdmin | http://localhost:5050 |
