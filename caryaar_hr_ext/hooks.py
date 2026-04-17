from . import __version__ as app_version  # noqa: F401

app_name = "caryaar_hr_ext"
app_title = "CarYaar HR Extensions"
app_publisher = "CarYaar"
app_description = "Small customizations on top of frappe/hrms — handbook link in the PWA, etc."
app_email = "sahaib.singh@caryaar.com"
app_license = "MIT"

# ─── Asset injection ──────────────────────────────────────────────────────
# The HRMS PWA (/hrms/*) is a Vue SPA loaded from a single HTML shell that
# Frappe serves via the `www/hrms` page controller. The quick-access tiles
# on the Home view are hardcoded in the HRMS frontend build, so we can't
# modify them via any doctype. Instead we inject a small JS patch that
# waits for the Quick Links section to mount, then appends our custom tile.
#
# Using `app_include_js` so the asset is bundled into Frappe's standard
# website JS bundle — this is loaded on every HRMS PWA route without us
# having to override the HRMS Vue source or rebuild the PWA bundle.
#
# `web_include_js` would also work but only runs on portal pages; the PWA
# is considered a "desk app" for asset-loading purposes, so app_include_js
# is the correct hook. Both are kept here so the script survives either
# way HRMS chooses to serve its shell across upgrades.
app_include_js = [
    "/assets/caryaar_hr_ext/js/hrms_handbook_tile.js",
]
web_include_js = [
    "/assets/caryaar_hr_ext/js/hrms_handbook_tile.js",
]

# ─── Handbook config ─────────────────────────────────────────────────────
# Exposed as a whitelisted server method so the JS can fetch the current
# handbook route + label without hardcoding it. Lets us rename the
# handbook or point it elsewhere without republishing the app.
#
# Also lets future tiles be added by dropping rows in a Singles doctype
# (not built yet — starting with just the handbook).

from . import api  # noqa: E402, F401 — registers the whitelisted method

# If you want to add more tiles later, extend `api.get_custom_tiles()` to
# return a list of dicts. The JS loops over every tile returned.
