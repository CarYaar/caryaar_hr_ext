"""Card serial generation: sequential year counter + random suffix.

Founder call (28-Aug-2026): serials are enumerable on the public verify
page, so they carry a 4-char random suffix (2026-0001-K7QX). Typing
"auto" (or "new" / "generate") into the card serial field replaces it
with the next generated serial on save; anything else is kept verbatim.
The alphabet skips 0/O/1/I/L so serials survive being read out loud.
"""
import secrets

import frappe

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
AUTO_VALUES = {"auto", "new", "generate"}


def ensure_card_serial(doc, method=None):
    if (doc.cy_card_serial or "").strip().lower() in AUTO_VALUES:
        doc.cy_card_serial = generate_serial()
        frappe.msgprint(f"Card serial assigned: {doc.cy_card_serial}", alert=True)


def generate_serial() -> str:
    year = frappe.utils.nowdate()[:4]
    for _ in range(20):
        seq = (frappe.db.count("Employee", {"cy_card_serial": ["like", f"{year}-%"]}) or 0) + 1
        suffix = "".join(secrets.choice(ALPHABET) for _ in range(4))
        serial = f"{year}-{seq:04d}-{suffix}"
        if not frappe.db.exists("Employee", {"cy_card_serial": serial}):
            return serial
    frappe.throw("Could not generate a unique card serial, save again.")
