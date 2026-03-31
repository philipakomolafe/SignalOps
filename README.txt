# Currently building - SignalOps.
SignalOps - your goto tool for autonomous analysis...

MVP (Format 1) now includes:
- CSV upload ingestion
- Feature generation
- Rule-based leak detection
- Diagnostic report generation
- SQLite persistence for analysis history

Run locally:
1) Install dependencies: pip install -r requirements.txt
2) Start API: uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
3) Serve frontend folder from backend API
4) Open v1 UI: http://localhost:5500/v1/
5) Upload sample CSV: app/utils/sample_shopify_orders.csv
6) Signup page: http://localhost:8000/signup/
7) Login page: http://localhost:8000/login/

Persistence:
- Database file: app/data/signalops.db
- List history: GET /api/v1/srl/history
- Read saved run: GET /api/v1/srl/history/{run_id}

Auth:
- Signup endpoint: POST /api/v1/auth/signup
- Login endpoint: POST /api/v1/auth/login
- Current user endpoint: GET /api/v1/auth/me
- Logout endpoint: POST /api/v1/auth/logout
