# Performance, Plane and WFH program: design

- **Date:** 26-Sep-2026
- **Owner:** Sahaib (tech). Policy owners: Maxson (CEO, handbook author), Joel (COO, handbook approver), Reema (Director HR and Admin).
- **Status:** DRAFT for founder review. Nothing in production has been changed.
- **Repo:** `caryaar_hr_ext` (ERP customisations). The Plane-side sync kit lives here too, under `deploy/plane-erp-sync/`, mirroring `deploy/notification-relay/`.

## 1. Why

On 26-Sep Joel asked in the founders group who approved Kaushik's weekly WFH day, and proposed stopping WFH "except special cases where deliverables of working from home are tracked (like Shiwans now)". That rule is the right one. The problem is that nothing in the company makes "tracked" true by default:

- **WFH requests have the wrong approvers.** Employees can only draft; anyone with HR User, HR Manager or System Manager submits. 14 of the 20 WFH requests were self-submitted and 6 were submitted by Accounts; none by a manager. 30 WFH days since June (Jun 1, Aug 8, Sep 21), Tech 18, Finance 6, Ops 5, Marketing 1.
- **Performance is not set up.** One appraisal cycle "Mar 2026 - Sept 2026" (ends 30-Sep) was never started: 0 appraisees, 0 goals, 0 feedback. Its one template holds 8 company-wide KRAs, not the 5 role KRAs the handbook requires.
- **The handbook contradicts itself.** Section 13.10 (added 10-Apr) rates people on measurable outcomes, while Sections 8 and 11 judge presence. Section 11 has no eligibility rule at all.
- **Plane is used unevenly.** It is open to every team but only engineering uses it as its system of record.

**Goal:** from the Oct-2026 to Mar-2027 cycle, every employee's work is visible in Plane, every employee has role KRAs and goals in the ERP, adherence to these habits is measured, and WFH follows from all of that instead of from case-by-case trust.

## 2. What success looks like

1. From 1-Oct every WFH day in the ERP has an approval by the employee's reporting manager (or HR fallback). The founders never again have to ask "who approved it".
2. By 15-Oct every non-founder employee has 5 goals under their role's KRAs, signed off by them and their manager.
3. From 1-Nov each employee and manager can see a monthly adherence score, computed from system records only.
4. Goal progress for work tracked in Plane updates itself; nobody types a percentage by hand for that work.
5. The founders can see the company rating distribution against the handbook's 5/15/25/50/5 guide before ratings are final.
6. Handbook v1.1 (Sections 8, 11, 13) is approved by the founders and published, and every employee has acknowledged it.

## 3. What we will not do

- No screen monitoring, keystroke or "time online" tracking.
- No scoring on raw task or commit counts. Plane feeds goal progress and adherence, never a count-based score.
- No change to biometric check-in, to "On Duty" or "Weekly Off" requests (they keep self-submitting as today), or to payroll.
- No ERPNext or Frappe version upgrade as part of this program.
- No change to the unused Mar-Sep cycle beyond letting it lapse.

## 4. Live facts this design rests on (verified 26-Sep)

| Fact | Source |
|---|---|
| Frappe 16.27, ERPNext 16.28, HRMS 16.13 on GCE VM `caryaar-erpnext` (project `cy-erp`) | `get_versions`, memory |
| 14 active employees; Tech 3 (Sahaib, Shiwans, Nayan intern) | Employee list |
| Only Sahaib has a confirmation date; Shiwans (joined 15-Jun) and Kaushik (20-Jul) are inside the handbook's 6-month probation | Employee list |
| Kaushik reports to Maxson; Priya (intern) reports to Kaushik; ops executives report to Hiren | Employee.reports_to |
| Reema (Director HR) holds only "HR User"; Shubham (Accounts) holds "HR Manager" and "System Manager" | Has Role |
| 0 Workflows, 0 Server Scripts, 0 Insights dashboards; 7 Wiki spaces, 4 LMS courses | API counts |
| Workflow conditions can use `frappe.db.get_value` and `frappe.session` | frappe v16 `get_workflow_safe_globals` |
| The HRMS mobile app shows workflow action buttons on Attendance Request | hrms v16 `FormView.vue` renders `WorkflowActionSheet` |
| Final score formula variables: `goal_score`, `average_feedback_score`, `self_appraisal_score`; KRA method "Automated Based on Goal Progress" exists | hrms v16 `appraisal.py`, `appraisal_cycle.json` |
| No native team bell curve; Appraisal Overview report lists final score and department per person | hrms v16 source |
| ERP `/api` bypasses Cloudflare Access by design; Plane UI is behind Access; the Google Chat to Plane app already calls Plane's API on `127.0.0.1` from the Plane VM | memory: `reference_erp_cloudflare_access_model`, `project_gchat_to_plane_task_integration` |

## 5. Decisions (defaults proposed; founders confirm)

| # | Decision | Default | Why |
|---|---|---|---|
| D1 | What makes a person eligible for standing WFH | Not an intern, role work tracked in Plane, and **90 percent adherence in the previous full month**. Not "finished probation". | Confirmation dates are not recorded, and a probation rule would exclude Shiwans, Joel's own example. Track record is what Joel asked for. |
| D2 | How many WFH days a week | A founders' number, set as one parameter. Default for the pilot: **1 day a week**, managers may approve more for a specific deliverable. | Joel is at "stop it"; one tracked day is an easy yes and can grow with evidence. |
| D3 | Who approves | The employee's **reporting manager**; HR Manager as fallback (manager away, or no manager). No self-approval. | Kaushik's request went to Sahaib, but his manager is Maxson. |
| D4 | Founders | Founders use Plane and appear in adherence. They are **not** appraised on the bell curve; their goals sit under a "Leadership - Company Scorecard" template built from the 8 existing company KRAs. | Founders cannot calibrate themselves; adherence must still include them or nobody follows it. |
| D5 | Bell curve level | **Company-wide** until a function has 10 or more people. Section 13.10.4 note amended accordingly. | Teams of 1 to 3 cannot hold a 5/15/25/50/5 split. |
| D6 | Performance category bands (final score out of 5) | Exceptional 4.50+, Excellent 3.75 to 4.49, Good 3.00 to 3.74, Fair 2.00 to 2.99, Non-Satisfactory below 2.00 | HRMS scores are 0 to 5; bands are HR's call and are one setting. |
| D7 | Weight of process adherence | Inside the handbook's 20 percent "Behaviour and Culture": feedback criteria Competencies 40, Behaviour and Culture 25, Process Adherence 15, Initiative 20 (of the feedback half). Overall: KRAs 50, Competencies 20, Behaviour 12.5, Adherence 7.5, Initiative 10. | Keeps Section 13.10.3's weights intact while making adherence count. |
| D8 | WFH and ratings | Only a **Non-Satisfactory** rating removes WFH eligibility. | 13.10.9.2 puts "Fair" (50 percent of people by design) on weekly check-ins; tying WFH to Fair would remove it from half the company. |
| D9 | When adherence counts | October is a learning month (visible, not counted). Counts from **1-Nov**. | Many new habits at once; a fair start makes enforcement stick. |

## 6. Workstreams

### W1. WFH approval in the ERP (configuration, no code; revised 26-Sep after live permission checks)

**What the live ERP showed (26-Sep):** the Employee role can only create an Attendance Request draft; only HR User, HR Manager and System Manager can submit. Of the 20 WFH days since June, 14 were submitted by the employee themself (their broad roles allowed it) and 6 by an Accounts executive; none by a reporting manager or HR. Reema, Joel, Hiren and Kaushik each carry a User Permission that locks them to their own Employee record for all doctypes, so as managers they cannot open their team's requests. That lock also scopes salary slips, so it must not simply be removed. In Frappe v16 a document shared with a user is readable even when their user permission fails, and user permissions can be scoped to a single doctype.

**Pieces:**

1. **Approver fields** on Attendance Request (custom fields, `cy_` prefix, later shipped as fixtures): `cy_reports_to` (Link Employee, read-only, fetched from `employee.reports_to`) and `cy_approver_user` (Link User, read-only, fetched from `cy_reports_to.user_id`).
2. **States** (Draft first, so existing drafts map to Draft): Draft (0, Employee), Pending (0, HR Manager), Approved (1, HR Manager), Rejected (0, HR Manager), Cancelled (2, HR Manager).
3. **Transitions:**

| From | Action | To | Role | Condition |
|---|---|---|---|---|
| Draft | Send for Approval | Pending | Employee | `doc.reason == "Work From Home"` |
| Draft | Approve | Approved | HR User, HR Manager, System Manager (one row each) | `doc.reason != "Work From Home"` (On Duty and Weekly Off keep today's HR submission exactly) |
| Pending | Approve / Reject | Approved / Rejected | Employee | `doc.cy_approver_user and frappe.session.user == doc.cy_approver_user`; self-approval off |
| Pending | Approve / Reject | Approved / Rejected | HR Manager | approver's Employee department is Human Resources or Corporate Management; self-approval off |
| Approved | Cancel | Cancelled | HR Manager | none |

   Workflow email alerts stay OFF: Frappe would alert every holder of the allowed role, and that role is Employee (everyone).
4. **Submit permission:** the Employee role gets `submit` on Attendance Request so a manager's approval can submit the document; the workflow is the gate (an employee has no transition that submits their own WFH).
5. **Scoped manager visibility:** User Permission rows (allow Employee, applicable for Attendance Request only) for each restricted manager over each direct report: Hiren over Janhavi and Anagha; Joel over Reema, Zoeb and Hiren; Kaushik over Priya; Reema (HR fallback) over every active employee. Salary slips and every other doctype stay as today. Rows must follow reporting-line changes (W4 can maintain them later).
6. **Notifications** (Frappe Notification, email): to `cy_approver_user` when a request enters Pending; to the HR mailbox when a request enters Pending with no approver (only the CEO has no manager); to the employee when it is Approved or Rejected.
7. **Pre-req:** Reema gets HR Manager.

**Rollback:** set the workflow inactive, delete the scoped user permissions, remove the Employee submit permission, disable the notifications. These stay rolled back across deploys: the workflow, notifications and docperms are versioned in `performance/setup_data/` and created by an `after_migrate` step only where missing, never re-applied as fixtures (final review, 26-Sep).

**Status: LIVE on production 26-Sep-2026.** Founder decisions applied: Reema and Joel unlocked fully (their `create_user_permission` switched off, which removed their Employee and Company user permissions), so scoped rows exist only for Hiren (Janhavi, Anagha) and Kaushik (Priya). Both approver fields carry `ignore_user_permissions`, otherwise an employee locked to their own record would lose access to their own request because `cy_reports_to` holds the manager's ID. Existing requests mapped to 36 Approved, 7 Draft, 1 Cancelled. Notification subjects are capped at 140 characters by Frappe.

**Acceptance:** existing requests map to Draft, Approved or Cancelled by docstatus; an On Duty draft offers only the HR "Approve"; a WFH draft offers only "Send for Approval"; the approver's email arrives; the manager (not the employee, not Accounts) can approve; the same works in the HRMS mobile app. Staging (`erp-staging`) was unreachable on 26-Sep, so the end-to-end check is a real request on production (a direct report of Sahaib files a future-dated WFH request, Sahaib approves, HR cancels it afterwards).

### W2. Performance setup in the ERP (configuration)

1. **KRA library:** add the role KRAs in Appendix A.
2. **Feedback criteria:** Competencies, Behaviour and Culture, Process Adherence, Initiative and Innovation (weights per D7).
3. **Appraisal templates**, one per role family (Appendix A): Leadership, Technology, Technology Intern, Customer Experience, Workshop Relations, Partnerships, Marketing, Marketing Intern, Accounts, HR and Admin.
4. **Appraisal Cycle "Oct 2026 - Mar 2027"** (01-Oct-2026 to 31-Mar-2027): KRA method "Automated Based on Goal Progress"; formula `goal_score * 0.5 + average_feedback_score * 0.5`; appraisees = all active non-founders with their role template; started on 1-Oct.
5. **Goals** 1 to 15 Oct: each employee drafts 5 goals under their KRAs with their manager (handbook 13.10.5 sign-off). Work tracked in Plane links the goal to a Plane module (W4).
6. The unused "Mar 2026 - Sept 2026" cycle is left untouched.

**Status: created as DRAFT on production 26-Sep-2026 (cycle Not Started, 0 appraisals).** 49 KRAs (41 new plus the 8 existing company ones); every KRA carries a description in the form "Measure: ... Source: ..." because the founder found bare titles too vague. Person-specific targets belong in each Goal, not in the KRA. Four criteria, ten templates, cycle "Oct 2026 - Mar 2027" with 11 appraisees (founders excluded). Next: founders and heads edit KRA wording by 30-Sep, start the cycle on 1-Oct, goals 1 to 15 Oct.

**Acceptance:** every appraisee has an appraisal with the right template on 1-Oct; a test goal's progress change moves its appraisal's goal score; the formula reproduces a hand-computed final score for one sample.

### W3. Plane for every team (Plane admin)

**Structure (founder-confirmed direction, 26-Sep): one workspace ("CarYaar"), one project per ERP department.** Separate workspaces are hard walls (no cross-workspace views, analytics or issue links) and would break cross-team tickets such as FINANCE-1 to DEV-1198. Sensitive work uses private projects instead.

As seen on 26-Sep the workspace has 7 members and projects Finance, Branding, Yaar Space, Operations, Marketing, Corporate, Development.

| ERP department | Plane project | Action |
|---|---|---|
| Technology | Development | keep |
| Finance and Accounts | Finance | keep |
| Marketing | Marketing | keep; Branding folds in as a module unless it is a separate program (founder to confirm) |
| Operations (Customer Experience) | Operations | keep |
| Corporate Management | Corporate | keep, set private |
| Workshop Relations | WR | created 26-Sep (lead Hiren) |
| Partnerships | PARTNER | created 26-Sep (lead Zoeb once he joins) |
| Human Resources | HR ("HR and Admin") | created 26-Sep; must be set private in the UI (API cannot) |
| (none) | Yaar Space | general project imported from ClickUp; its 11 closed items copied to CORP, MKT, BRAND, FINANCE, HR (tagged `external_source=yaar-space`) and the project archived on 26-Sep-2026 |

1. Create the three missing projects; set Corporate and HR private.
2. Invite the 7 employees not yet in the workspace, by company email (the identity key for W4).
3. House rules, kept to three: every task has one assignee; every task has a target date; each goal from W2 has a matching Plane module in its team's project.
4. Cross-team work: the requesting team logs the need in its own project and links the executing team's issue; no duplicate tickets.

**Acceptance:** all 14 active employees are workspace members with their `@caryaar.com` email; each team has a project; each W2 goal that is Plane-tracked has a module.

### W4. Plane to ERP link and adherence engine (code; as built 26-Sep, after the final review)

Plans: `docs/superpowers/plans/2026-09-26-plan-a-erp-performance-foundation.md` (ERP side) and `...plan-b-plane-erp-sync.md` (Plane side).

**4a. `plane-erp-sync` on the Plane VM** (`deploy/plane-erp-sync/`, a Python container on the `plane-app_default` Docker network, running every 15 minutes, restart unless-stopped):

- Reads Plane's Postgres directly as a dedicated role `plane_erp_sync` with `SELECT` on the ten tables it needs and `default_transaction_read_only = on`. The owner password (`PLANE_POSTGRES_PASSWORD`) is used only by the deploy script on the VM to create that role and never reaches the container. The public API was not used: it has no activity-by-person endpoint and allows 60 requests a minute.
- Asks the ERP how far Plane data is confirmed (`get_sync_state`) and re-sends from that day, at least yesterday and at most 31 days, so an outage leaves no silent gap.
- Excludes deleted rows, drafts, bot users, users without a real email, Plane's automation rows, and the Yaar Space copies (`external_source = 'yaar-space'`).
- Pushes to the ERP through `/api` with the API key of `performance-sync@caryaar.com`, whose only role is `Performance Sync` (no doctype permissions; the endpoints check the role). Never the Administrator key.
- A column missing after a Plane upgrade stops the container at startup, naming the column. Errors go to the container log; a stopped sync is visible in the ERP as a stale "synced through" time.

**4b. Rules in the ERP app** (nightly at 23:30 IST for today and the three days before, plus an HR "recompute" for up to 62 days):

- **Intake:** `ingest_activity(source, synced_through, covers_from, rows)` writes one `Work Activity Day` per person, day and source, updating only the metrics a row carries. A source's stamp moves forward only when the payload covers from the day of the current stamp, so days never sent stay pending. `ingest_module_progress` keeps `Plane Module Progress`.
- **Work Adherence Day** per employee per working day (holidays resolved through HRMS Holiday List Assignments as of that day; leave and absent days excluded):
  - `work_visible`: activity in the person's work record (Plane, or CY Admin for Operations) that day; pending until every expected source has synced past the day.
  - `wfh_approved` and `wfh_evidenced` on WFH days. A request still waiting for approval makes a day a WFH day only when there is no attendance saying otherwise.
- **Monthly adherence percent** = passed checks / applicable checks.
- **Goal progress:** goals in In Progress cycles for active employees with a Plane module (ID or pasted link) get progress = completed / non-cancelled tasks. Unknown modules are listed on the settings form.
- **Performance category:** stored on submitted appraisals only; the Rating Distribution report shows the provisional spread live.

DocTypes (in this app): `Work Activity Day`, `Work Adherence Day`, `Plane Module Progress`, `Performance Sync Settings` (single). Custom fields: `Goal.cy_plane_module`, `Appraisal.cy_performance_category`, plus the live `Attendance Request` approver fields. Role: `Performance Sync`.

**Testing:** pure rules and payload tests run locally; Frappe integration tests (`performance/tests/test_integration.py`) run on the staging ERP before production.

**Acceptance:** a Plane task moved to Done appears in the ERP within 15 minutes; a goal linked to a module shows the module's completion; a WFH day with no completed work shows as not evidenced; a stopped sync leaves later days pending, not failed.

**Not built yet (tracked):** employees and managers seeing their own adherence (success criterion 3, needed before 01-Nov; who sees what is a founder decision), manager response-time and monthly goal-hygiene checks.

### W4c. CY Admin as a second activity source (added 26-Sep on the founder's direction)

Customer Experience (Anagha, Janhavi) work in CY Admin, not Plane: calls, assigned leads, follow-ups. Their proof of work and KRA progress come from the caryaar-api database. Facts below are from caryaar-api `origin/main` c03c667, read-only.

**Identity:** staff are `users` rows with `user_type='CY_ADMIN'`, `status='ACTIVE'`, `deleted_at IS NULL` (agent_roster.py:100). The calling team holds role `SALES_AGENT`. There is no link from a user to an ERP Employee. The join key is `users.email` = Employee `user_id` (seeded as `first.last@caryaar.com`, migration 206).

**Where it runs:** a Celery beat task in caryaar-api (Celery runs in IST, crontab 23:50), using the existing `FrappeClient` (integrations/frappe/client.py) but with a dedicated least-privilege ERP key, not the Administrator key the billing sync uses today. It writes the same ERP `Work Activity Day` records as the Plane sync, with `source = "CY Admin"`. The existing per-agent `sales-report` (live_ops_tower.py:1237) is the reference, but its team block buckets days in the DB session timezone (likely UTC), so the export must bucket every timestamp with `AT TIME ZONE 'Asia/Kolkata'`.

**Per agent per IST day:**

| Measure | Source | Note |
|---|---|---|
| Calls handled, answered, talk time | `voice_calls` where `source='HUMAN_AGENT'` and `agent_user_id` = user | one call produces several rows; collapse into sessions like call_collapse.py (5-minute gap) before counting. Answered = COMPLETED with duration > 0 |
| Calls with a disposition | `voice_calls.outcome` on HUMAN_AGENT rows | no timestamp or "by" on the disposition itself; counted by call date |
| Lead status moves | `lead_status_history.changed_by` = user | CALL-sourced rows have no actor |
| Notes written | `customer_notes.author_user_id` | |
| Bookings credited | `bookings.credited_user_id` (snapshot of the assignee at booking) | the attribution column |
| Leads assigned, untouched, overdue follow-ups | `customers.assigned_to_user_id`, `next_action_at` | point-in-time only (no assignment history), so the export snapshots them daily |

**Adherence for CY Admin roles:** a working day counts as "work visible" when the person has at least one handled call, status move or note that day.

**Gaps the code cannot measure yet (small additive backend changes, own plan):** assignment history (overwritten in place), disposition time and author, follow-up completion (marking Done sets `next_action_at` to NULL with no record), an agent on `scheduled_callbacks`, and the sender of an agent WhatsApp message (only `audit_logs` has it). Until then, "Customer follow-ups on time" is inferred from a later call by the agent, and "Job updates to customers on time" and "CRM data completeness" stay manager-assessed. Existing per-agent targets (`agent_allocations`, migration 200; `sales_targets`, migration 193) can seed Customer Experience goals.

### W5. Dashboards (native Frappe, shipped as fixtures)

Dashboard "Performance and Adherence":

1. Rating distribution (Appraisal grouped by `cy_performance_category`, company-wide) plus a query report "Rating distribution vs guide" showing actual percent next to 5/15/25/50/5.
2. Monthly adherence by department and by person.
3. WFH days per month by department, with percent approved and percent evidenced.
4. Unmapped Plane users and sync freshness.

Native Dashboard Charts are used instead of Insights (0 dashboards exist there) so the charts are versioned in git with the app.

### W6. Handbook, guides and announcement

1. **Handbook v1.1 redline** (Sections 8, 11, 13) as a CarYaar-branded Word document for Maxson, Joel and Reema: Section 11 rewritten around D1 to D9; Section 8 recognises approved WFH as attendance; Section 13 notes on bell-curve level, adherence weight and the D8 rule. After approval, publish to the `Employee Handbook` doctype and `/handbook`.
2. **Employee guides** in the ERP Wiki, plain language: "Asking for a WFH day", "Your work in Plane", "Your KRAs and goals".
3. **"What changes on 1 October"** announcement for Reema to send on Google Chat and email, stating what is measured and what is not (section 3).

## 7. Sequence

| When | What | Gate |
|---|---|---|
| 26 to 30 Sep | Founders agree D1 to D9; W1 on staging then production; W2 configured; Appendix A KRAs reviewed | Founder go per production change |
| 1 Oct | Cycle opens; Plane mandatory; learning month starts; announcement and guides out | |
| 1 to 15 Oct | Goals set per person; W3 projects and invites | |
| October | W4 built, tested on staging, deployed; W5 dashboards | App deploy go (VM snapshot first) |
| 1 Nov | Adherence counts | |
| November | Handbook v1.1 approved and published | Founder approval |
| March 2027 | Annual review on real data | |

## 8. Production changes needing an explicit founder go (one at a time)

| # | Change | System | Reversible by |
|---|---|---|---|
| P1 | Give Reema "HR Manager" | ERP | removing the role |
| P2 | Create "Attendance Request Approval" workflow | ERP | setting the workflow inactive |
| P3 | Create KRAs, criteria, templates and the Oct-Mar cycle | ERP | deleting the new records (cycle not yet started) |
| P4 | Plane: inventory, new projects, invites | Plane | archiving projects, removing members |
| P5 | ERP user `performance-sync@caryaar.com` with only the "Performance Sync" role (no doctype permissions) and its API key in Secret Manager `erp-performance-sync-key` | ERP, GCP | disabling the user |
| P6 | Secret Manager `PLANE_ERP_SYNC_DB_PASSWORD`; read-only Postgres role `plane_erp_sync` (SELECT on ten tables); deploy the `plane-erp-sync` container on the Plane VM | GCP, Plane VM | `docker rm -f plane-erp-sync`; `DROP ROLE plane_erp_sync` |
| P6b | Deploy caryaar-api with the dormant CY Admin sync; wire `ERP_PERFORMANCE_SYNC_KEY` on the worker; switch on `PERFORMANCE_SYNC_ENABLED` | Cloud Run | switch the flag off |
| P7 | Deploy app update to the ERP (`bench migrate`) after a VM snapshot | ERP VM | snapshot restore; app revert |
| P8 | Publish handbook v1.1 | ERP | re-publish v1.0 content |

**Done on 26-Sep-2026 (P5, P7):** production backend, queues and scheduler run `caryaar-erpnext:v16.5-live-perf2`, built on the ERP VM from the image that was live (`v16.5-live`) plus this app at 09d9c0d and the `cy_billing` module `__init__.py` (caryaar-platform 7b733d0). Nginx and websocket stay on `v16.5-live`. Recipe, migrate logs and rollback notes are on the VM in `/home/sahaib/backups/perf-deploy-20260926/`; snapshot `caryaar-erpnext-pre-perf1-20260926`. Three things found on the way and fixed:

- A full `bench migrate` had been failing on production because the `cy_billing` module folder had no `__init__.py`.
- "Weekly Off" and bulk edit on Attendance and Attendance Request had been made by editing stock HRMS files in developer mode. They now ship from this app as Property Setters, and HRMS is back to stock files.
- Developer mode is off on production.

The sync user is a Website User with the Performance Sync role only. The LMS and Wiki apps add "LMS Student" and "Wiki User" to every new user, so those roles were removed. Recreating the backend container changes its address, so always restart the frontend (nginx) in the same step.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Managers do not approve in time and WFH stalls | Manager response time is itself an adherence check; HR fallback path |
| People mark attendance another way to skip approval | W5 shows WFH days without an approved request; HR follows up |
| Adherence reads as surveillance | Announcement states exactly what is and is not measured; no screen or time tracking; October not counted |
| `bench migrate` on the financial ERP breaks billing | Staging first, VM snapshot, deploy in a quiet window, `cy_billing` smoke check after |
| Plane emails do not match ERP users | Sync reports unmapped users; W3 invites by company email only |
| Plane upgrade changes API responses | Sync validates shapes and fails loudly into `Plane Sync Settings.last_error` |
| Leadership does not use Plane | D4 puts founders in adherence from day one |
| Phone-first staff (Operations, Workshop Relations) cannot use the Plane native app: self-hosted login is Commercial Edition only (memory `project_plane_pm_selfhost`) | Mobile browser as baseline; bring the built Google Chat `/task` bridge live so tasks can be created from Chat; Plane to Google Chat updates already live |

## Appendix A. Draft role KRAs (for founders and heads to edit; 5 per role, weights sum to 100)

| Template | KRA (weight) |
|---|---|
| Leadership - Company Scorecard | Existing 8 company KRAs: Company Revenue 15, Company Profitability 15, Workshop Partners Onboarded 15, Workshop Partners Managed 10, New Customers Onboarded 15, Customers Managed 10, Technology Development 10, Technology Maintained 10 |
| Technology (Programmer, Full-Stack Engineer) | Committed sprint work delivered 30; Production reliability and fix time 20; Quality of releases (defects found after release) 20; Support to operations teams 15; Documentation and knowledge sharing 15 |
| Technology Intern | Learning plan completed 30; Assigned tasks delivered 30; Code review feedback applied 20; Documentation and knowledge sharing 10; Team participation 10 |
| Customer Experience (Operations) | Lead to booking conversion 30; Customer follow-ups on time 20; Customer satisfaction 20; Job updates to customers on time 15; CRM data completeness 15 |
| Workshop Relations | Service Partners onboarded 25; Service Partner turnaround time 25; Disputes and escalations resolved 20; Service Partner quality audits 15; Team development 15 |
| Partnerships | Partnerships signed 30; Revenue from partnerships 30; Partner activation 20; Partner retention 10; Pipeline hygiene 10 |
| Marketing (Social Media) | Content calendar delivered 25; Reach and engagement growth 20; Leads from social and ads 25; Cost per lead 15; Brand consistency 15 |
| Marketing Intern | Content pieces delivered 30; Learning plan completed 25; Assigned campaigns supported 25; Brand consistency 10; Team participation 10 |
| Accounts | Monthly books closed on time 25; Payables and receivables on time 20; GST and TDS compliance 25; Service Partner payout reconciliation 20; MIS reports on time 10 |
| HR and Admin | Hiring turnaround 20; Attendance and payroll accuracy 25; Policy compliance and records 20; Appraisal cycle run on time 20; Employee engagement 15 |
