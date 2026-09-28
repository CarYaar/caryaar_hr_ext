"""Read-only queries against Plane v1.3.1's Postgres (models under apps/api/plane/db/models)."""

REQUIRED_COLUMNS = {
    "issue_activities": {"issue_id", "actor_id", "field", "new_value", "comment", "created_at", "deleted_at", "workspace_id"},
    "issues": {"id", "state_id", "completed_at", "is_draft", "external_source", "deleted_at", "workspace_id",
               "sequence_id", "name", "project_id", "start_date", "target_date", "created_at", "updated_at", "archived_at"},
    "issue_assignees": {"issue_id", "assignee_id", "deleted_at", "created_at"},
    "labels": {"id", "name", "deleted_at"},
    "label_issues": {"issue_id", "label_id", "deleted_at"},
    "users": {"id", "email", "is_bot", "is_active"},
    "states": {"id", "group"},
    "modules": {"id", "name", "project_id", "workspace_id", "archived_at", "deleted_at"},
    "module_issues": {"module_id", "issue_id", "deleted_at", "created_at"},
    "projects": {"id", "identifier", "deleted_at"},
    "workspaces": {"id", "slug"},
    "workspace_members": {"member_id", "workspace_id", "is_active", "deleted_at"},
}

SCHEMA_SQL = """
SELECT table_name, column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = ANY(%(tables)s)
"""

MEMBERS_SQL = """
SELECT lower(u.email)
FROM workspace_members wm
JOIN workspaces w ON w.id = wm.workspace_id AND w.slug = %(slug)s
JOIN users u ON u.id = wm.member_id
WHERE wm.deleted_at IS NULL AND wm.is_active AND u.is_active AND NOT u.is_bot
  AND u.email LIKE '%%@%%'
"""

ACTIVITY_SQL = """
SELECT lower(u.email) AS email, (a.created_at AT TIME ZONE 'Asia/Kolkata')::date AS day, count(*) AS n
FROM issue_activities a
JOIN users u ON u.id = a.actor_id
JOIN issues i ON i.id = a.issue_id AND i.deleted_at IS NULL
JOIN workspaces w ON w.id = a.workspace_id AND w.slug = %(slug)s
WHERE a.deleted_at IS NULL
  AND NOT u.is_bot AND u.email LIKE '%%@%%'
  AND a.created_at >= %(start)s AND a.created_at < %(end)s
  AND coalesce(i.external_source, '') <> 'yaar-space'
  AND NOT (coalesce(a.field, '') = 'archived_at' AND coalesce(a.new_value, '') = 'archive')
  AND NOT (coalesce(a.field, '') = 'state' AND coalesce(a.comment, '') LIKE 'Plane updated the state to %%')
GROUP BY 1, 2
"""

COMPLETED_SQL = """
SELECT lower(u.email) AS email, (i.completed_at AT TIME ZONE 'Asia/Kolkata')::date AS day,
       count(DISTINCT i.id) AS n
FROM issues i
JOIN issue_assignees ia ON ia.issue_id = i.id AND ia.deleted_at IS NULL
JOIN users u ON u.id = ia.assignee_id
JOIN states s ON s.id = i.state_id AND s."group" = 'completed'
JOIN workspaces w ON w.id = i.workspace_id AND w.slug = %(slug)s
WHERE i.deleted_at IS NULL AND NOT i.is_draft AND NOT u.is_bot AND u.email LIKE '%%@%%'
  AND i.completed_at >= %(start)s AND i.completed_at < %(end)s
  AND coalesce(i.external_source, '') <> 'yaar-space'
GROUP BY 1, 2
"""

MODULES_SQL = """
SELECT m.id::text, p.identifier, m.name,
       count(i.id) FILTER (WHERE s."group" <> 'cancelled') AS total,
       count(i.id) FILTER (WHERE s."group" = 'completed') AS done
FROM modules m
JOIN projects p ON p.id = m.project_id AND p.deleted_at IS NULL
JOIN workspaces w ON w.id = m.workspace_id AND w.slug = %(slug)s
LEFT JOIN module_issues mi ON mi.module_id = m.id AND mi.deleted_at IS NULL
LEFT JOIN issues i ON i.id = mi.issue_id AND i.deleted_at IS NULL AND NOT i.is_draft
LEFT JOIN states s ON s.id = i.state_id
WHERE m.deleted_at IS NULL AND m.archived_at IS NULL
GROUP BY m.id, p.identifier, m.name
"""

# Every non-draft work item in the workspace changed since %(since)s (the daily full pass
# passes the epoch). Soft deletes and archives arrive flagged, never dropped, and apart:
# Plane only archives completed or cancelled items (by hand or its auto-archive), so an
# archived item is finished work that still counts, while a deleted one is gone. One
# assignee (the earliest) per item; every module membership (oldest first) and the labels
# as comma lists. The state group arrives raw (Intake's "triage" is mapped in core).
WORK_ITEMS_SQL = """
SELECT i.id::text, p.identifier, i.sequence_id, i.name, i.start_date, i.target_date, i.completed_at,
       i.created_at, i.updated_at, coalesce(s."group", 'backlog') AS state_group,
       (i.deleted_at IS NOT NULL) AS is_deleted,
       (i.archived_at IS NOT NULL) AS is_archived,
       (SELECT lower(u.email) FROM issue_assignees ia JOIN users u ON u.id = ia.assignee_id
         WHERE ia.issue_id = i.id AND ia.deleted_at IS NULL ORDER BY ia.created_at LIMIT 1) AS assignee_email,
       (SELECT string_agg(mi.module_id::text, ',' ORDER BY mi.created_at) FROM module_issues mi
         WHERE mi.issue_id = i.id AND mi.deleted_at IS NULL) AS module_ids,
       (SELECT string_agg(l.name, ',' ORDER BY l.name) FROM label_issues li JOIN labels l ON l.id = li.label_id
         WHERE li.issue_id = i.id AND li.deleted_at IS NULL AND l.deleted_at IS NULL) AS labels
FROM issues i
JOIN projects p ON p.id = i.project_id AND p.deleted_at IS NULL
JOIN workspaces w ON w.id = i.workspace_id AND w.slug = %(slug)s
LEFT JOIN states s ON s.id = i.state_id
WHERE NOT i.is_draft
  AND coalesce(i.external_source, '') <> 'yaar-space'
  AND greatest(i.updated_at, coalesce(i.deleted_at, i.updated_at)) >= %(since)s
"""
