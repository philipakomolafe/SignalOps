# SignalOps

<p align="center">
  <img src="web/assets/logo.png" alt="SignalOps Logo" width="120" />
</p>

SignalOps is your go-to tool for autonomous analysis.

It helps operators upload order data, generate key business features, detect silent revenue leaks, and get plain-language diagnostic guidance they can act on quickly.

## Core MVP (Format 1)

- CSV upload ingestion
- Feature generation
- Rule-based leak detection
- Diagnostic report generation
- User authentication (signup/login/logout)
- User-scoped SQLite persistence for analysis history
- Dashboard workflow for upload, analysis, and history replay

## Tech Stack

- Backend: FastAPI
- Frontend: Modular HTML/CSS/JS
- Storage: SQLite
- Validation/Models: Pydantic

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
│  ├─ assets/
│  ├─ dashboard/
│  ├─ login/
│  ├─ signup/
│  ├─ v1/
│  └─ v2/
├─ requirements.txt
└─ README.md
```

## Run Locally

1. Install dependencies

```bash
pip install -r requirements.txt
```

2. Start the API (also serves frontend routes)

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

3. Open the app

- Landing (v1): http://127.0.0.1:8000/v1/
- Landing (v2): http://127.0.0.1:8000/v2/
- Login/Register: http://127.0.0.1:8000/login/
- Dashboard: http://127.0.0.1:8000/dashboard/

4. Test with sample CSV

- `app/utils/sample_shopify_orders.csv`

## Clean URL Behavior

SignalOps uses canonical URL handling:

- `/dashboard/index.html` -> `/dashboard/`
- `/login/index.html` -> `/login/`
- `/index.html` -> `/`

It also supports chat-style entry URLs:

- `/c/<conversation_id>`

## API Endpoints

### Auth

- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`

### Analysis

- `POST /api/v1/srl/analyze`
- `GET /api/v1/srl/history`
- `GET /api/v1/srl/history/{run_id}`

### System

- `GET /health`

## Persistence

- SQLite DB file: `app/data/signalops.db`
- Analysis rows are user-scoped
- Content-hash dedup prevents duplicate re-analysis for identical uploads

## Pricing (Launch)

- Free: One-time CSV analysis (1 upload + 1 report, no monitoring alerts)
- Starter ($29/month): Continuous monitoring, weekly leak checks, saved history
- Scale ($99/month): Integrations, real-time alerts, multi-store coverage, priority support

## Notes

- Dashboard access requires authentication.
- Frontend assets are served from `/assets` (for example, `/assets/logo.png`).

---

Built as an operator-first MVP for detecting silent revenue leaks before they become visible losses.
