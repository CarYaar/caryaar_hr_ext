import frappe

no_cache = 1


def get_context(context):
    serial = (frappe.form_dict.get("serial") or "").strip()[:32]
    context.found = False
    context.serial = serial
    if serial:
        emp = frappe.db.get_value(
            "Employee",
            {"cy_card_serial": serial},
            ["employee_name", "designation", "image", "status",
             "cy_card_status", "cy_card_valid_through"],
            as_dict=True,
        )
        if emp:
            context.found = True
            context.person_name = emp.employee_name
            context.designation = emp.designation
            # public files only; private employee photos never leak
            context.photo = emp.image if (emp.image or "").startswith("/files/") else None
            context.card_ok = emp.status == "Active" and emp.cy_card_status == "Active"
            context.card_status = emp.cy_card_status
            context.valid_through = emp.cy_card_valid_through
    return context
