#!/usr/bin/env bash
# Run the whole app (API + website) on http://127.0.0.1:8000. Builds the website if needed.
# Optional: KEEP_AWAKE=1 ./scripts/start.sh   keeps the Mac from idle-sleeping while this runs.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/public frontend/index.html -newer frontend/dist/index.html -print -quit)" ]; then
  echo "Building the website..."
  (cd frontend && npm install --silent && npm run build --silent)
fi

cmd=(uv --directory backend run uvicorn app.main:app --host 127.0.0.1 --port 8000)
if [ "${KEEP_AWAKE:-0}" = "1" ] && command -v caffeinate >/dev/null; then
  exec caffeinate -i "${cmd[@]}"
fi
exec "${cmd[@]}"
