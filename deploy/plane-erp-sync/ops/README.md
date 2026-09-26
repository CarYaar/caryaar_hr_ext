# Plane ops scripts

Run from a machine with IAP access to the Plane VM. Each script executes on the VM,
reads the `cy-automation` Plane API token from `/opt/plane-chat-app/plane_token`
(never printed) and calls Plane's public API through the `plane-app-proxy` container.

## plane_membership_sync.sh

Idempotent. Puts each employee into their department's Plane project (plus their
manager), and sets the leads of the three projects created on 26-Sep-2026
(WR = Hiren, PARTNER = Zoeb, HR = Reema). People who have not accepted their
workspace invite are listed under "WAITING FOR ACCEPT" and picked up on the next run.
It also reports whether "HR and Admin" is private and whether a departed member is
still in the workspace; both of those can only be fixed in Plane's UI (the v1 API
has no project privacy field and no workspace member removal).

```bash
gcloud compute ssh caryaar-plane --zone=asia-south1-a --project=caryaar-api-dev \
  --tunnel-through-iap --command "bash -s" < deploy/plane-erp-sync/ops/plane_membership_sync.sh
```

Edit `MAP` in the script when people join, leave or move department.

Plane v1.3.1 traps found while building this:
- Creating a project with a `project_lead` whose workspace role is Member returns 400
  after the project row is created, leaving it with no states. Create without a lead,
  then add the member (role 15) and PATCH `project_lead`.
- Project names cannot contain `&`.
- Public API invites are saved without a token and send no email; use the UI.
