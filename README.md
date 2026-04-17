# CarYaar HR Extensions

Small customizations on top of [frappe/hrms](https://github.com/frappe/hrms) that would otherwise need forking the upstream app.

## What it does (v0.1.0)

- **Handbook tile on HRMS PWA Home** — injects an "Employee Handbook" quick-link tile into the mobile HRMS app at `/hrms/` pointing to `/handbook`. Survives every `bench update --hrms` because it lives in this separate app, not in HRMS source.

## How it works

The HRMS PWA's Home screen hardcodes its 6 Quick Links (Request Attendance, Request a Shift, Request Leave, Claim an Expense, Request an Advance, View Salary Slips) directly in the Vue source — there's no doctype or config to edit. This app solves that by:

1. Registering `/assets/caryaar_hr_ext/js/hrms_handbook_tile.js` via `app_include_js` so Frappe auto-loads it on every page (including `/hrms/*`).
2. The JS bails on non-HRMS routes, then watches the DOM for the Quick Links container, finds an existing tile, clones its look, replaces the label + route, and appends.
3. Tile config is returned by `caryaar_hr_ext.api.get_custom_tiles` — add more tiles there without touching the JS.

Everything is idempotent — clones with a sentinel attribute so repeat mutations don't duplicate.

## Installation

### On Frappe Cloud

1. **Private Apps** → **Add App** → GitHub repo URL (once this is pushed to `CarYaar/caryaar_hr_ext`)
2. Install on your `erp.caryaar.com` site
3. Frappe Cloud handles `bench restart` and cache clear automatically

### On a self-hosted bench

```bash
cd ~/frappe-bench
bench get-app https://github.com/CarYaar/caryaar_hr_ext.git
bench --site erp.caryaar.com install-app caryaar_hr_ext
bench --site erp.caryaar.com clear-cache
bench restart
```

## Verifying

After install, open `https://erp.caryaar.com/hrms/` on mobile or desktop. You should see **Employee Handbook** as the 7th tile in Quick Links, below View Salary Slips. Tapping it opens `/handbook` in a new tab.

If it doesn't appear:

1. Hard-refresh the PWA (Cmd+Shift+R / pull-to-refresh on mobile)
2. Open devtools → Network → filter for `hrms_handbook_tile.js` — should return 200
3. Console → look for `"[caryaar_hr_ext]"` logs (not present by default, but any errors would show)

## Adding more tiles

Edit `caryaar_hr_ext/api.py` — the `get_custom_tiles` function returns a list of dicts:

```python
return [
    {
        "label": "Employee Handbook",
        "icon": "book-open",
        "route": "/handbook",
        "external": True,
    },
    {
        "label": "IT Help Desk",
        "route": "/support",
        "external": True,
    },
]
```

`bench restart` to pick up the Python change. JS is cached 5 min client-side; tiles appear on next page reload after the cache expires (or change the TTL in `hrms_handbook_tile.js`).

## License

MIT
