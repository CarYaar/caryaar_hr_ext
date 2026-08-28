import frappe

no_cache = 1


def get_context(context):
    certno = (frappe.form_dict.get("certno") or "").strip()[:40]
    context.found = False
    context.certno = certno
    if certno and frappe.db.exists("Internship Certificate", certno):
        doc = frappe.db.get_value(
            "Internship Certificate", certno,
            ["intern_name", "role_title", "start_date", "end_date",
             "issued_on", "docstatus"],
            as_dict=True,
        )
        if doc and doc.docstatus in (1, 2):  # drafts stay invisible
            context.found = True
            context.cert = doc
            context.revoked = doc.docstatus == 2
    return context
