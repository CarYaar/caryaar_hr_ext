frappe.query_reports["Activity Summary"] = {
  filters: [
    { fieldname: "period", label: __("Period"), fieldtype: "Select", reqd: 1, default: "This month",
      options: ["This month", "Last month", "Last 7 days", "Last 30 days", "Custom"] },
    { fieldname: "from_date", label: __("From"), fieldtype: "Date", depends_on: "eval:doc.period == 'Custom'" },
    { fieldname: "to_date", label: __("To"), fieldtype: "Date", depends_on: "eval:doc.period == 'Custom'" },
    { fieldname: "group_by", label: __("Group by"), fieldtype: "Select", reqd: 1, default: "Person",
      options: ["Person", "Department", "Role"] },
    { fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
    { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
  ],
};
