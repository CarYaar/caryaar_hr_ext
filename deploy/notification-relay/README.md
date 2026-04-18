# Notification Relay deploy

`metalmon/notification-relay` Docker image on the `caryaar-erpnext` VM. Bridges Frappe Push Notifications → Firebase Cloud Messaging so HRMS PWA + Desk users can receive browser push.

## Current deployment

- Host: `caryaar-erpnext` VM, GCP project `cy-erp`, zone `asia-south1-b`
- Config dir: `/opt/notification-relay/config/`
- Docker compose: `/opt/notification-relay/docker-compose.yml`
- Network: `traefik-public` (joined by Frappe backend + workers so they resolve the container by name)
- Frappe reaches it via: `http://notification-relay-notification-relay-1:5000` (internal Docker DNS)
- Firebase project: `cy-erp` with service account `notification-relay-fcm@cy-erp.iam.gserviceaccount.com`
- VAPID keypair: generated locally, public key pasted into `config.json`

## To rebuild / re-deploy

1. SCP `config.example.json` → VM `/opt/notification-relay/config/config.json`, fill in real values.
2. SCP your SA JSON → VM `/opt/notification-relay/config/service-account.json` (chmod 600).
3. SCP `docker-compose.yml` → VM `/opt/notification-relay/docker-compose.yml`.
4. `cd /opt/notification-relay && docker compose up -d`.
5. On first Frappe push attempt, the bench does a handshake with the relay and stores `api_key`/`api_secret` on the `Push Notification Settings` single doctype.

## Gotchas learned the hard way

- **Project entries per Frappe app.** Every Frappe app that sends push instantiates `PushNotification("<app_name>")` with its own name — `frappe`, `gameplan`, `hrms`, `helpdesk`, `crm`, etc. The relay's config needs a matching entry per app or sends fail with `Project <name> not found`. All entries can share the same VAPID + firebase_config; just duplicate the block per app. See `config.example.json`.
- **Pre-existing stale credentials.** If Push Notification Settings was touched before the first real handshake, `api_key`/`api_secret` may contain placeholder values ("Administrator", etc.) that short-circuit the handshake. Clear them once (set both to `None` + save) so the next push attempt triggers a real handshake with the relay.
- **Worker containers are separate venvs.** `caryaar-erpnext` runs Frappe across 5 containers (backend, queue-short, queue-long, scheduler, websocket) that each have their own Python venv. Any app listed in `sites/apps.txt` must be pip-installed in all 5; otherwise the 3 workers restart-loop on import. Either bake the app into the Docker image via `apps.json` (preferred — `/home/sahaib/gitops/apps.json` is the source of truth) or `docker exec ... env/bin/pip install -e apps/<name>` into each worker.

## Verified working

- Frappe ↔ relay handshake: relay callback to `erp.caryaar.com/api/method/frappe.push_notification.auth_webhook` returned matching token, credentials persisted on Push Notification Settings.
- Relay ↔ FCM: smoke-tested with a dummy token — FCM rejected the token (as expected) but authenticated the relay's service account, confirming the send path works end-to-end.

## Not set up (optional)

- `push.caryaar.com` DNS A record → VM IP `35.200.155.219`. Only needed if you want the relay reachable from outside the cluster (e.g. for another self-hosted Frappe site to use the same relay). For erp.caryaar.com alone, internal Docker DNS is enough.
