frappe.query_reports["Rating Distribution"] = {
  filters: [
    { fieldname: "appraisal_cycle", label: __("Appraisal cycle"), fieldtype: "Link",
      options: "Appraisal Cycle", reqd: 1 },
  ],
};
