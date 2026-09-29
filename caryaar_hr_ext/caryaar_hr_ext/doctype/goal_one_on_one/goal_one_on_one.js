// The employee acknowledges from their own login; the server rule (performance.api.acknowledge_goals)
// stays the authority, this only shows the button to the right person. HR and the manager can refill
// the goals table from the cycle while the record is not yet acknowledged.
frappe.ui.form.on("Goal One on One", {
  refresh(frm) {
    if (frm.is_new()) return;
    const mine = frm.doc.employee_user && frm.doc.employee_user === frappe.session.user;
    if (!frm.doc.employee_acknowledged && mine) {
      frm.add_custom_button(__("Acknowledge my goals"), () => {
        frappe.confirm(__("You confirm these goals were discussed with you and you accept them for this cycle."), () => {
          frappe.call({
            method: "caryaar_hr_ext.performance.api.acknowledge_goals",
            args: { name: frm.doc.name },
            callback: () => {
              frappe.show_alert({ message: __("Goals acknowledged"), indicator: "green" });
              frm.reload_doc();
            },
          });
        });
      }).addClass("btn-primary");
    }
    if (!frm.doc.employee_acknowledged && frm.perm[0] && frm.perm[0].write && !mine) {
      frm.add_custom_button(__("Fill goals from the cycle"), () => {
        frappe.call({ method: "fill_goals", doc: frm.doc, callback: () => frm.reload_doc() });
      });
    }
    if (frm.doc.employee_acknowledged) {
      frm.dashboard.set_headline(__("Acknowledged on {0}", [frappe.datetime.str_to_user(frm.doc.acknowledged_on)]));
    }
  },
});
