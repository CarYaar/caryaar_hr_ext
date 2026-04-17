from . import __version__ as app_version  # noqa: F401

app_name = "caryaar_hr_ext"
app_title = "CarYaar HR Extensions"
app_publisher = "CarYaar"
app_description = "Small customizations on top of frappe/hrms — handbook link in the PWA, etc."
app_email = "sahaib.singh@caryaar.com"
app_license = "MIT"

# ─── Asset injection ──────────────────────────────────────────────────────
# The HRMS PWA (/hrms/*) ships as a Vue SPA loaded from a single HTML shell
# rendered by `hrms/www/hrms.py`. That template doesn't extend Frappe's
# standard base and therefore does NOT pick up `app_include_js` /
# `web_include_js` hooks. To inject our tile script we use the
# `after_request` hook to rewrite the HTML response before it's sent.
#
# We still register app_include_js as a fallback so the asset loads on any
# Desk page (e.g. if someone opens /app), but it's not the mechanism that
# gets it into the PWA — that's done by the HTML rewrite below.
app_include_js = [
    "/assets/caryaar_hr_ext/js/hrms_handbook_tile.js",
]

# ─── HRMS HTML rewrite ────────────────────────────────────────────────────
# Injects a <script> tag for our tile loader into the HRMS PWA index
# response. Runs on every request but only rewrites when the path matches
# /hrms or /hrms/* AND the response is HTML.
after_request = ["caryaar_hr_ext.api.inject_hrms_script"]

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
