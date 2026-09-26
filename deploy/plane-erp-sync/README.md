# plane-erp-sync

Sends Plane activity to the ERP performance program (Plan B of
`docs/superpowers/plans/2026-09-26-plan-b-plane-erp-sync.md`).

## What it does

Every 15 minutes, on the Plane VM (`caryaar-plane`, project `caryaar-api-dev`):

1. Asks the ERP how far Plane data is already confirmed (`get_sync_state`) and re-sends from that day
   (at least yesterday, at most 31 days), so an outage leaves no silent gap.
2. Reads Plane's Postgres (`plane-db:5432` on the `plane-app_default` network) as the read-only role.
3. For each of those days (IST), counts per person: actions in Plane (`activity_count`) and tasks completed
   where they are an assignee (`completed_count`). Every active workspace member gets a row, zeros included.
4. For every module, counts tasks (excluding cancelled) and completed tasks.
5. POSTs to the ERP intake endpoints `caryaar_hr_ext.performance.api.ingest_activity` and
   `ingest_module_progress`. The real "synced through" time is sent only after every row was accepted.

Excluded from every count: deleted rows, drafts, bot users, users without a real email, Plane's own automation (auto-archive and
auto-close), and the 11 Yaar Space copies tagged `external_source = 'yaar-space'`.

## Known caveat

Actions taken through the shared `cy-automation` API token (the Google Chat `/task` command, admin
scripts) are booked by Plane to the token's owner, so they count as that person's activity. Move
automation to a dedicated bot user when that matters.

## Secrets

Files under `/opt/plane-erp-sync/secrets/` (mode 600, owned by the container user 10001), mounted read-only:

- `pg_password`: password of the read-only Postgres role `plane_erp_sync`, from Secret Manager
  `PLANE_ERP_SYNC_DB_PASSWORD` (create it before the first deploy). The role has `SELECT` on the ten
  tables the queries read and `default_transaction_read_only = on`; `deploy-on-vm.sh` creates or
  refreshes it using the owner password `PLANE_POSTGRES_PASSWORD`, which never reaches the container.
- `erp_key` from Secret Manager `erp-performance-sync-key` (`key:secret` of the ERP user
  `performance-sync@caryaar.com`, role Performance Sync only)

## Deploy

```bash
gcloud compute scp --recurse deploy/plane-erp-sync caryaar-plane:/tmp/plane-erp-sync \
  --zone=asia-south1-a --project=caryaar-api-dev --tunnel-through-iap
gcloud compute ssh caryaar-plane --zone=asia-south1-a --project=caryaar-api-dev --tunnel-through-iap \
  --command "sudo mkdir -p /opt/plane-erp-sync && sudo rm -rf /opt/plane-erp-sync/src && \
             sudo mv /tmp/plane-erp-sync /opt/plane-erp-sync/src && bash /opt/plane-erp-sync/src/deploy-on-vm.sh"
```

That builds the image and runs a dry run only. Check two numbers against the Plane UI, then re-run
with `deploy-on-vm.sh --start`.

## Operate

- Logs: `sudo docker logs -f plane-erp-sync` (rotated at 10 MB x 3)
- Stop: `sudo docker rm -f plane-erp-sync`
- Freshness: ERP, Performance Sync Settings, "Plane activity synced through" (should be under 15 minutes old)
- A Plane upgrade that changes a column makes the container exit at startup naming the missing column.
