// "Record reading" on the Goal form, for goals measured by a manual reading (Goal Meter method Manual).
//
// Founder, 01-Oct-2026: the review pack email had no way to open the ERP and record the reading. The pack
// now links each Manual goal to /app/goal/<goal>?record_reading=1, which opens this dialog once.
// The dialog saves through caryaar_hr_ext.performance.meter.write_manual_reading, the one path that
// enforces the rules: evidence is required, nobody records a reading for their own goal, and only HR
// (HR Manager, HR User) or a System Manager may write one. A raw Goal Meter Reading form skips the first
// two, so the button never points there.
(function () {
	const WRITERS = ["HR Manager", "HR User", "System Manager"];
	const METHOD = "caryaar_hr_ext.performance.meter.write_manual_reading";

	function open_dialog(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Record reading: {0}", [frm.doc.goal_name || frm.doc.name]),
			fields: [
				{
					fieldname: "progress",
					fieldtype: "Percent",
					label: __("Progress"),
					reqd: 1,
					description: __("0 to 100, as of today. A second reading today replaces the first."),
				},
				{
					fieldname: "evidence",
					fieldtype: "Small Text",
					label: __("Evidence"),
					reqd: 1,
					description: __("A link, or a note on what you checked."),
				},
			],
			primary_action_label: __("Save reading"),
			primary_action(values) {
				d.disable_primary_action();
				// callback/always, not .then/.finally: frappe.call hands back a jQuery promise. A refusal (own
				// goal, no evidence, no role) arrives as the server's own message; the dialog stays open to fix it.
				frappe.call({
					method: METHOD,
					type: "POST",
					args: { goal: frm.doc.name, progress: values.progress, evidence: values.evidence },
					callback(r) {
						d.hide();
						const written = r && r.message && r.message.written_to_goal;
						frappe.show_alert({
							message: written
								? __("Reading saved and written to the goal's progress.")
								: __("Reading saved. It is shown in the review pack; the appraisal percentage is written from 01-Nov-2026."),
							indicator: "green",
						});
						frm.reload_doc();
					},
					always() {
						d.enable_primary_action();
					},
				});
			},
		});
		d.show();
	}

	function wants_dialog_from_link() {
		try {
			return new URLSearchParams(window.location.search).get("record_reading") === "1";
		} catch (e) {
			return false;
		}
	}

	function forget_link_flag() {
		try {
			const url = new URL(window.location.href);
			url.searchParams.delete("record_reading");
			window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
		} catch (e) {
			/* the dialog still opened; the flag only matters on a reload */
		}
	}

	frappe.ui.form.on("Goal", {
		refresh(frm) {
			if (frm.is_new()) return;
			const from_link = wants_dialog_from_link();
			frappe.db.get_value("Goal Meter", frm.doc.name, ["method", "active"]).then((r) => {
				const meter = (r && r.message) || {};
				if (meter.method !== "Manual" || !meter.active) {
					if (from_link) {
						forget_link_flag();
						frappe.msgprint(__("This goal is measured automatically, so it needs no manual reading."));
					}
					return;
				}
				if (!frappe.user.has_role(WRITERS)) {
					if (from_link) {
						forget_link_flag();
						frappe.msgprint(
							__("Only HR or a System Manager can record a reading for this goal. Please ask HR to record it.")
						);
					}
					return;
				}
				frm.add_custom_button(__("Record reading"), () => open_dialog(frm));
				if (from_link) {
					forget_link_flag();
					open_dialog(frm);
				}
			});
		},
	});
})();
