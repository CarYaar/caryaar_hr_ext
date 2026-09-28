frappe.query_reports["Goal Review Pack"] = {
  filters: [
    { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee", reqd: 1 },
    { fieldname: "appraisal_cycle", label: __("Appraisal cycle"), fieldtype: "Link", options: "Appraisal Cycle", reqd: 1,
      default: "Oct 2026 - Mar 2027" },
    { fieldname: "as_of", label: __("As of"), fieldtype: "Date", default: frappe.datetime.get_today() },
  ],
};
