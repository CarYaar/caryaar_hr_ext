# Goal meter: automatic goal progress and review packs, design

Status: draft for the founder's review, 28-Sep-2026. Plane item DEV-1232.
Builds on the performance program spec (2026-09-26) and what is live: the
nightly adherence engine, the Plane sync (every 15 minutes) and the CY Admin
activity sync (hourly and nightly) in `caryaar_hr_ext.performance`.

## 1. What the founder asked for (28-Sep-2026)

1. "I trust all these goals can be measured in an automated way from CY Admin
   and Plane." Today the syncs feed adherence (work visible per day), not goal
   progress. Goal progress in the ERP is typed by hand, except for a goal
   linked to a Plane module.
2. Plane coverage is every project and every work item, with start date, due
   date, completion and assignee.
3. People will create many small tickets under their own name. Only the items
   tied to a goal count toward that goal. Everything else is activity.
4. An automated report before each review, so founders and managers know the
   numbers before the employee walks in.
5. Live before 01-Nov-2026, when adherence and goals start to count. October
   is the learning month.

Constraints carried over: the ERP is the system of record for goals; Plane's
database is read-only for us; CY Admin sends data through the least-privilege
sync user; nothing here changes how HRMS scores an appraisal.

## 2. How HRMS scores a goal (verified in HRMS v16 source)

- Each Appraisal KRA row's `goal_completion` is the **average of `Goal.progress`**
  over the employee's non-archived goals on that KRA in the cycle
  (`appraisal.py::set_goal_score`).
- `goal_score` = completion x KRA weight / 100; the sum over KRAs is
  `goal_score_percentage`; `total_score` = that / 20, so 0 to 5.
- `Goal.progress` is 0 to 100. Progress 0 = status Pending, 100 = Completed,
  anything between = In Progress (`goal.py::set_status`).

So the meter has one job: keep `Goal.progress` right for every goal that has
a numeric source. HRMS does the rest.

## 3. Decisions

| # | Decision | Default | Why |
|---|---|---|---|
| G1 | Where the meter runs | In the ERP (`caryaar_hr_ext.performance.meter`), nightly at 23:45 IST after the adherence engine, and on demand from a button | Targets, goals, readings and evidence live in one place; the sync user and stamps already exist |
| G2 | How a Plane item is tied to a goal | One Plane **module per Plane-measured goal**, created by us and named after the goal; the goal's `cy_plane_module` holds the module id. An item counts only if it is in that module | Managers move items in on purpose; a flood of small tickets never inflates a goal; no new Plane feature needed |
| G3 | Which Plane items are synced | **All projects, all non-draft items**: id, project, sequence, title, assignee, state group, module, start date, target date, completed at, created at, labels, deleted flag | Founder asked for all of it; the review pack lists items with dates and overdue flags |
| G4 | Progress for a "reach a number" goal | `min(100, value / target x 100)`, value measured **cycle to date** or **for the latest full month**, as the meter says | Simple to explain in a 1:1; matches how the goals were written ("3% by Dec, 5% by Mar" becomes the final target with the Dec number as a check-in) |
| G5 | Progress for a "keep a standard" goal | Share of **elapsed months** in the cycle that met the standard (24 h fixes, 99.5% uptime, filings on time, books closed on time) | A standard is met or missed month by month; averaging hides misses |
| G6 | Progress for a Plane-only goal | Weighted completion of the goal's module: completed items / all non-cancelled items; items past their due date and not done are listed as overdue in the pack | Already how `update_goal_progress` works today |
| G7 | Manual goals | Method `Manual`: the manager types progress with an evidence link in a Goal Meter Reading; the pack flags any goal with no reading in the last 30 days | Brand consistency, audits, surveys, filings without a system record |
| G8 | Counting start | Readings are taken from 01-Oct-2026 and shown from day one; **progress is written to Goal only from 01-Nov-2026** (October readings are visible in the pack, marked learning month) | Founder's D9: October is visible, not counted |
| G9 | Review pack cadence and readers | Generated per employee on the **1st and 15th** of each month at 08:00 IST and 3 days before a date entered on the Appraisal (`cy_next_review_on`); emailed to the employee's reporting manager and to Maxson, Joel and Sahaib; also a report page in the ERP | Founder: "before employees come for review" |
| G10 | Two systems disagree on a count | The meter names **one source per metric** (table below) and the pack shows the source; nobody reconciles two numbers in a 1:1 | Draft note on New Customers: "the two counts differ; agree one" |
| G11 | A source has not synced | If the source's `synced_through` stamp is older than the reading date, the reading is **skipped and the last reading stands**, marked stale in the pack; outage never lowers a goal | Same rule as adherence |

## 4. Architecture

Three data feeds, one meter, one pack.

```
Plane (all projects)  --15 min-->  Plane Work Item (ERP)        \
CY Admin per agent    --hourly-->  Work Activity Day (ERP)       >-- nightly meter --> Goal.progress + Goal Meter Reading --> review pack (report + email)
CY Admin company      --nightly--> Company Metric Day (ERP)     /
ERP itself (invoices, attendance, hiring, wiki)  ---- read in place ----/
```

### 4.1 New doctypes (module `caryaar_hr_ext`)

- **Plane Work Item** (name = Plane issue id): project_identifier, sequence_id,
  title (140), assignee (Link Employee, resolved by email like the syncs do),
  assignee_email, state_group (backlog / unstarted / started / completed /
  cancelled), module_id, labels (comma list), start_date, target_date,
  completed_at, created_at, updated_at, is_deleted (Check), synced_at.
  Indexed on assignee, module_id, target_date.
- **Company Metric Day** (name = metric + date): metric (Data), metric_date,
  value (Float), detail (JSON, small), source (CY Admin / ERP), synced_at.
- **Goal Meter** (name = goal): goal (Link Goal, unique), employee (fetched),
  method (Select: Ratio to target / Months meeting standard / Plane module /
  Manual), metric (Select from the catalogue in section 5, blank for Plane and
  Manual), window (Select: Cycle to date / Latest full month), target_value
  (Float), standard_value (Float), unit (Data), direction (Select: Higher is
  better / Lower is better), source_note (Small Text), active (Check).
- **Goal Meter Reading** (name = goal + date): goal, reading_date, value,
  progress (Percent), method, evidence (Small Text, URL or text), stale
  (Check), written_to_goal (Check), computed_at, entered_by (for manual).

`Performance Sync Settings` gains `plane_items_synced_through` and
`company_metrics_synced_through`.

### 4.2 Feeds

**Plane work items (extend `deploy/plane-erp-sync`).** New SQL over the whole
workspace: every non-draft issue with its project identifier, sequence, name,
state group, first assignee email, module (from `module_issues`), labels,
`start_date`, `target_date`, `completed_at`, `created_at`, `updated_at`,
`deleted_at IS NOT NULL` as deleted. Sent every run as an upsert of rows
updated since the last stamp (plus a full pass once a day at 00:30 IST so a
missed run heals). New intake `ingest_work_items(synced_through, items)`
validated by pure rules like the other two intakes. `Plane Module Progress`
stays as it is; the meter reads items, not module totals.

**CY Admin per agent (existing, plus three metrics).** `compute_agent_activity`
adds `followups_due`, `followups_done_on_time` and `leads_statused_48h`
(leads assigned that day that carried a status within 48 hours, written by
the nightly run two days later). Sent through the existing `ingest_activity`;
`Work Activity Day` gains the three columns. Nothing else in the sync changes.

**CY Admin company metrics (new nightly block, 00:25 IST).** One row per
metric per day, sent to a new intake `ingest_company_metrics`. Metrics come
from the catalogue: bookings, first paid customers, returning customers,
partners onboarded (ACTIVE with a first job), partners active (a job in the
last 30 days), turnaround median hours, escalations closed within SLA, ground
leads, ads leads, ads spend (from the Meta insights table), partner-tagged
jobs. Each is a documented SQL in `app/services/performance/company_metrics.py`
with a pure test for its window logic.

**ERP in place.** Revenue and first or returning customers from Sales
Invoice; hiring from Job Applicant and Job Opening; attendance regularised
from unmarked Attendance before the payroll date; handbook acknowledgements;
wiki pages by author; appraisal cycle milestones. These are read by the
meter directly, no feed needed.

### 4.3 The meter (`performance/meter.py`, pure rules in `performance/meter_rules.py`)

Nightly, after the adherence engine:

1. For every active Goal Meter whose goal's cycle is Not Started or In
   Progress and whose employee is Active, compute the value for the reading
   date from the metric's source (section 5). If the source stamp is older
   than the reading date, write a reading marked stale that repeats the last
   value (G11).
2. Compute progress by method (G4 to G6). Round to one decimal.
3. Write a Goal Meter Reading. From 01-Nov-2026 (G8), if the progress differs
   from `Goal.progress` by 0.5 or more, set it through `frappe.get_doc` so
   HRMS runs its own hooks (status, parent, appraisal score), exactly as
   `update_goal_progress` does today.
4. Manual meters are skipped by the job; a manager's reading writes progress
   at once, with the same 01-Nov rule.
5. Every failure is caught per goal and listed in `Performance Sync Settings.last_error`;
   one bad goal never stops the others.

The existing `update_goal_progress` (module completion) is folded into the
meter as the Plane module method, so there is one writer of `Goal.progress`.

### 4.4 The review pack

- **Script Report "Goal Review Pack"** (filters: employee, cycle, as-of date):
  per goal: KRA and weight, goal, target, method, latest value, progress,
  trend (readings at 15-day steps), source, stale or manual flags; for Plane
  goals the items in the module with assignee, start, due, done-on and an
  overdue flag; the adherence summary for the window (from Work Adherence
  Day); items assigned to the person outside any goal module (count only, so
  the "many small tickets" are visible but not counted); manual goals with no
  reading in 30 days.
- **Scheduled send** (`performance/review_pack.py`, 08:00 IST on the 1st and
  15th, and 3 days before `Appraisal.cy_next_review_on` when set): renders the
  report to HTML and emails it to the reporting manager and the three
  founders through the ERP's outgoing email. One email per employee, subject
  "Review pack: <name>, <date>".
- **On demand**: a "Review pack" button on the Appraisal form opens the report
  for that employee.

### 4.5 Setup for the current cycle

- Create one Plane module per Plane-measured goal (script through the Plane
  API, in the person's department project), set `cy_plane_module` on the goal.
  About 12 goals.
- Load Goal Meter rows for all goals in the cycle from a fixture generated
  from the catalogue (section 5). Founders review the targets in the ERP
  Goal Meter list; a target change there is the only place a target lives.
- Manual goals get a Goal Meter with method Manual so the pack lists them.

## 5. Metric catalogue (one source per metric)

| Metric key | Definition | Source | Feeds goals |
|---|---|---|---|
| leads_assigned | leads assigned to the agent in the window | Work Activity Day | conversion (denominator), CRM completeness |
| bookings_within_7d | of those leads, bookings created within 7 days of assignment | CY Admin per agent (new detail on `bookings_credited`) | Lead to booking conversion (Anagha, Janhavi, Hiren) |
| followups_due / followups_done_on_time | follow-ups due in the window and those done by their time | CY Admin per agent (new) | Customer follow-ups on time |
| leads_statused_48h | leads given a status within 48 h of assignment | CY Admin per agent (new) | CRM data completeness |
| job_updates_sent_on_time | customer status updates sent for the agent's jobs at each stage | CY Admin per agent (new, phase 2) | Job updates to customers on time |
| ratings_asked / ratings_received | feedback asked and received per handled job | Manual until the rating capture is fixed (18 of 19 ratings are "1" today) | Customer satisfaction |
| partners_onboarded | Service Partners moved to ACTIVE with a first job | Company Metric Day (CY Admin) | Partners onboarded (Hiren, Joel) |
| partners_active_30d | partners with a job in the last 30 days | Company Metric Day | Partner retention (Zoeb), partners managed |
| turnaround_median_h | median intake to ready hours for jobs completed in the window | Company Metric Day (WMS job cards) | Turnaround (Hiren, Joel) |
| escalations_closed_sla | escalations closed within SLA / opened | Company Metric Day (CY Admin tickets) | Disputes and escalations |
| first_paid_customers | customers whose first paid invoice falls in the window | ERP Sales Invoice (customer's earliest paid invoice) | New customers (Sahaib), first paid job |
| returning_paid_customers | customers with a second or later paid invoice in the window | ERP Sales Invoice | Customers managed (Joel), second paid job |
| revenue_net | net Sales Invoice value in the window against the monthly plan | ERP Sales Invoice; plan in the Goal Meter target | Company Revenue (all founders) |
| contribution_margin | revenue minus partner payouts minus direct costs, monthly, sign | ERP (definition to be fixed with Shubham; until then Manual) | Company Profitability (all founders) |
| ground_leads | leads with channel WALK_IN or tag ground | Company Metric Day | Kaushik ground leads |
| ads_leads / ads_spend | Meta leads and spend in the window | Company Metric Day (Meta insights) | Cost per lead |
| partner_jobs_revenue | invoices on jobs tagged to a partner | ERP Sales Invoice + CY Admin job tag | Revenue from partnerships (Zoeb) |
| partners_signed / partner_first_job_30d | signed partners; first job within 30 days | Plane module items (signed) + Company Metric Day | Partnerships signed, activation |
| incidents_fixed_24h | Plane items labelled incident with completed_at within 24 h of created_at | Plane Work Item | Production reliability (Shiwans) |
| release_bugs_14d | Plane items labelled bug created within 14 days after a release item | Plane Work Item | Release quality |
| support_on_time | support module items done by target date | Plane Work Item | Support to operations |
| module_completion | done / non-cancelled items in the goal's module | Plane Work Item | every Plane-only goal (sprint work, calendar, ATL, founders' office, foundations, learning, docs) |
| wiki_pages_by_author | Wiki Page created or updated by the person | ERP | Documentation |
| hiring_days_to_fill | Job Opening opened to Job Applicant accepted | ERP | Hiring turnaround |
| unmarked_before_payroll | unmarked attendance days on the payroll cut-off date | ERP | Attendance and payroll accuracy |
| handbook_acks | employees with the v1.1 acknowledgement | ERP (Employee custom field) | Policy compliance |
| books_closed_on_time | month closed by the agreed working day | Manual with evidence until a Period Closing Voucher is used | Books closed |
| payables_receivables_on_time | invoices paid or collected by due date | ERP Purchase and Sales Invoice | Payables and receivables |
| gst_tds_on_time | returns filed by statutory date | Manual with evidence | GST and TDS |
| payouts_reconciled | partner payouts matched to jobs and settlements | Company Metric Day (CY Admin remittances) | Payout reconciliation |
| mis_on_time | MIS delivered by the agreed day | Plane module item per month | MIS reports |

Phase 1 (by 15-Oct): Plane Work Items, Goal Meter and Readings, Plane and
per-agent CY Admin metrics, review pack v1 (report and email).
Phase 2 (by 01-Nov): company metrics, ERP finance and HR metrics, Meta
spend, the Appraisal button, and the 01-Nov switch that starts writing
progress.

## 6. What is not in scope

- Changing HRMS scoring, templates or weights.
- Writing anything to Plane except the modules created at setup.
- Uptime measurement (no monitor yet); "Technology Maintained" uses
  incidents_fixed_24h and the handover module until a monitor exists.
- Fixing the customer rating capture (separate CY Admin bug; satisfaction
  stays manual until then).

## 7. Testing and rollout

- Pure rules (`meter_rules.py`): progress by method, windows in IST, stale
  handling, the 01-Nov gate, overdue flags; table-driven tests.
- Intake validation for work items and company metrics: rejects bad rows,
  keeps the stamp rule (contiguous advance only).
- Integration on staging (frappe-staging clone): load the fixture, run the
  meter for a day, check three goals by hand (one per method), render one
  pack, send it to a test mailbox.
- Rollout: deploy the ERP app (derived image, migrate), deploy caryaar-api
  with the new metrics dormant behind `PERFORMANCE_SYNC_ENABLED` (already
  on), start the Plane sync's new query, load the fixture, watch two nightly
  runs, then the founders confirm targets in the Goal Meter list.

## Review fix pass, 28-Sep-2026

The whole-branch review (fresh Opus reviewer) found three critical and fourteen important defects; all were fixed on the branch before Task 10. The design changes that matter to readers of this spec:

- **Archived is not deleted.** Plane only archives completed or cancelled items, so an archived item is finished work that still counts. The mirror carries `is_archived` apart from `is_deleted`; the meter and the pack drop deleted items only.
- **An item can be in several modules.** The mirror carries `module_ids` (every membership, oldest first) and the meter matches on it, so an item added to a goal's module later still counts.
- **Intake items** arrive in Plane's `triage` state group and are mirrored as backlog.
- **Manual goals (G7).** A reading entered by hand (the Goal Meter Reading form, or `meter.write_manual_reading`) reaches `Goal.progress` through the reading's `on_update` under the same 01-Nov gate; a reading entered in October is applied on the first night of November. `write_manual_reading` requires evidence, refuses a reading for one's own goal, and checks write permission on the Goal, so User Permissions apply.
- **Review pack (G9, G10).** Recipients are the settings list plus the manager, backfilled once after migrate; a pack with nobody to send to is logged, not counted. Adherence counts judged working days only. Rows show the source and metric, the target (with standard and unit for Months goals), the latest reading, the percentage HRMS averages ("in appraisal"), a fortnightly trend, and each item's assignee, start and due dates in DD-MMM-YYYY. The report is HR Manager and System Manager only.
- **The person's own view (founder, 28-Sep).** `caryaar_hr_ext.performance.api.person_goals(email)` returns one person's goals in each live cycle with how each is measured, the latest reading, the items counted and the next review date, for CY Admin's home screen from 01-Oct (readings shown, the appraisal percentage from 01-Nov). The Employee role reads their own Goal Meter and readings in the ERP.

## Rollout record

**Staging, 28-Sep-2026 22:11 to 22:16 IST (frappe-staging, fresh prod backup 20260928_221100):** restore and `migrate` clean (after_migrate created 62 Goal Meters: 37 Manual, 13 Plane module, 10 Ratio to target, 2 Months meeting standard; recipients backfilled). All 23 Frappe integration tests passed. `run_meter(as_of=2026-10-02)`: 25 readings (all stale, no sync stamps on staging), 13 Plane-module goals listed as unmatched (modules not created yet), 37 Manual meters without readings. `send_pack` for Anagha queued to Joel and the three founders. Two live-data findings fixed the same night: the previous cycle (Mar to Sep 2026) is still "Not Started" in HRMS, so cycles are now judged by their dates (`meter_rules.cycle_is_live`); and a reading with no value was stored as 0.0 (Frappe's Float), so no reading row is written until there is a value.
