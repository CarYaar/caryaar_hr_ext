#!/usr/bin/env bash
# deploy/plane-erp-sync/deploy-on-vm.sh: run ON caryaar-plane after scp'ing this folder to /opt/plane-erp-sync/src
set -euo pipefail
PROJECT=caryaar-api-dev
APP=/opt/plane-erp-sync
sudo mkdir -p "$APP/secrets"
echo "=== secrets -> $APP/secrets (600)"
gcloud secrets versions access latest --secret=PLANE_POSTGRES_PASSWORD --project="$PROJECT" | sudo tee "$APP/secrets/pg_password" >/dev/null
gcloud secrets versions access latest --secret=erp-performance-sync-key --project="$PROJECT" | sudo tee "$APP/secrets/erp_key" >/dev/null
sudo chown -R 10001 "$APP/secrets" && sudo chmod 600 "$APP/secrets/"*
DB=$(sudo docker ps --format '{{.Names}}' | grep -E 'plane-db' | head -1)
[ -n "$DB" ] || { echo "FATAL: plane-db container not found"; exit 1; }
echo "=== build"
sudo docker build -t plane-erp-sync:latest "$APP/src"
echo "=== dry run (read-only, prints payload counts)"
sudo docker run --rm --network plane-app_default -e PLANE_DB_HOST="$DB" \
  -e PLANE_DB_PASSWORD_FILE=/run/secrets/pg_password -e ERP_KEY_FILE=/run/secrets/erp_key \
  -v "$APP/secrets:/run/secrets:ro" plane-erp-sync:latest python -m plane_erp_sync.main --dry-run | tail -5
if [ "${1:-}" != "--start" ]; then echo "Dry run only. Re-run with --start to launch."; exit 0; fi
sudo docker rm -f plane-erp-sync 2>/dev/null || true
sudo docker run -d --name plane-erp-sync --restart unless-stopped --network plane-app_default \
  -e PLANE_DB_HOST="$DB" -e PLANE_DB_PASSWORD_FILE=/run/secrets/pg_password -e ERP_KEY_FILE=/run/secrets/erp_key \
  -v "$APP/secrets:/run/secrets:ro" --log-opt max-size=10m --log-opt max-file=3 plane-erp-sync:latest
sudo docker logs --tail 20 plane-erp-sync
