#!/usr/bin/env bash
# deploy/plane-erp-sync/deploy-on-vm.sh: run ON caryaar-plane after scp'ing this folder to /opt/plane-erp-sync/src
set -euo pipefail
PROJECT=caryaar-api-dev
APP=/opt/plane-erp-sync
sudo mkdir -p "$APP/secrets"
DB=$(sudo docker ps --format '{{.Names}}' | grep -E 'plane-db' | head -1)
[ -n "$DB" ] || { echo "FATAL: plane-db container not found"; exit 1; }
echo "=== read-only Postgres role plane_erp_sync (SELECT on the 10 tables only)"
SYNC_PW=$(gcloud secrets versions access latest --secret=PLANE_ERP_SYNC_DB_PASSWORD --project="$PROJECT") \
  || { echo "FATAL: create Secret Manager secret PLANE_ERP_SYNC_DB_PASSWORD first"; exit 1; }
OWNER_PW=$(gcloud secrets versions access latest --secret=PLANE_POSTGRES_PASSWORD --project="$PROJECT")
sudo docker exec -i -e PGPASSWORD="$OWNER_PW" "$DB" psql -U plane -d plane -v ON_ERROR_STOP=1 \
  -v pw="$SYNC_PW" <<'SQL'
SELECT 'CREATE ROLE plane_erp_sync LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'plane_erp_sync') \gexec
ALTER ROLE plane_erp_sync WITH LOGIN PASSWORD :'pw';
ALTER ROLE plane_erp_sync SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE plane TO plane_erp_sync;
GRANT USAGE ON SCHEMA public TO plane_erp_sync;
GRANT SELECT ON issue_activities, issues, issue_assignees, labels, issue_labels, users, states, modules,
  module_issues, projects, workspaces, workspace_members TO plane_erp_sync;
SQL
unset OWNER_PW
echo "=== secrets -> $APP/secrets (600)"
printf '%s' "$SYNC_PW" | sudo tee "$APP/secrets/pg_password" >/dev/null
unset SYNC_PW
gcloud secrets versions access latest --secret=erp-performance-sync-key --project="$PROJECT" | sudo tee "$APP/secrets/erp_key" >/dev/null
sudo chown -R 10001 "$APP/secrets" && sudo chmod 600 "$APP/secrets/"*
echo "=== build"
sudo docker build -t plane-erp-sync:latest "$APP/src"
echo "=== dry run (read-only, prints payload counts)"
sudo docker run --rm --network plane-app_default -e PLANE_DB_HOST="$DB" -e PLANE_DB_USER=plane_erp_sync \
  -e PLANE_DB_PASSWORD_FILE=/run/secrets/pg_password -e ERP_KEY_FILE=/run/secrets/erp_key \
  -v "$APP/secrets:/run/secrets:ro" plane-erp-sync:latest python -m plane_erp_sync.main --dry-run | tail -5
if [ "${1:-}" != "--start" ]; then echo "Dry run only. Re-run with --start to launch."; exit 0; fi
sudo docker rm -f plane-erp-sync 2>/dev/null || true
sudo docker run -d --name plane-erp-sync --restart unless-stopped --network plane-app_default \
  -e PLANE_DB_HOST="$DB" -e PLANE_DB_USER=plane_erp_sync -e PLANE_DB_PASSWORD_FILE=/run/secrets/pg_password -e ERP_KEY_FILE=/run/secrets/erp_key \
  -v "$APP/secrets:/run/secrets:ro" --log-opt max-size=10m --log-opt max-file=3 plane-erp-sync:latest
sudo docker logs --tail 20 plane-erp-sync
