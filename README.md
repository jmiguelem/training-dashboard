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

## Weekly auto-run
While the backend is running, it syncs Whoop and Garmin every Sunday at 23:00 (machine local time) and writes the coach's plan for the coming week, shown on Home. If the machine was off and nothing has synced for over 8 days, it catches up on start. Set `AUTO_SYNC=0` to turn it off. "Sync now" always works on demand.

## Run it with one command
```bash
./scripts/start.sh            # builds the website if needed, serves everything on http://127.0.0.1:8000
KEEP_AWAKE=1 ./scripts/start.sh   # also stops the Mac idle-sleeping while it runs (so the Sunday run happens)
```

## On your phone (Mac + Tailscale, free)
The app stays on your Mac. Tailscale makes a private network between your Mac and phone, with HTTPS.
1. Install Tailscale on the Mac and on the phone, and sign in to the same account on both.
2. On the Mac, with the app running: `tailscale serve --bg 8000`. It prints an address like `https://your-mac.your-tailnet.ts.net`.
3. On the phone, open that address in Chrome, then menu > Add to Home screen.
Only your own devices on your Tailscale account can reach it. The Mac must be on, awake and running the app. Whoop/Garmin sign-in is done once on the Mac.
