#!/usr/bin/env bash
# Deploy and operate the app on the GCP VM created by deploy/terraform. No GitHub credentials live on the VM:
# the committed code is streamed over an IAP SSH tunnel and built there.
#
#   deploy/deploy.sh                  build and (re)start the committed code
#   deploy/deploy.sh garmin-login     one-time interactive Garmin login on the server
#   deploy/deploy.sh upload-data DIR  copy a local data/ folder (database, Garmin tokens) to the server
#   deploy/deploy.sh backup           run the backup to the bucket now
#   deploy/deploy.sh logs             follow the app logs
set -euo pipefail
cd "$(dirname "$0")/.."

TF=(terraform -chdir=deploy/terraform)
tf_out() { "${TF[@]}" output -raw "$1"; }
PROJECT=$(tf_out project_id) ZONE=$(tf_out zone) VM=$(tf_out instance)
URL=$(tf_out site_url) HOST=$(tf_out site_host)
COMPOSE="cd /opt/app/src && sudo docker compose --env-file /opt/app/.env -f deploy/docker-compose.yml"

vm_ssh() { gcloud compute ssh "$VM" --project "$PROJECT" --zone "$ZONE" --tunnel-through-iap --quiet "$@"; }

case "${1:-deploy}" in
  deploy)
    ENVFILE=deploy/.env.prod
    [ -f "$ENVFILE" ] || { echo "Missing $ENVFILE. Copy deploy/env.prod.example and fill it in."; exit 1; }
    grep -Eq '^DASHBOARD_PASSWORD=.{12,}' "$ENVFILE" || { echo "Set DASHBOARD_PASSWORD (at least 12 characters) in $ENVFILE."; exit 1; }
    [ -z "$(git status --porcelain)" ] || echo "Warning: uncommitted changes are NOT deployed (only HEAD is)."

    echo "Uploading settings..."
    { cat "$ENVFILE"; printf '\nSITE_ADDRESS=%s\nWHOOP_REDIRECT_URI=%s/auth/whoop/callback\nFRONTEND_URL=%s\n' "$HOST" "$URL" "$URL"; } |
      vm_ssh --command 'sudo mkdir -p /opt/app && sudo install -m 600 /dev/stdin /opt/app/.env'

    echo "Uploading code and building (the first build takes a few minutes)..."
    git archive --format=tar.gz HEAD | vm_ssh --command '
      set -e
      command -v docker >/dev/null || { echo "The VM is still setting itself up. Wait a minute and run again."; exit 1; }
      sudo rm -rf /opt/app/src && sudo mkdir -p /opt/app/src && sudo tar -xzf - -C /opt/app/src
      '"$COMPOSE"' up -d --build && sudo docker image prune -f >/dev/null'

    echo "Waiting for $URL ..."
    for _ in $(seq 1 30); do
      curl -fsS -m 5 "$URL/health" >/dev/null 2>&1 && { echo "Up: $URL"; exit 0; }
      sleep 5
    done
    echo "Not answering yet. HTTPS can take a minute after the first start. Check: deploy/deploy.sh logs"
    ;;
  garmin-login)
    vm_ssh --command "$COMPOSE exec app python -m app.garmin.login" -- -t
    ;;
  upload-data)
    [ -d "${2:-}" ] || { echo "Usage: deploy/deploy.sh upload-data path/to/data"; exit 1; }
    tar -C "$2" -c . | vm_ssh --command "$COMPOSE stop app && sudo tar -x -C /mnt/data/app && $COMPOSE start app"
    ;;
  backup)
    vm_ssh --command 'sudo /usr/local/bin/backup-app.sh && echo "Backup uploaded to gs://'"$(tf_out backup_bucket)"'"'
    ;;
  logs)
    vm_ssh --command "$COMPOSE logs -f --tail 100 app"
    ;;
  *)
    sed -n '2,10p' "$0"
    exit 1
    ;;
esac
