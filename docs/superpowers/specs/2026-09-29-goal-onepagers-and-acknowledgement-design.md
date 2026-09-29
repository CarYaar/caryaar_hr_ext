# Goal one-pagers and the 1:1 acknowledgement in the ERP

Date: 29-Sep-2026. Owner: Sahaib (decisions), Claude (build). Systems: the ERP app caryaar_hr_ext (doctype, permissions, notification), a generator that builds one Claude artifact per employee from the ERP, the goal meter (readings), Plane item DEV-1241.

## 1. What the founder asked for

29-Sep-2026: "Maxson will close on all the actual goals for each of them and then we can prepare that one pager for each employee in a Claude artifact, with motion, smooth transitioned motion in loop, not too frantic; and document the 1:1 in the ERP, as the team members have to acknowledge the goals set up; if it is in the ERP that would be best as it needs to be documented." He said yes to the design below the same day, and asked for the handbook to match (section 13.9.5 and 13.10.5 now say the employee acknowledges the goals in the HRMS at a goal setting 1:1, then monthly 1:1s are recorded there).

## 2. Design in one breath

The acknowledgement is a record in the ERP, never in the artifact. A new doctype, Goal One on One, holds one meeting between a manager and an employee for a cycle: the goals discussed (filled from the cycle), notes, agreed actions, and an acknowledgement that only the employee's own login can give, stamped with who and when. The one-pager is the presentation: one artifact per employee, generated from the ERP after the goals are final, with a link to the employee's Goal One on One record where the acknowledgement happens. HR reads acknowledgements from the doctype's list view.

## 3. The doctype: Goal One on One

Module Caryaar Hr Ext, not a table, not single, naming `format:1ON1-{employee}-{meeting_date}`, `track_changes` on.

| Field | Type | Notes |
|---|---|---|
| employee | Link Employee, required | in list view, standard filter |
| employee_name | Data, fetched from employee.employee_name, read only | |
| manager | Link Employee, required | default: employee.reports_to |
| manager_name | Data, fetched, read only | |
| appraisal_cycle | Link Appraisal Cycle, required | default: the live cycle |
| meeting_date | Date, required | in list view |
| meeting_type | Select: Goal setting, Monthly check-in, Mid-cycle review, Final review | default Goal setting |
| goals | Table Goal One on One Goal | filled from the cycle by the Fill goals button and on first save when empty |
| notes | Text Editor | what was discussed |
| agreed_actions | Small Text | who does what by when |
| one_pager_url | Data | the artifact link, set by the generator |
| employee_acknowledged | Check, read only | set only by the acknowledge action |
| acknowledged_on | Datetime, read only | |
| acknowledged_by | Link User, read only | must equal the employee's user |

Child table Goal One on One Goal (istable): goal (Link Goal), goal_name (Data), kra (Link KRA), weight (Percent, from the person's appraisal template row for that KRA), target_text (Data, from the Goal Meter through `meter_rules.target_text`), measured_from (Data, `meter_rules.source_text`), progress (Percent, the latest reading's progress if any).

Rules (`performance/one_on_one_rules.py`, pure, tested without Frappe):

- `goal_rows(goals, meters, readings, template_weights)` builds the child rows for the employee and cycle: one row per non-group Goal, weight from the template row whose KRA matches, target and source from the meter, progress from the latest reading.
- `can_acknowledge(session_user, employee_user, already)` returns the reason a stamp is refused: not the employee's own login, already acknowledged, or no user on the employee record.
- `acknowledgement_state(doc)` returns "acknowledged on DD-MMM-YYYY" or "not yet acknowledged" for the one-pager and the list.

Controller (`goal_one_on_one.py`): `validate` fills the goals table when empty; `fill_goals` is a whitelisted document method for the button. The acknowledge action is a whitelisted method `caryaar_hr_ext.performance.api.acknowledge_goals(name)` that loads the document, calls `can_acknowledge` with `frappe.session.user`, and on success writes the three acknowledgement fields with `db_set` and a comment "Goals acknowledged by <name>" so the timeline shows it. A user cannot set those fields through the form: they are read only and `validate` restores them from the database on every save.

Permissions: HR Manager and System Manager full. Employee role: read. Visibility is narrowed by `permission_query_conditions` and `has_permission` hooks in `caryaar_hr_ext`: an Employee-role user sees records where they are the employee or the manager. Managers who hold only the Employee role can create and edit records for their reports (write for Employee role limited by the same hook to records where they are the manager). The self-scoped Employee user permissions that Hiren and Kaushik carry do not block this because the hook, not the link permission, decides.

Notification (create-if-missing in `performance/setup.py`, like the WFH ones): "Goals acknowledged" on the acknowledgement, to the manager's user and humanresource@caryaar.com, subject under 140 characters.

Workspace: a shortcut to the Goal One on One list under Performance and Adherence; the list view shows employee, meeting date, type and the acknowledged flag; a filter "Not acknowledged" is the HR follow-up view.

## 4. The one-pager

One artifact per employee, generated by `scripts/goal_onepagers/build.py` (run from the operator's Mac with `~/.config/caryaar/frappe.env`, read only against the ERP) into `scripts/goal_onepagers/out/<employee>.html`, then published with the Artifact tool and shared by the founder with that person and their manager. Nothing personal leaves the ERP except into that person's own page.

Content, in order: the CarYaar wordmark and the cycle (01-Oct-2026 to 31-Mar-2027, mid-cycle review January, final review March); the person (name, designation, department, manager); the KRAs with their weights; one card per goal with the goal name, the target, the baseline, how it is measured and from which system, and the current reading when the meter has one; how the score is built (goals 50, feedback 50, the five levels); the acknowledgement block with a link to the person's Goal One on One record in the ERP (`https://erp.caryaar.com/app/goal-one-on-one/<name>`) and the state "acknowledged on DD-MMM-YYYY" or "not yet acknowledged, open your 1:1 record in the ERP and press Acknowledge".

Design: brand tokens (paper, ink, purple, tint), Inter and Newsreader, no emoji, lucide inline SVG only, dark theme tokens, phone width first. Motion: one slow looping road with the brand car drifting along it (the film's grammar, GSAP from cdnjs), goal cards that settle in from a visible resting state, KRA weight bars that fill once, everything under `prefers-reduced-motion` reduced to fades. No canvas, no particle effects, nothing that competes with the numbers. The page is complete at rest: every number is visible without scrolling tricks.

Data: Employee (name, designation, department, reports_to, user_id), Appraisal Cycle appraisee row (template), Appraisal Template goals (KRA, weight), Goal (employee, cycle, kra, goal_name, description with target and baseline), Goal Meter (method, metric, target, unit, window), latest Goal Meter Reading, and the Goal One on One record for the cycle (or none). The generator writes `one_pager_url` back to the record only when told the published URL (`--set-url <employee> <url>`), the one write it makes.

## 5. Sequence

1. Build the doctype, rules, hooks, notification and tests; ship with the next ERP image (perf7).
2. Build the generator and the template; review one page (Anagha) with the founder before the rest.
3. When Maxson closes the goals: HR or the manager creates the Goal setting 1:1 for each person (or the generator's `--create-1on1` creates the thirteen with meeting_type Goal setting and the goals filled), the thirteen pages are generated and published, each shared with the person and the manager.
4. The manager holds the 1:1, the employee opens the record and presses Acknowledge. HR watches the "Not acknowledged" list.
5. Monthly 1:1s are new records of type Monthly check-in on the same doctype.

Melita logs in as the shared humanresource@ mailbox, so her acknowledgement needs her own ERP user first (CORP-98). Shruti gets a record when her goals exist.

## 6. Failure modes

An acknowledgement by anyone but the employee is refused with a plain reason. A record saved with the acknowledgement fields edited by hand is restored from the database. A goal added to the cycle after the 1:1 does not appear on the old record; the next monthly check-in fills it. The generator never writes goals or readings. A page for a person with no goals says so instead of rendering an empty deck.

## 7. Testing

Pure tests for the rules; stand-in tests for the controller and the acknowledge method (own user succeeds and stamps, another user refused, HR refused, twice refused, hand-edited fields restored); meta tests for the doctype JSON (fields, permissions, hooks registered); generator tests on a fixture export (one person, two goals, one reading) checking the HTML carries every number and the acknowledgement state. The founder reviews one published page before the thirteen.
