"""Whitelisted API returning the list of custom tiles to inject into the
HRMS PWA Home Quick Links.

Starts with just the Employee Handbook. Add more tiles here later (or
point it at a doctype) without touching the JS.
"""

import frappe


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
