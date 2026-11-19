# Changelog

## 1.0.1 (19 Nov 2026)

First release of the rebuilt STACKLOOM: all phases of the brief (0–7).

Phases 2–7:

- Runtime: start, stop and restart with one-time approval of the exact command;
  process groups with PID and start-time checks; Compose apps through a generated
  override outside the project; health checks; bounded per-project logs; apps
  started elsewhere shown as "running outside STACKLOOM" and never stopped;
  notice when an app STACKLOOM started stops by itself.
- Ports: one registry in SQLite, automatic and pinned ports, conflicts named with
  the holding program, nothing ever stopped to free a port.
- Docker: containers (with CPU and memory), Compose projects started anywhere,
  images, volumes (with backup), networks; logs, configuration with secrets
  masked, one-off commands; destructive actions confirmed, volumes never removed
  as a side effect.
- Databases: SQLite built in; PostgreSQL, MySQL/MariaDB, MongoDB and Redis through
  optional drivers; discovery from env files, SQLite files, containers and ports;
  read-only by default and enforced by the database; table browser, structure,
  row edits by primary key, query editor with highlighting, history and CSV export;
  server variables, connections and users; dumps and SQLite restore; passwords
  from the keychain, the project's env file or memory.
- CodeCortex: graph explorer (force, hierarchy, circle and grid layouts, search,
  kind filters, focus, hotspots, node details with source, PNG/JSON/GraphML export),
  validation, map backup and deletion, "connect to Claude Code".
- Git for every repository: status, diffs, commits of selected files, branches,
  stashes, fetch, fast-forward pull, push, abort merge or rebase.
- Environment files with secret values hidden, comparison by checksum, missing
  variables from example files, edits with backup.
- Diagnostics and Markdown handover reports with secrets removed.
- Backup manager: STACKLOOM's own state (daily), databases, volumes, maps and
  config files; checksums, verification, retention, download, restore.
- Notifications under a bell; declared dependencies on the project page; moving a
  project to another group.
- Status colours #16A36A, #E6A23C, #DC5757, #4285D4 with AA-safe text shades;
  borders #E5E7EF.
- Brand: woven-stack mark, logo set in SVG and PNG, favicon and touch icon,
  `docs/BRAND.md`.
- Packaging: wheel and sdist ship the built dashboard; Homebrew formula template
  and generator; CI and release workflows (PyPI trusted publishing, formula built
  from source and tested).
- Docs: `USER_GUIDE.md`, `API.md` (generated), `BRAND.md`.

Phases 0–1:

- Workspace inventory and architecture (`docs/INVENTORY.md`, `docs/ARCHITECTURE.md`).
- `stackloom` command: one-command start with a single dashboard instance, `init`,
  `status`, `discover`, `projects`, `import researchos`, `workspace`, `codecortex`,
  `agent open`, `agent hook`, `dashboard`, `doctor`, `admin reset-password`.
- SQLite state with migrations: accounts, sessions, projects, groups, ports,
  discovery results, tasks, activity, CodeCortex map records.
- Accounts with Argon2id, forced change of the first-run password, sign-in
  throttling, CSRF tokens, Host-header check, audit log.
- Discovery of projects, components, monorepos and nested repositories, with
  inferred start commands that stay disabled until reviewed.
- Import of the ResearchOS admin registry and port book.
- CodeCortex (`codecortex-engine` 2.0.2) as a required dependency: per-project
  maps, incremental refresh in a background process, automatic refresh for
  projects opened in Claude Code, and a SessionStart hook.
- Dashboard (React, prebuilt): sign-in, password change, overview, projects,
  project page, discovery, project maps, tasks, activity, settings; light and dark;
  works from 360 px wide.
