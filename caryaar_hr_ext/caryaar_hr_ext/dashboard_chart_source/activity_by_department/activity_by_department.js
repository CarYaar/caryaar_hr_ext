frappe.dashboards.chart_sources["Activity by department"] = {
  method: "caryaar_hr_ext.caryaar_hr_ext.dashboard_chart_source.activity_by_department.activity_by_department.get",
  filters: [
    { fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
    { fieldname: "period", label: __("Period"), fieldtype: "Select", default: "This month",
      options: ["This month", "Last month", "Last 7 days", "Last 30 days"] },
  ],
};
