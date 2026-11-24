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

## Run it with one command
```bash
./scripts/start.sh            # builds the website if needed, serves everything on http://127.0.0.1:8000
KEEP_AWAKE=1 ./scripts/start.sh   # also stops the Mac idle-sleeping while it runs (so the Sunday run happens)
```

## Deploy to Google Cloud (always on, nothing runs on your laptop)
Terraform creates one small VM (Debian, Docker, Caddy for automatic HTTPS), a static IP, a separate persistent disk for the database and Garmin tokens, a private backup bucket (nightly, 30 days kept), and a firewall that only opens 80 and 443. SSH goes through Google's IAP tunnel, so port 22 is never public. No secrets go into Terraform or its state.

Prerequisites: a GCP project with billing, `gcloud` and `terraform` installed, and `gcloud auth login && gcloud auth application-default login`.

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars   # set project_id (and domain, optionally)
terraform init && terraform apply
cd ../..
cp deploy/env.prod.example deploy/.env.prod    # DASHBOARD_PASSWORD (12+ chars), timezone, API keys
deploy/deploy.sh                               # waits for the VM, builds, starts, prints your URL
```

Then, once:
1. Whoop: set the app's redirect URI in the Whoop developer portal to `<your URL>/auth/whoop/callback` (the URL is `terraform output site_url`), then open `<your URL>/auth/whoop/login` while signed in.
2. Garmin: `deploy/deploy.sh garmin-login` (asks for the MFA code).
3. To keep your history, copy your local data first: `deploy/deploy.sh upload-data ./data`.
4. On your phone, open the URL, sign in, then Add to Home screen.

Notes:
- Without a `domain`, the site is `https://<ip-with-dashes>.sslip.io`, which needs no DNS. With a domain, point an A record at `terraform output ip` first.
- `deploy/deploy.sh` deploys the last commit, not uncommitted changes. Other commands: `logs`, `backup`.
- The default `e2-micro` has 1 GB of memory; the config adds swap so builds work. Set `machine_type = "e2-small"` if builds are slow. Check Google's current free-tier terms and pricing for your region.
- The database lives on its own disk with `prevent_destroy`, so replacing the VM keeps your data. Restore a backup by downloading it from the bucket and using `upload-data`.
- Running more apps in the same project: copy this folder, give each a different `name` in `terraform.tfvars`, or put several containers on one VM behind the same Caddy.

## On your phone from your own Mac (Tailscale, free)
The app stays on your Mac. Tailscale makes a private network between your Mac and phone, with HTTPS.
1. Install Tailscale on the Mac and on the phone, and sign in to the same account on both.
2. On the Mac, with the app running: `tailscale serve --bg 8000`. It prints an address like `https://your-mac.your-tailnet.ts.net`.
3. On the phone, open that address in Chrome, then menu > Add to Home screen.
Only your own devices on your Tailscale account can reach it. The Mac must be on, awake and running the app. Whoop/Garmin sign-in is done once on the Mac.
