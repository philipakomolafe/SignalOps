# SignalOps

<p align="center">
  <img src="web/assets/logo.png" alt="SignalOps Logo" width="120" />
</p>

SignalOps is an operator-first analysis platform for identifying performance leaks, explaining why they are happening, and guiding what to do next.

It currently supports:

- CSV-based analysis workflows
- Shopify OAuth integration + autonomous monitoring
- Authenticated user dashboard + history replay
- Admin analytics views
- Plan-based billing and access control with Flutterwave

## What Is Implemented

### Analysis + Diagnostics

- CSV ingestion and normalization
- Feature computation and comparison windows
- Rule-based leak detection
- Plain-language diagnosis blocks:
  - What changed
  - Likely why
  - What to do
- Content-hash dedup for repeated identical uploads

### Authentication + Sessions

- Signup/login/logout endpoints
- Bearer-token session model
- Session revocation support

### Shopify Integration

- OAuth connect flow for `.myshopify.com` stores
- Expiring offline token support + refresh flow
- Legacy token migration path
- Store sync status and manual monitor trigger
- Scheduled monitor endpoint for autonomous runs
- No-protected-data scope/field posture

### Billing + Access Control

- Flutterwave inline checkout initialization
- Webhook signature verification + server-side transaction verification
- Idempotent payment event ingestion
- Subscription upsert and plan activation
- Admin email allow-list override
- Plan gates:
  - Free: limited analysis usage
  - Starter/Pro: expanded access
  - Admin: full access

### Frontend Surfaces

- Landing pages: `v1`, `v2`
- Login/register
- User dashboard
- Buy/checkout page
- Admin metrics page

## Tech Stack

- Backend: FastAPI
- Frontend: Modular HTML/CSS/JS
- Storage: SQLite (default) or PostgreSQL (Aiven/Render compatible)
- Models/Validation: Pydantic

## Project Structure

```text
signalops/
├─ app/
│  ├─ main.py
│  ├─ configs/
│  ├─ models/
│  ├─ services/
│  └─ utils/
├─ web/
│  ├─ admin/
│  ├─ assets/
│  ├─ buy/
│  ├─ dashboard/
│  ├─ login/
│  ├─ signup/
│  ├─ v1/
│  └─ v2/
├─ requirements.txt
└─ README.md
```

## Local Run

1. Install dependencies

```bash
pip install -r requirements.txt
```

2. Optional: use PostgreSQL

```bash
# Linux/macOS
export DATABASE_URL="postgres://<db_user>:<db_password>@<db_host>:<db_port>/<db_name>?sslmode=require"

# Windows PowerShell
$env:DATABASE_URL="postgres://<db_user>:<db_password>@<db_host>:<db_port>/<db_name>?sslmode=require"
```

Security note:

- Never commit real credentials, API keys, or tokens to git.
- Keep production secrets only in your deployment secret manager (Render, Aiven, GitHub Secrets, etc.).

3. Start API + static routes

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

4. Open routes

- Landing v1: `http://127.0.0.1:8000/v1/`
- Landing v2: `http://127.0.0.1:8000/v2/`
- Login: `http://127.0.0.1:8000/login/`
- Dashboard: `http://127.0.0.1:8000/dashboard/`
- Buy: `http://127.0.0.1:8000/buy/`
- Admin: `http://127.0.0.1:8000/admin/`

5. Sample CSV

- `app/utils/sample_shopify_orders.csv`

## Canonical URL Behavior

- `/dashboard/index.html` -> `/dashboard/`
- `/login/index.html` -> `/login/`
- `/index.html` -> `/`
- Chat-style redirect: `/c/<conversation_id>` -> dashboard conversation route

## Key API Endpoints

### System

- `GET /health`

### Auth

- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`

### Analysis

- `POST /api/v1/srl/analyze`
- `GET /api/v1/srl/history`
- `GET /api/v1/srl/history/{run_id}`

### Shopify

- `POST /api/v1/integrations/shopify/connect/start`
- `GET /api/v1/integrations/shopify/callback`
- `GET /api/v1/integrations/shopify/status`
- `POST /api/v1/integrations/shopify/disconnect`
- `POST /api/v1/integrations/shopify/monitor-now`
- `POST /api/v1/monitor/run/shopify` (internal token)

### Billing

- `GET /api/v1/buy`
- `POST /api/v1/payments/flutterwave/initialize`
- `POST /api/v1/payments/flutterwave/webhook`
- `GET /api/v1/account/plan`

### Admin

- `GET /api/v1/admin/founder-metrics`
- `GET /api/v1/admin/feature-timeseries`

### Maintenance

- `POST /api/v1/maintenance/data-retention/run` (internal token)

## Environment Variables

All variables below are names only. Use real values in your deployment secret manager, not in this README.

### Core

- `DATABASE_URL` (optional, for PostgreSQL)
- `CORS_ALLOW_ORIGINS`
- `APP_PUBLIC_BASE_URL`

### Auth/Admin

- `ADMIN_EMAILS`

### Monitor/Cron Security

- `MONITOR_INTERNAL_TOKEN`

### Shopify

- `SHOPIFY_API_KEY`
- `SHOPIFY_API_SECRET`
- `SHOPIFY_SCOPES`
- `SHOPIFY_API_VERSION`
- `SHOPIFY_STATE_SECRET`
- `SHOPIFY_TOKEN_REFRESH_LEEWAY_SECONDS`

### Flutterwave + Billing

- `FLW_PUBLIC_KEY`
- `FLW_SECRET_KEY`
- `FLW_WEBHOOK_SECRET_HASH`
- `FLW_API_BASE_URL`
- `FLW_STARTER_PLAN_ID`
- `FLW_PRO_PLAN_ID`
- `BILLING_CURRENCY`
- `BILLING_STARTER_AMOUNT`
- `BILLING_PRO_AMOUNT`

### Retention

- `RETENTION_MONITOR_RUNS_DAYS`
- `RETENTION_REVOKED_SESSIONS_DAYS`
- `RETENTION_INACTIVE_SHOPIFY_DAYS`
- `RETENTION_ANALYSIS_RUNS_DAYS`

Recommended local setup:

- Create a local `.env` file for development values.
- Add `.env` to `.gitignore`.
- Commit only an `.env.example` with placeholders.

Example `.env.example` (safe placeholders only):

```env
DATABASE_URL=
ADMIN_EMAILS=
MONITOR_INTERNAL_TOKEN=
SHOPIFY_API_KEY=
SHOPIFY_API_SECRET=
SHOPIFY_STATE_SECRET=
FLW_PUBLIC_KEY=
FLW_SECRET_KEY=
FLW_WEBHOOK_SECRET_HASH=
FLW_STARTER_PLAN_ID=
FLW_PRO_PLAN_ID=
```

## Scheduled Jobs

You can run cron either with your platform scheduler or GitHub Actions.

Recommended schedules:

- Shopify monitor: `POST /api/v1/monitor/run/shopify` every 30 minutes
- Retention cleanup: `POST /api/v1/maintenance/data-retention/run` once daily

Required header for both:

- `x-monitor-token: <MONITOR_INTERNAL_TOKEN>`

## Current Product Notes

- Dashboard and admin views are authenticated.
- Admin routes require configured admin email allow-list.
- Shopify support is intentionally scoped to non-protected order data for faster deployment and reduced compliance friction.
- Frontend assets are served from `/assets`.
- If any secret was previously committed, rotate it immediately.

---

Built as a pragmatic operator tool for turning business data into fast, actionable decisions.
