"""Custom tile injection for the HRMS PWA.

`get_custom_tiles` exposes the list of tiles the client-side JS appends.
`inject_hrms_script` is an `after_request` hook that rewrites the HTML
response for /hrms to include our tile loader — HRMS's www template
doesn't honor `app_include_js`, so response rewriting is the only
forward-compatible way to get a script tag into the PWA shell.
"""

import frappe


SCRIPT_TAG = (
    b'<script src="/assets/caryaar_hr_ext/js/hrms_handbook_tile.js" '
    b'defer></script>'
)


def inject_hrms_script(response, request):
    """Append our tile loader to HRMS PWA responses."""
    try:
        path = (getattr(request, "path", "") or "").rstrip("/")
        if path != "/hrms" and not path.startswith("/hrms/"):
            return
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return
        data = response.get_data()
        if b"caryaar_hr_ext" in data:  # already injected
            return
        if b"</head>" not in data:
            return
        response.set_data(data.replace(b"</head>", SCRIPT_TAG + b"</head>", 1))
    except Exception:  # noqa: BLE001 — never break the response
        frappe.log_error(title="caryaar_hr_ext:inject_hrms_script")


@frappe.whitelist(allow_guest=False)
def get_custom_tiles() -> list[dict]:
    """Tiles to append to the Home Quick Links in HRMS PWA.

    Each tile:
      label: string shown in the UI
      icon:  lucide icon name (optional — JS falls back to a default)
      route: URL the tile navigates to (can be relative or absolute)
      external: true if this should open in a new tab
    """
    return [
        {
            "label": "Employee Handbook",
            "icon": "book-open",
            "route": "/handbook",
            "external": True,
        },
    ]
