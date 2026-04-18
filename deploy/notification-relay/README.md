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

## Not set up (optional)

- `push.caryaar.com` DNS A record → VM IP `35.200.155.219`. Only needed if you want the relay reachable from outside the cluster (e.g. for another self-hosted Frappe site to use the same relay). For erp.caryaar.com alone, internal Docker DNS is enough.
