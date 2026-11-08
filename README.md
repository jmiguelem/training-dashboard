# Training Dashboard

Personal dashboard for Garmin and Whoop data, with progress analysis.

## Stack
- Backend: Python, FastAPI, SQLite
- Frontend: Vite, React, TypeScript (PWA)

## Layout
- `backend/` API, sync jobs, metrics
- `frontend/` dashboard UI

## Setup
Copy `.env.example` to `.env` and fill in values. Never commit `.env`.

## Run
```bash
# backend (http://localhost:8000)
cd backend && uv run uvicorn app.main:app --reload
# frontend (http://localhost:5173, proxies /api and /auth to the backend)
cd frontend && npm install && npm run dev
```

First-time connections:
- Whoop: open http://localhost:8000/auth/whoop/login
- Garmin: `cd backend && uv run python -m app.garmin.login`

Then press "Sync now" in the dashboard.
