// The Activity board: one period filter feeds the six tiles, one chart per department and the grouped
// table. Everything comes from caryaar_hr_ext.performance.api.activity_board, the same rules the
// Activity Summary report and the dashboard use, so the numbers agree to the digit.
frappe.pages["activity-board"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Activity board"), single_column: true });
  const PERIODS = ["This month", "Last month", "Last 7 days", "Last 30 days", "Custom"];
  const f = {};
  f.period = page.add_field({ fieldname: "period", label: __("Period"), fieldtype: "Select", options: PERIODS, default: "This month",
    change: () => { toggleDates(); load(); } });
  f.from_date = page.add_field({ fieldname: "from_date", label: __("From"), fieldtype: "Date", change: load });
  f.to_date = page.add_field({ fieldname: "to_date", label: __("To"), fieldtype: "Date", change: load });
  f.department = page.add_field({ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department", change: load });
  f.group_by = page.add_field({ fieldname: "group_by", label: __("Table by"), fieldtype: "Select", options: ["Department", "Role", "Person"],
    default: "Department", change: load });

  $(`<style>
    .cy-board { padding: 8px 0 32px; }
    .cy-board .cy-range { margin: 0 0 12px; }
    .cy-board .cy-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-bottom: 20px; }
    .cy-board .cy-tile { border: 1px solid var(--border-color); border-radius: var(--border-radius-md); background: var(--card-bg); padding: 14px 16px; }
    .cy-board .cy-tile span { color: var(--text-muted); font-size: var(--text-sm); }
    .cy-board .cy-tile b { display: block; font-size: 28px; font-weight: 600; margin-top: 4px; font-variant-numeric: tabular-nums; }
    .cy-board .cy-charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .cy-board .cy-chart { border: 1px solid var(--border-color); border-radius: var(--border-radius-md); background: var(--card-bg); padding: 12px 16px 4px; }
    .cy-board .cy-chart h5 { margin: 0 0 4px; font-weight: 600; }
    .cy-board table.cy-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); background: var(--card-bg); }
    .cy-board table.cy-table th, .cy-board table.cy-table td { border-bottom: 1px solid var(--border-color); padding: 6px 10px; text-align: right; white-space: nowrap; }
    .cy-board table.cy-table th:first-child, .cy-board table.cy-table td:first-child { text-align: left; }
    .cy-board table.cy-table tr:last-child td { font-weight: 600; }
    .cy-board .cy-table-wrap { overflow-x: auto; border: 1px solid var(--border-color); border-radius: var(--border-radius-md); }
  </style>`).appendTo(wrapper);
  const $body = $('<div class="cy-board"></div>').appendTo(page.body);

  function toggleDates() {
    const custom = f.period.get_value() === "Custom";
    f.from_date.$wrapper.toggle(custom);
    f.to_date.$wrapper.toggle(custom);
  }
  function args() {
    return { period: f.period.get_value(), from_date: f.from_date.get_value(), to_date: f.to_date.get_value(),
             department: f.department.get_value(), group_by: f.group_by.get_value() };
  }
  let latest = 0;
  function load() {
    const a = args();
    if (a.period === "Custom" && !(a.from_date && a.to_date)) return;
    const call = ++latest;
    frappe.xcall("caryaar_hr_ext.performance.api.activity_board", a).then((data) => { if (call === latest) render(data); });
  }
  const esc = frappe.utils.escape_html;
  function render(data) {
    $body.empty();
    $body.append(`<p class="text-muted cy-range">${esc(data.from_date)} to ${esc(data.to_date)}</p>`);
    const $tiles = $('<div class="cy-tiles"></div>').appendTo($body);
    data.cards.forEach((c) => $tiles.append(`<div class="cy-tile"><span>${esc(__(c.label))}</span><b>${format_number(c.value, null, 0)}</b></div>`));
    const $charts = $('<div class="cy-charts"></div>').appendTo($body);
    if (!data.charts.length) $charts.append(`<p class="text-muted">${__("No activity in this period.")}</p>`);
    data.charts.forEach((ch) => {
      const $card = $('<div class="cy-chart"><h5></h5><div class="cy-chart-body"></div></div>').appendTo($charts);
      $card.find("h5").text(ch.department);
      new frappe.Chart($card.find(".cy-chart-body")[0], {
        data: { labels: ch.labels, datasets: ch.datasets }, type: "bar", height: 220, colors: ["#6D28D9"],
        axisOptions: { xAxisMode: "tick", xIsSeries: 0 }, barOptions: { spaceRatio: 0.5 },
      });
    });
    if (data.columns.length) {
      const head = data.columns.map((c) => `<th>${esc(c.label)}</th>`).join("");
      const rows = data.rows.map((r) => `<tr>${data.columns.map((c, i) => `<td>${i === 0 ? esc(r[c.fieldname] || "") : format_number(r[c.fieldname] || 0, null, 0)}</td>`).join("")}</tr>`).join("");
      $body.append(`<div class="cy-table-wrap"><table class="cy-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`);
    }
  }
  toggleDates();
  load();
};
