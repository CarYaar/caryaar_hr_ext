frappe.query_reports["Activity Summary"] = {
  filters: [
    { fieldname: "from_date", label: __("From"), fieldtype: "Date", reqd: 1,
      default: frappe.datetime.month_start() },
    { fieldname: "to_date", label: __("To"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
    { fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
    { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
  ],
};
