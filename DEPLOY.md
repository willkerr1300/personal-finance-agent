# Travel Planner — Production Deployment Guide
## Vercel (Frontend) + Oracle Cloud A1 (Backend)

This guide deploys the frontend to Vercel's free Hobby plan and the backend to Oracle Cloud's
Always Free ARM A1 instance. Both are permanently free with no expiry and no credit card charges,
provided you stay within the Always Free resource limits.

---

## Table of Contents

1. [Architecture overview](#1-architecture-overview)
2. [Prerequisites and accounts](#2-prerequisites-and-accounts)
3. [Oracle Cloud: create the A1 instance](#3-oracle-cloud-create-the-a1-instance)
4. [Oracle Cloud: open firewall ports](#4-oracle-cloud-open-firewall-ports)
5. [Server: system setup](#5-server-system-setup)
6. [Server: clone and configure the backend](#6-server-clone-and-configure-the-backend)
7. [Server: run migrations](#7-server-run-migrations)
8. [Server: systemd services](#8-server-systemd-services)
9. [Server: nginx + HTTPS](#9-server-nginx--https)
10. [Vercel: deploy the frontend](#10-vercel-deploy-the-frontend)
11. [Google OAuth: production redirect URIs](#11-google-oauth-production-redirect-uris)
12. [Verification checklist](#12-verification-checklist)
13. [Updating after code changes](#13-updating-after-code-changes)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Architecture overview

```
Browser
  └── Vercel (Next.js, auto-deploys from GitHub on push to main)
        └── HTTPS → api.yourdomain.com (or raw Oracle public IP)
              └── nginx :443 → uvicorn :8000 (FastAPI)
                    ├── Celery worker (booking tasks)
                    ├── Celery beat  (hourly trip monitoring)
                    ├── Docker: PostgreSQL 16 (localhost:5432)
                    └── Docker: Redis 7      (localhost:6379)
```

**What is free and why:**

| Component | Platform | Free tier |
|---|---|---|
| Next.js frontend | Vercel Hobby | Always free, unlimited deploys |
| FastAPI + Celery | Oracle A1 (ARM) | Always free, 4 OCPUs + 24 GB RAM total |
| PostgreSQL | Docker on A1 | Included in instance |
| Redis | Docker on A1 | Included in instance |
| Block storage | Oracle | 200 GB always free |
| Public IP | Oracle reserved IP | 1 free per account |

---

## 2. Prerequisites and accounts

### 2.1 — Oracle Cloud account

1. Go to [cloud.oracle.com](https://cloud.oracle.com) and click **Start for free**
2. Enter your name, email, and choose a **Home Region** — pick one close to you.
   **The home region cannot be changed after signup.** US East (Ashburn) or UK South
   (London) are good default choices with full A1 availability.
3. Provide a mobile number for verification
4. Enter a credit card — Oracle uses it for identity verification only. Always Free
   resources do not generate charges. You will not be billed unless you manually upgrade
   to a paid account.
5. Complete signup and sign in to the OCI Console

### 2.2 — Vercel account

Sign up at [vercel.com](https://vercel.com) with your GitHub account. The Hobby plan is
free and covers everything this project needs.

### 2.3 — Domain (optional but recommended)

Without a domain you use the raw Oracle public IP on port 80 (no HTTPS). A domain lets
you get a TLS certificate and is strongly recommended if you share the app with others.

Cheap options: Namecheap (.com from ~$10/yr), Cloudflare Registrar (at-cost pricing),
or Porkbun. You can also use a free subdomain from [DuckDNS](https://www.duckdns.org)
if you don't want to pay for a domain.

### 2.4 — SSH key pair

Generate a key pair on your local machine if you don't have one. This is used to SSH
into the Oracle instance.

```bash
ssh-keygen -t ed25519 -C "oracle-travel-planner" -f ~/.ssh/oracle_travel_planner
```

This creates two files:
- `~/.ssh/oracle_travel_planner` — private key (never share this)
- `~/.ssh/oracle_travel_planner.pub` — public key (you paste this into Oracle)

---

## 3. Oracle Cloud: create the A1 instance

### 3.1 — Navigate to Compute Instances

OCI Console → hamburger menu (top-left) → **Compute** → **Instances** → **Create Instance**

### 3.2 — Configure the instance

**Name:** `travel-planner-backend`

**Placement:** Leave default (availability domain 1 in your home region)

**Image and shape:**
1. Under "Image and shape", click **Edit**
2. Click **Change image** → select **Canonical Ubuntu** → choose **22.04 LTS** (Minimal
   is fine) → click **Select image**
3. Click **Change shape** → select **Ampere** (ARM) → select **VM.Standard.A1.Flex**
4. Set **OCPUs: 2** and **Memory: 8 GB** → click **Select shape**

> The Always Free allowance is 4 OCPUs and 24 GB RAM total across all A1 instances in
> your account. 2 OCPUs + 8 GB is a comfortable allocation that runs this entire stack
> with headroom. Do not allocate all 4 OCPUs to one instance — spread them if needed.

**Networking:**
- Leave "Create new virtual cloud network" selected, or use an existing VCN
- Leave "Create new public subnet" selected
- **Assign a public IPv4 address:** make sure this is set to **Yes**

**Add SSH keys:**
- Select **Paste public keys**
- Open `~/.ssh/oracle_travel_planner.pub` in a text editor, copy the contents, paste it here

**Boot volume:**
- Click **Specify a custom boot volume size**
- Set to **50 GB** (the free allowance is 200 GB total across all volumes)

Click **Create**.

### 3.3 — Reserve a public IP

The instance gets a public IP on creation, but it is ephemeral — it changes if the instance
is ever stopped. Reserve it so it stays permanent.

1. Click into your new instance → **Attached VNICs** tab → click the VNIC name
2. Click **IPv4 Addresses** → click the **...** next to your public IP → **Edit**
3. Change "Public IP type" from **Ephemeral** to **Reserved**
4. Create a new reserved IP named `travel-planner-ip` → click **Update**

Write down this IP address. You will use it in every step that follows.

### 3.4 — SSH into the instance

```bash
ssh -i ~/.ssh/oracle_travel_planner ubuntu@<RESERVED_IP>
```

If this hangs, the firewall is not yet open — proceed to section 4 and then retry.

---

## 4. Oracle Cloud: open firewall ports

Oracle Cloud has **two independent firewall layers**. Both must allow a port for traffic
to reach your server. This is the most common reason connections fail silently.

**Layer 1: VCN Security List** — controls traffic at the network boundary (like AWS security groups)
**Layer 2: iptables on the instance** — Ubuntu firewall rules running inside the OS

### 4.1 — VCN Security List (Layer 1)

1. OCI Console → **Networking** → **Virtual Cloud Networks** → click your VCN
2. Click **Security Lists** → click **Default Security List**
3. Click **Add Ingress Rules** and add each row below as a separate rule:

| Source CIDR | Protocol | Destination port | Purpose |
|---|---|---|---|
| 0.0.0.0/0 | TCP | 22 | SSH |
| 0.0.0.0/0 | TCP | 80 | HTTP (for certbot + nginx redirect) |
| 0.0.0.0/0 | TCP | 443 | HTTPS (nginx + TLS) |

> If you are not using a domain and want to expose the API on port 8000 directly
> (not recommended), add a rule for port 8000 as well.

4. Click **Add Ingress Rules**

### 4.2 — iptables on the instance (Layer 2)

SSH into the instance and run:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 22 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
```

If you need port 8000 temporarily:
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
```

Save the rules so they survive a reboot:
```bash
sudo netfilter-persistent save
```

If `netfilter-persistent` is not found:
```bash
sudo apt install -y iptables-persistent
sudo netfilter-persistent save
```

---

## 5. Server: system setup

All commands in sections 5–9 run on the Oracle instance over SSH.

### 5.1 — System updates

```bash
sudo apt update && sudo apt upgrade -y
```

### 5.2 — Install system dependencies

```bash
sudo apt install -y \
  build-essential \
  libpq-dev \
  python3.12 \
  python3.12-venv \
  python3.12-dev \
  git \
  nginx \
  certbot \
  python3-certbot-nginx \
  iptables-persistent
```

Verify Python:
```bash
python3.12 --version   # must be 3.12.x
```

If Python 3.12 is not available in the default Ubuntu 22.04 repos, install via the
deadsnakes PPA:
```bash
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
```

### 5.3 — Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
newgrp docker
```

Verify:
```bash
docker ps   # should return an empty table, not a permission error
```

---

## 6. Server: clone and configure the backend

### 6.1 — Clone the repository

```bash
git clone https://github.com/willkerr1300/travel-planner.git
cd travel-planner
```

### 6.2 — Start PostgreSQL and Redis

```bash
docker compose up -d
docker compose ps   # all three services should show "running"
```

Both services bind to localhost inside the container network. They are not reachable
from the public internet.

### 6.3 — Python virtual environment

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> `psycopg2-binary` publishes aarch64 (ARM64) Linux wheels for Python 3.12 and
> installs without compilation on this instance. If you see a compilation error anyway,
> run: `pip install psycopg2 --no-binary psycopg2`

For live booking mode only (skip this if using `BOOKING_MOCK_MODE=true`):
```bash
playwright install chromium
playwright install-deps chromium
```

### 6.4 — Generate secrets

While the venv is active, generate the two required keys. Copy the output of each
command — you need them in the next step.

```bash
# INTERNAL_API_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# ENCRYPTION_KEY (Fernet)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 6.5 — Create the backend .env file

```bash
cp .env.example .env
nano .env
```

Minimum configuration (mock mode, no external APIs required):

```env
DATABASE_URL=postgresql://travelplanner:travelplanner@localhost:5432/travelplanner
INTERNAL_API_KEY=<paste value from step 6.4>
ENCRYPTION_KEY=<paste value from step 6.4>
BOOKING_MOCK_MODE=true
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Optional — leave blank to use mock fallbacks, or fill in for live integrations
AMADEUS_CLIENT_ID=
AMADEUS_CLIENT_SECRET=
AMADEUS_ENV=test
ANTHROPIC_API_KEY=
STRIPE_SECRET_KEY=
SENDGRID_API_KEY=
SENDGRID_FROM_EMAIL=
BROWSERLESS_URL=
```

Save: Ctrl+O, Enter, Ctrl+X.

---

## 7. Server: run migrations

```bash
# Must be in backend/ with venv active
alembic upgrade head
```

Expected final output line:
```
INFO  [alembic.runtime.migration] Running upgrade 003 -> 004, add trip_alerts table
```

Run this command again any time you pull new code — it is safe to run repeatedly and
only applies unapplied migrations.

---

## 8. Server: systemd services

Three systemd services keep the backend processes running and automatically restart them
on crash or reboot.

### 8.1 — FastAPI service

```bash
sudo nano /etc/systemd/system/travelplanner-api.service
```

```ini
[Unit]
Description=Travel Planner FastAPI
After=network.target docker.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/travel-planner/backend
ExecStart=/home/ubuntu/travel-planner/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
EnvironmentFile=/home/ubuntu/travel-planner/backend/.env

[Install]
WantedBy=multi-user.target
```

### 8.2 — Celery worker service

```bash
sudo nano /etc/systemd/system/travelplanner-worker.service
```

```ini
[Unit]
Description=Travel Planner Celery Worker
After=network.target docker.service travelplanner-api.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/travel-planner/backend
ExecStart=/home/ubuntu/travel-planner/backend/.venv/bin/celery -A app.worker worker --loglevel=info --concurrency=2
Restart=always
RestartSec=5
EnvironmentFile=/home/ubuntu/travel-planner/backend/.env

[Install]
WantedBy=multi-user.target
```

### 8.3 — Celery beat service

```bash
sudo nano /etc/systemd/system/travelplanner-beat.service
```

```ini
[Unit]
Description=Travel Planner Celery Beat (trip monitoring)
After=network.target docker.service travelplanner-worker.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/travel-planner/backend
ExecStart=/home/ubuntu/travel-planner/backend/.venv/bin/celery -A app.worker beat --loglevel=info
Restart=always
RestartSec=5
EnvironmentFile=/home/ubuntu/travel-planner/backend/.env

[Install]
WantedBy=multi-user.target
```

### 8.4 — Enable and start all three

```bash
sudo systemctl daemon-reload
sudo systemctl enable travelplanner-api travelplanner-worker travelplanner-beat
sudo systemctl start travelplanner-api travelplanner-worker travelplanner-beat
```

Check they are all running:
```bash
sudo systemctl status travelplanner-api travelplanner-worker travelplanner-beat
```

Each should show `active (running)`. To see live logs:
```bash
sudo journalctl -u travelplanner-api -f
```

Smoke test from within the instance:
```bash
curl http://127.0.0.1:8000/docs   # returns FastAPI Swagger HTML
```

---

## 9. Server: nginx + HTTPS

Skip to section 10 if you have no domain and want to expose the API on port 8000
directly (no HTTPS). In that case, add port 8000 to both firewall layers (section 4)
and set `BACKEND_URL=http://<RESERVED_IP>:8000` in Vercel.

### 9.1 — Point your domain to the Oracle instance

In your DNS provider, create an **A record**:

```
api.yourdomain.com  →  <RESERVED_IP>
```

Propagation can take a few minutes to a few hours. Check it with:
```bash
dig api.yourdomain.com +short   # should return your Oracle IP
```

If you are using DuckDNS, follow their instructions at duckdns.org to assign your
subdomain to the Oracle IP.

### 9.2 — nginx site configuration

```bash
sudo nano /etc/nginx/sites-available/travelplanner
```

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

> `proxy_read_timeout 120s` is important. Booking tasks can take up to 60 seconds and
> the default nginx timeout is 60s, which would drop the connection mid-request.

```bash
sudo ln -s /etc/nginx/sites-available/travelplanner /etc/nginx/sites-enabled/
sudo nginx -t          # must print "syntax is ok" and "test is successful"
sudo systemctl reload nginx
```

### 9.3 — TLS certificate (Let's Encrypt)

```bash
sudo certbot --nginx -d api.yourdomain.com
```

Follow the prompts:
- Enter an email for renewal notices
- Agree to Terms of Service
- Choose whether to share your email with EFF (optional)

Certbot modifies the nginx config to add TLS and installs a systemd timer that
auto-renews the certificate before expiry. No manual renewal is needed.

Verify:
```bash
curl https://api.yourdomain.com/docs   # must return HTML, not a certificate error
```

### 9.4 — Remove port 8000 from the firewall (optional hardening)

Once nginx is in front, uvicorn only needs to be reachable on localhost. Remove the
port 8000 rule from the VCN Security List and iptables if you added it earlier.

```bash
# Remove iptables rule for port 8000 if it exists
sudo iptables -D INPUT -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save
```

---

## 10. Vercel: deploy the frontend

### 10.1 — Import the project

1. Go to [vercel.com](https://vercel.com) → **Add New Project**
2. Click **Import Git Repository** → select `willkerr1300/travel-planner`
3. Set **Root Directory** to `frontend`
4. Framework preset auto-detects as **Next.js** — leave it

Do not click Deploy yet.

### 10.2 — Set environment variables

In the Vercel project settings (or on the import screen under "Environment Variables"),
add the following. Set each variable for **Production**, **Preview**, and **Development**
unless noted.

| Variable | Value |
|---|---|
| `AUTH_SECRET` | Generate with `openssl rand -base64 32` on your local machine |
| `AUTH_URL` | `https://your-project.vercel.app` (Vercel's auto-assigned domain) |
| `GOOGLE_CLIENT_ID` | From Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | From Google Cloud Console |
| `INTERNAL_API_KEY` | Exact same value you set in `backend/.env` on the Oracle instance |
| `BACKEND_URL` | `https://api.yourdomain.com` (or `http://<RESERVED_IP>:8000` if no domain) |

Generate `AUTH_SECRET` locally:
```bash
# macOS / Linux:
openssl rand -base64 32

# Windows (PowerShell):
[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }) -as [byte[]])
```

### 10.3 — Deploy

Click **Deploy**. Vercel runs `npm install` and `next build`, then deploys to its CDN.
This takes 1–2 minutes.

After the deploy completes, your frontend is live at `https://your-project.vercel.app`.

### 10.4 — Custom domain on Vercel (optional)

If you have a domain and want the frontend on `app.yourdomain.com` instead of the
auto-assigned Vercel URL:

1. Vercel project → **Settings** → **Domains** → add `app.yourdomain.com`
2. Vercel shows you a CNAME record to add in your DNS provider:
   ```
   app.yourdomain.com  CNAME  cname.vercel-dns.com
   ```
3. Once DNS propagates, Vercel issues a TLS certificate automatically
4. Update `AUTH_URL` in Vercel environment variables to `https://app.yourdomain.com`
5. Redeploy: Vercel dashboard → **Deployments** → click the latest → **Redeploy**

---

## 11. Google OAuth: production redirect URIs

Google OAuth will reject logins if the redirect URI doesn't match exactly.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → **APIs &
   Services** → **Credentials** → your OAuth 2.0 Client ID
2. Under **Authorized JavaScript origins**, add:
   - `https://your-project.vercel.app`
   - `https://app.yourdomain.com` (if using a custom domain)
3. Under **Authorized redirect URIs**, add:
   - `https://your-project.vercel.app/api/auth/callback/google`
   - `https://app.yourdomain.com/api/auth/callback/google` (if using a custom domain)
4. Click **Save**

Changes take effect immediately.

---

## 12. Verification checklist

Work through these in order after deployment to confirm the full stack is functioning.

### Backend health

From your local machine:
```bash
curl https://api.yourdomain.com/docs
# Expected: HTML page (FastAPI Swagger UI)
```

### Frontend loads

- Open `https://your-project.vercel.app` (or your custom domain)
- The login page should appear without errors

### Google OAuth

- Click **Sign in with Google**
- Complete the Google sign-in flow
- You should land on the dashboard with your email shown in the navigation

### Profile and trip creation

- Go to `/profile`, fill in first name and last name, click Save
- Return to the dashboard and submit: `"Fly me from New York to Tokyo in June, 7 days, budget $3000"`
- You should be redirected to `/trips/[id]` with 3 itinerary options

### Booking (mock mode)

- Select an itinerary → click **Book this trip**
- Within ~30 seconds, each booking row should show step-by-step agent logs
- Final state: green "Confirmed" badges and 6-character confirmation numbers

### Service status on Oracle instance

```bash
sudo systemctl status travelplanner-api travelplanner-worker travelplanner-beat
```

All three should show `active (running)`.

---

## 13. Updating after code changes

**Frontend** — Vercel auto-deploys when you push to `main`. No action needed.

**Backend** — SSH into the Oracle instance and run:

```bash
cd ~/travel-planner
git pull origin main
cd backend
source .venv/bin/activate
pip install -r requirements.txt   # run if requirements.txt changed
alembic upgrade head               # run if new migrations were added
sudo systemctl restart travelplanner-api travelplanner-worker travelplanner-beat
```

---

## 14. Troubleshooting

### Cannot SSH into the instance

- Check the VCN Security List has port 22 open for your IP
- Check iptables allows port 22: `sudo iptables -L INPUT -n`
- Verify you are using the correct private key: `ssh -i ~/.ssh/oracle_travel_planner ubuntu@<IP>`
- Oracle instances use `ubuntu` as the username (not `ec2-user` or `opc`)

### curl to the API hangs or times out

Almost always a firewall issue. Both layers must allow the port:
1. OCI Console → VCN → Security List → confirm port 80/443 ingress rules exist
2. On the instance: `sudo iptables -L INPUT -n | grep -E "80|443"` — confirm ACCEPT rules exist
3. Confirm nginx is running: `sudo systemctl status nginx`
4. Confirm uvicorn is running: `sudo systemctl status travelplanner-api`

### 502 Bad Gateway from nginx

nginx is running but uvicorn is not. Check:
```bash
sudo systemctl status travelplanner-api
sudo journalctl -u travelplanner-api -n 50
```

Common causes: `.env` file not found, Python import error, database not reachable.

### Frontend returns 401 Unauthorized

The `INTERNAL_API_KEY` in Vercel does not match the one in `backend/.env` on the Oracle
instance. They must be identical.

### Booking stuck in "in progress" forever

The Celery worker is not running or cannot reach Redis:
```bash
sudo systemctl status travelplanner-worker
docker compose ps   # redis must show "running"
```

If the worker crashed, check:
```bash
sudo journalctl -u travelplanner-worker -n 100
```

### Login redirects back to / instead of /dashboard

- `AUTH_URL` in Vercel must exactly match the URL you are accessing (including `https://`
  and the correct domain — no trailing slash)
- The redirect URI in Google Cloud Console must exactly match the URL being used

### `psycopg2-binary` fails to install (ARM)

If prebuilt wheels are unavailable for your exact Python/ARM combination:
```bash
sudo apt install -y libpq-dev python3.12-dev
pip install psycopg2 --no-binary psycopg2
```

This compiles from source using the system `libpq-dev` and takes ~30 seconds.

### `alembic upgrade head` fails with "relation already exists"

The database has tables from a previous install. Check which migrations have been applied:
```bash
alembic current
```

If the output is `(head)`, the database is already up to date. If it shows an earlier
revision, run `alembic upgrade head` again — it will only apply unapplied migrations.
If the tables exist but Alembic has no record, you may need to stamp the current
revision: `alembic stamp head`.

### Certbot fails with "Port 80 not reachable"

- Confirm port 80 is open in the VCN Security List
- Confirm iptables allows port 80: `sudo iptables -L INPUT -n | grep 80`
- Confirm DNS is pointing to your Oracle IP: `dig api.yourdomain.com +short`
- Confirm nginx is running and listening: `sudo ss -tlnp | grep :80`

---

## Resource summary

| Resource | Oracle Always Free limit | What this deployment uses |
|---|---|---|
| A1 OCPU | 4 total | 2 |
| A1 RAM | 24 GB total | 8 GB |
| Block storage | 200 GB total | 50 GB |
| Reserved public IPs | 2 total | 1 |
| Outbound data transfer | 10 TB/month | Well within limits for a personal project |
