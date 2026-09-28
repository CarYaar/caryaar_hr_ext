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

# ─── Identity: public verify routes + jinja QR helper ────────────────────
# /v/<serial> and /c/<certno> are the guest verification pages behind the
# QR printed on every identity card and internship certificate. They are
# proxied publicly via verify.caryaar.com (allowlist Cloudflare worker).
website_route_rules = [
    {"from_route": "/v/<serial>", "to_route": "verify_card"},
    {"from_route": "/c/<certno>", "to_route": "verify_certificate"},
]

jinja = {
    "methods": [
        "caryaar_hr_ext.utils.qr.qr_data_uri",
        "caryaar_hr_ext.utils.photo.photo_data_uri",
    ],
}

# Brand fonts for wkhtmltopdf print formats (see utils/fonts.py), then the WFH
# approval setup: created only where missing, so HR's edits survive every deploy
# (see performance/setup.py; the workflow, notifications and docperms are not
# fixtures on purpose).
after_migrate = [
    "caryaar_hr_ext.utils.fonts.install_fonts",
    "caryaar_hr_ext.performance.setup.ensure_wfh_approval_setup",
    "caryaar_hr_ext.performance.setup.ensure_goal_meters",
]

# Typing "auto" into the card serial field generates 2026-0001-K7QX
# style serials (sequential + random suffix, founder call 28-Aug).
doc_events = {
    "Employee": {"validate": "caryaar_hr_ext.utils.serial.ensure_card_serial"},
}

# ─── Fixtures ────────────────────────────────────────────────────────────
# Identity card fields (Employee), the WFH approval fields and workflow
# states/actions (live since 26-Sep-2026) and the performance program fields
# (Goal, Appraisal) ship as fixtures so
# `bench migrate` recreates them on any site this app is installed on.
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["fieldname", "like", "cy_%"],
                    ["dt", "in", ["Employee", "Attendance Request", "Goal", "Appraisal"]]],
    },
    {"dt": "Role", "filters": [["role_name", "in", ["Identity Manager", "Performance Sync"]]]},
    {
        "dt": "Print Format",
        "filters": [
            ["name", "in",
             ["CY Card Front", "CY Card Back", "CY Internship Certificate"]],
        ],
    },
    {"dt": "Workflow State", "filters": [["name", "in", ["Draft", "Cancelled"]]]},
    {"dt": "Workflow Action Master", "filters": [["name", "in", ["Send for Approval", "Cancel"]]]},
    {"dt": "Dashboard Chart", "filters": [["module", "=", "Caryaar Hr Ext"]]},
    {"dt": "Number Card", "filters": [["module", "=", "Caryaar Hr Ext"]]},
    {"dt": "Dashboard", "filters": [["module", "=", "Caryaar Hr Ext"]]},
    # "Weekly Off" reason and bulk edit on Attendance / Attendance Request.
    # First made by editing stock HRMS files on the live site; an HRMS upgrade
    # restores those files, so they live here as customisations instead.
    {
        "dt": "Property Setter",
        "filters": [
            ["name", "in",
             ["Attendance Request-main-allow_bulk_edit", "Attendance Request-reason-options",
              "Attendance-main-allow_bulk_edit"]],
        ],
    },
]

# ─── Performance engine ──────────────────────────────────────────────────
# 23:30 IST (site time zone Asia/Kolkata): adherence for today and the three
# days before (late syncs), then goal progress from Plane modules, then
# rating categories.
scheduler_events = {
    "cron": {
        "30 23 * * *": ["caryaar_hr_ext.performance.engine.run_nightly"],
        "0 8 * * *": ["caryaar_hr_ext.performance.review_pack.send_scheduled_packs"],
    },
}

from . import api  # noqa: E402, F401 — registers the whitelisted method

# If you want to add more tiles later, extend `api.get_custom_tiles()` to
# return a list of dicts. The JS loops over every tile returned.
