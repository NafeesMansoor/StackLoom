# STACKLOOM architecture and plan

Read with `docs/INVENTORY.md` (what exists) and `docs/STACKLOOM_Rebuild_Brief.md` (what is wanted).

## Shape

One Python package, one process. The CLI and the dashboard API call the same service layer,
which keeps all state in one SQLite file. The dashboard is a React + TypeScript app built ahead
of time into static files that ship inside the wheel, so users never need Node.

```
stackloom (CLI) ─┐
                 ├─► services (stackloom/*.py) ─► SQLite  ~/.stackloom/stackloom.db
browser ─► API ──┘        │
 (FastAPI, 127.0.0.1)     ├─► subprocess: git, docker, lsof, ps
                          ├─► adapters: databases (optional extras)
                          └─► codecortex-engine (required; imported only in the indexing child process)
```

## Decisions

| Area | Choice | Why |
|---|---|---|
| Python | 3.11+ | brief; `tomllib` in stdlib |
| API | FastAPI + uvicorn (no `[standard]` extras) | brief; small and async |
| Password hashing | argon2-cffi, Argon2id, m=19 MiB t=2 p=1 | brief; OWASP minimum; the 64 MiB default kept the server at 117 MB after one sign-in |
| State | one SQLite file, WAL mode, numbered migrations | no server, easy backup |
| Frontend | React 18 + TypeScript + Vite, built into `stackloom/web/dist` | brief; no runtime Node |
| Graph view | Cytoscape.js 3.30, loaded with the graph page only (122 KB gzipped) | force, hierarchical, circle and grid layouts in one library |
| Docker | `docker` CLI with `--format json` | no SDK dependency; works with Docker Desktop, Colima, OrbStack |
| Compose files | `docker compose config --format json` | no YAML dependency |
| CodeCortex | `codecortex-engine` from PyPI, a required dependency | one engine, never copied; agents need fresh maps |
| Map refresh | child process runs `open_pipeline(root, save=True)` | incremental; engine memory freed after each run |
| Recent projects | `~/.claude/projects/*` newest session, plus `stackloom agent open <dir>` from a Claude Code SessionStart hook | agents get a fresh map within seconds of opening a project |
| Graph reading | read `graph.db` + `state.json` with `sqlite3` | viewing never loads the engine or re-indexes |
| DB drivers | extras: `postgres` (psycopg), `mysql` (PyMySQL), `mongodb` (pymongo), `redis` (redis) | core stays small |
| Credentials | OS keychain through `keyring` (extra `secrets`), else asked per session and not stored | never plaintext |

## Data layout

```
~/.stackloom/            (STACKLOOM_HOME overrides; %APPDATA%\stackloom on Windows)
  config.toml            workspace roots, port pool, dashboard port
  stackloom.db           users, sessions, projects, services, ports, tasks, activity, settings
  logs/                  stackloom.log, one log per managed project (bounded, rotated)
  state/server.json      pid, kernel start time, port of the running dashboard
  backups/
```

Nothing is written inside managed projects. Compose overrides go to `~/.stackloom/state/compose/`.

## Safety rules carried over from the ResearchOS admin

- Commands are argument lists, never shell strings. A start command is shown and approved once;
  a change in its shape asks again.
- A PID is trusted only if its kernel start time matches the one recorded at launch.
- Nothing is killed to free a port. A pinned port that is busy blocks the start and names the holder.
- The registry refuses anything that looks like a credential and any hard-coded `host:port`.
- Everything binds to 127.0.0.1.

New in STACKLOOM:

- Accounts with Argon2id hashes and server-side sessions (HttpOnly, SameSite=Strict cookie).
  Mutating requests need the session's CSRF token in `X-CSRF-Token`.
- The Host header must be `127.0.0.1`, `localhost` or `[::1]`, which blocks DNS rebinding.
- Bootstrap account `admin`, password from `STACKLOOM_ADMIN_PASSWORD` or the brief's default.
  While `must_change_password` is set, every endpoint except "change password" and "sign out"
  returns 403.
- Every administrative action writes an audit row (who, what, target, result).

## Single instance

`stackloom` reads `state/server.json`. If the recorded PID is alive with the same start time and
`/api/health` answers, it opens the browser at that address. Otherwise it starts the server in the
background, writes the file and opens the browser. The dashboard port comes from `--port`, then
`STACKLOOM_PORT`, then the last port used, then a free port in the pool.

## Phases

| Phase | Scope | State |
|---|---|---|
| 0 | Inventory, architecture, plan | done (1.0.1) |
| 1 | Package, CLI, home dir, SQLite + migrations, config, logging, auth, sessions, CSRF, audit, project registry, workspace discovery, task manager, API, dashboard shell (sign-in, password change, overview, projects), ResearchOS registry import, CodeCortex map refresh for recently opened projects | done (1.0.1) |
| 2 | Services, start/stop with approval, process supervision, port registry UI, health checks, logs, project page | done (1.0.1) |
| 3 | Docker inventory and operations, Compose projects, images, volumes, networks | done (1.0.1) |
| 4 | Database adapters, connection manager, explorer, query editor, backups | done (1.0.1) |
| 5 | CodeCortex management page, graph explorer, "connect to coding agent" (`codecortex install`, per project, opt-in) | done (1.0.1) |
| 6 | Git dashboard, environment manager, diagnostics, handover reports, backup manager | done (1.0.1) |
| 7 | Logo and brand, PyPI release, Homebrew tap, install tests | done (1.0.1); MIT licence; publishing waits for the PyPI trusted publisher and a tap repository |

## Performance budget (checked on this Mac before each phase is closed)

- `stackloom --help` under 150 ms (lazy imports; FastAPI loads only when serving).
- Dashboard ready under 2 s on a warm start.
- Idle server: no polling and no scanning; discovery runs only on request.
- Idle memory under 80 MB without CodeCortex loaded.

Measured on this Mac for 1.0.1 (Python 3.12): `stackloom agent open --hook`
0.14 s; dashboard cold start under 1 s; 52 MB resident when idle, 73 MB after a
sign-in and 20 API reads; dashboard bundle 54 KB gzipped. The first `--help` of a
fresh install takes about 1 s while Python compiles bytecode, and about 0.1 s after that.
