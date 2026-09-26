"""Read-only queries against Plane v1.3.1's Postgres (models under apps/api/plane/db/models)."""

REQUIRED_COLUMNS = {
    "issue_activities": {"issue_id", "actor_id", "field", "new_value", "comment", "created_at", "deleted_at", "workspace_id"},
    "issues": {"id", "state_id", "completed_at", "is_draft", "external_source", "deleted_at", "workspace_id"},
    "issue_assignees": {"issue_id", "assignee_id", "deleted_at"},
    "users": {"id", "email", "is_bot", "is_active"},
    "states": {"id", "group"},
    "modules": {"id", "name", "project_id", "workspace_id", "archived_at", "deleted_at"},
    "module_issues": {"module_id", "issue_id", "deleted_at"},
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
