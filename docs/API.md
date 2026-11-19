# STACKLOOM HTTP API

The dashboard's own API, on 127.0.0.1 only. Generated from the code by `scripts/api_doc.py`; do not edit by hand.

Every route except `GET /api/health` and `POST /api/auth/login` needs the session cookie set at sign-in.
Requests that change something must send the session's CSRF token (returned by sign-in and `GET /api/auth/me`)
in `X-CSRF-Token`. While the first-run password is unchanged, only the `/api/auth/*` routes answer.

Errors come back as `{"detail": "<plain-language message>"}`. `409` means the action needs confirmation:
repeat it with `"confirm": true` (or `"approve": true` for a start command) after showing the message to the user.
Long operations return a task (`{"id", "status", "message"}`); poll `GET /api/tasks/{id}` until it is `done` or `failed`.

## Sign-in

| Method | Path |
|---|---|
| `POST` | `/api/auth/login` |
| `POST` | `/api/auth/logout` |
| `GET` | `/api/auth/me` |
| `POST` | `/api/auth/password` |

## Workspace

| Method | Path |
|---|---|
| `GET` | `/api/activity` |
| `GET` | `/api/groups` |
| `GET` | `/api/overview` |

## Projects and runtime

| Method | Path |
|---|---|
| `GET` | `/api/projects` |
| `DELETE` | `/api/projects/{project_id}` |
| `GET` | `/api/projects/{project_id}` |
| `GET` | `/api/projects/{project_id}/containers` |
| `POST` | `/api/projects/{project_id}/group` |
| `POST` | `/api/projects/{project_id}/handover` |
| `POST` | `/api/projects/{project_id}/launch` |
| `GET` | `/api/projects/{project_id}/logs` |
| `POST` | `/api/projects/{project_id}/open` |
| `POST` | `/api/projects/{project_id}/restart` |
| `GET` | `/api/projects/{project_id}/runtime` |
| `POST` | `/api/projects/{project_id}/start` |
| `POST` | `/api/projects/{project_id}/stop` |
| `GET` | `/api/services` |

## Discovery

| Method | Path |
|---|---|
| `POST` | `/api/discovery/adopt` |
| `GET` | `/api/discovery/candidates` |
| `POST` | `/api/discovery/scan` |

## Ports

| Method | Path |
|---|---|
| `GET` | `/api/ports` |
| `POST` | `/api/ports/pool` |
| `POST` | `/api/ports/{project_id}/{service}` |
| `POST` | `/api/ports/{project_id}/{service}/auto` |

## Docker

| Method | Path |
|---|---|
| `GET` | `/api/docker` |
| `POST` | `/api/docker/build/{project_id}` |
| `GET` | `/api/docker/compose` |
| `POST` | `/api/docker/compose/{name}` |
| `GET` | `/api/docker/containers` |
| `GET` | `/api/docker/containers/{name}` |
| `POST` | `/api/docker/containers/{name}` |
| `POST` | `/api/docker/containers/{name}/exec` |
| `GET` | `/api/docker/containers/{name}/logs` |
| `GET` | `/api/docker/images` |
| `GET` | `/api/docker/images/history` |
| `POST` | `/api/docker/images/prune` |
| `POST` | `/api/docker/images/pull` |
| `POST` | `/api/docker/images/remove` |
| `POST` | `/api/docker/images/tag` |
| `POST` | `/api/docker/networks` |
| `GET` | `/api/docker/networks` |
| `POST` | `/api/docker/networks/remove` |
| `POST` | `/api/docker/networks/{name}/connect` |
| `GET` | `/api/docker/volumes` |
| `POST` | `/api/docker/volumes` |
| `POST` | `/api/docker/volumes/backup` |
| `POST` | `/api/docker/volumes/remove` |

## Databases

| Method | Path |
|---|---|
| `POST` | `/api/db/connections` |
| `GET` | `/api/db/connections` |
| `DELETE` | `/api/db/connections/{conn_id}` |
| `POST` | `/api/db/connections/{conn_id}/password` |
| `POST` | `/api/db/connections/{conn_id}/test` |
| `GET` | `/api/db/discover` |
| `GET` | `/api/db/{conn_id}/admin` |
| `POST` | `/api/db/{conn_id}/backup` |
| `GET` | `/api/db/{conn_id}/browse` |
| `POST` | `/api/db/{conn_id}/databases` |
| `GET` | `/api/db/{conn_id}/databases` |
| `POST` | `/api/db/{conn_id}/databases/drop` |
| `POST` | `/api/db/{conn_id}/drop-table` |
| `POST` | `/api/db/{conn_id}/export` |
| `POST` | `/api/db/{conn_id}/find` |
| `GET` | `/api/db/{conn_id}/history` |
| `GET` | `/api/db/{conn_id}/key` |
| `GET` | `/api/db/{conn_id}/keys` |
| `POST` | `/api/db/{conn_id}/query` |
| `POST` | `/api/db/{conn_id}/restore/{backup_id}` |
| `POST` | `/api/db/{conn_id}/rows` |
| `GET` | `/api/db/{conn_id}/table` |
| `GET` | `/api/db/{conn_id}/tables` |

## CodeCortex

| Method | Path |
|---|---|
| `GET` | `/api/codecortex/maps` |
| `GET` | `/api/codecortex/recent` |
| `POST` | `/api/codecortex/{project_id}/backup` |
| `POST` | `/api/codecortex/{project_id}/connect-agent` |
| `POST` | `/api/codecortex/{project_id}/delete` |
| `POST` | `/api/codecortex/{project_id}/refresh` |
| `GET` | `/api/codecortex/{project_id}/validate` |
| `GET` | `/api/graph/{project_id}` |
| `GET` | `/api/graph/{project_id}/export` |
| `GET` | `/api/graph/{project_id}/node` |
| `GET` | `/api/graph/{project_id}/search` |
| `GET` | `/api/graph/{project_id}/summary` |

## Git

| Method | Path |
|---|---|
| `GET` | `/api/git` |
| `POST` | `/api/git/{project_id}` |
| `GET` | `/api/git/{project_id}` |
| `GET` | `/api/git/{project_id}/diff` |

## Environment

| Method | Path |
|---|---|
| `POST` | `/api/env/{project_id}` |
| `GET` | `/api/env/{project_id}` |
| `GET` | `/api/env/{project_id}/compare` |
| `GET` | `/api/env/{project_id}/file` |

## Diagnostics

| Method | Path |
|---|---|
| `GET` | `/api/diagnostics` |
| `GET` | `/api/diagnostics/{project_id}` |

## Backups

| Method | Path |
|---|---|
| `GET` | `/api/backups` |
| `POST` | `/api/backups/settings` |
| `POST` | `/api/backups/stackloom` |
| `POST` | `/api/backups/{backup_id}/delete` |
| `GET` | `/api/backups/{backup_id}/download` |
| `POST` | `/api/backups/{backup_id}/verify` |

## Notifications

| Method | Path |
|---|---|
| `GET` | `/api/notifications` |
| `POST` | `/api/notifications/read` |

## Tasks

| Method | Path |
|---|---|
| `GET` | `/api/tasks` |
| `GET` | `/api/tasks/{task_id}` |

## Settings

| Method | Path |
|---|---|
| `GET` | `/api/settings` |
| `POST` | `/api/settings/workspaces` |
| `DELETE` | `/api/settings/workspaces` |
| `GET` | `/api/system` |

## Health

| Method | Path |
|---|---|
| `GET` | `/api/health` |
