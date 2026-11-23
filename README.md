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

## Your goal and profile
Nothing personal is hardcoded. A fresh clone starts with a blank profile (general fitness, no race). Open the Coach page, "Profile and goals", and set your goal type (general, triathlon, running, cycling, strength), goal, event name and date, max HR, gym days and split, background, injuries, and optional longest-session targets for run, swim and ride. The coach and the readiness card follow those.

To pre-fill a new database instead, copy `profile.example.json` to `data/profile.json` (gitignored) and edit it. It only supplies values you have not saved in the app. Triathlon is the only goal type with built-in readiness targets and plan knowledge (70.3); for other goals set your own targets.

## Login
The dashboard is password protected. Set `DASHBOARD_PASSWORD` in `.env` (use a long random one). Without it the API refuses every request. Sessions are a signed HttpOnly cookie that lasts `SESSION_DAYS` (default 30); changing the password signs everyone out. After 5 wrong attempts an IP is locked out for 5 minutes. If you expose this beyond localhost, put it behind HTTPS so the cookie is marked `Secure`.

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

## Weekly auto-run
While the backend is running, it syncs Whoop and Garmin every Sunday at 23:00 (machine local time) and writes the coach's plan for the coming week, shown on Home. If the machine was off and nothing has synced for over 8 days, it catches up on start. Set `AUTO_SYNC=0` to turn it off. "Sync now" always works on demand.
