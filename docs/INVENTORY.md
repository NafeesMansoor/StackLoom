# STACKLOOM workspace inventory

Phase 0 inspection of `~/Desktop/Claude`, done 19 Nov 2026. Nothing in the workspace was changed
during the inspection. This file records what exists, what STACKLOOM can reuse, and what it has to
build.

## 1. Machine

| Item | Found |
|---|---|
| OS | macOS (Darwin 25.6, Apple silicon) |
| Python | 3.9 (system), 3.12, 3.13, 3.14, 3.15 (Homebrew), 3.13 (MacPorts, first on `PATH`) |
| Node | 26.12, with pnpm |
| Python tooling | uv, pipx |
| Docker | Docker Desktop installed; daemon not running at inspection time |
| Databases (Homebrew) | `postgresql@16` and `mysql`, both installed and stopped |
| Clients | `psql`, `mysql`; no `mongosh`, no `redis-cli` |
| Git | `/usr/bin/git` |

Names: `stackloom` is free on PyPI and has no Homebrew formula yet (both checked 19 Nov 2026).

## 2. Projects

The ResearchOS admin (`ros`) already registers 24 apps in
`ResearchOS/registry/projects.json`, grouped by folder:

| Group | Apps |
|---|---|
| research | rie, confagent, reviewdrgeek, myresearchagent, wikiagent, mickelangelo |
| drgeek | bytequest, statetrace, fish-fight, bounce-rewind |
| devtools | architectra, codecortex, freellmapi |
| platforms | obevolve, grantchain |
| web | mysite, cupverse, iceref, lorice |
| trading | zombie-trades, trading-test |
| lab | cyber-lab-camera, oracle-cloud |
| notes | notes |

One unregistered codebase sits at the top level (`php2shell-poc`). `stackloom` itself and
`RnD Server` have no code markers yet.

Each registry entry already holds what STACKLOOM needs for runtime control: launch type
(`process` or `docker-compose`), argument-list commands, named services with `${PORT:<service>}`
placeholders, health checks, compose project names and env-file references. Port assignments
live in `ResearchOS/admin/.state/ports.json` (pool 4100–4999). Apps that need care:

- `zombie-trades`: launch disabled (starts a trading scheduler and a public tunnel).
- `cyber-lab-camera`: launch disabled (listens on all interfaces).
- `grantchain`: needs MySQL running.
- `bytequest`: broken seed script, no commits, no remote.
- `oracle-cloud`: holds keys. STACKLOOM must never read or index it.

## 3. Docker

Compose files:

| Project | Services | Named volumes |
|---|---|---|
| `Platforms/OBEvolve` | postgres:16-alpine, redis:7-alpine, backend, frontend | obevolve_postgres_data |
| `ResearchOS/Modules/RIE` | postgres:16, api, scheduler, web | rie-pgdata |
| `DrGeek/ByteQuest/ByteQuest_SQL` | server, client | three data volumes |
| `DevTools/freellmapi` | freellmapi, watchtower | freellmapi-data |
| `php2shell-poc/lab` | security lab | — |

Container, image and volume counts could not be read because the daemon was down. STACKLOOM
has to handle that state cleanly and must not start Docker by itself.

## 4. Databases

| Engine | Where |
|---|---|
| PostgreSQL 16 | RIE and OBEvolve (in Docker); Homebrew `postgresql@16` (host) |
| MySQL | GrantChain, through Homebrew `mysql` (host) |
| Redis 7 | OBEvolve (in Docker) |
| SQLite | several apps; CodeCortex maps (`graph.db`) |

Connection strings are referenced from `.env.example` files in OBEvolve, GrantChain, LoRice,
ICERef and RIE. The ResearchOS registry already reads `DATABASE_URL` from a project's `.env` at
start time without storing it. STACKLOOM keeps that rule.

## 5. CodeCortex

- Published on PyPI as `codecortex-engine` (2.0.2, Python ≥3.10). Source at
  `DevTools/CodeCortex` (remote `github.com/NafeesMansoor/CodeCortex`). STACKLOOM depends on it
  as a required package (decided 19 Nov 2026) and never vendors or copies the engine. Coding
  agents must see a fresh map for any project opened recently, so indexing cannot be optional.
- Its base install pulls in tree-sitter and 16 grammar wheels, networkx, numpy and PyYAML.
  Embeddings, LSP and clustering are separate CodeCortex extras that STACKLOOM does not require.
  STACKLOOM imports the engine only inside an indexing child process, so the dashboard's own
  memory stays small.
- **Map location.** `codecortex index` always writes to `<project>/.codecortex/` (`graph.db`,
  `state.json`, embeddings) and adds a `.gitignore` of `*` there, so it never appears in Git.
  `state_dir_for(root)` is hard-wired in `codecortex/pipeline/state.py`. The agent tools
  (`codecortex query`, `explain`, the Claude Code `hook-guard` hook) look for the map in the
  same place. Maps therefore stay in each project and STACKLOOM keeps the central index of them.
- **Incremental refresh.** `open_pipeline(root, save=True)` in `codecortex.pipeline.state`
  loads a saved map and re-parses only files whose size or mtime changed, or builds the map
  when there is none.
- **Recently opened projects.** Claude Code keeps one folder per opened directory under
  `~/.claude/projects/`, named after the path with every non-alphanumeric character replaced
  by `-`. The newest session file in each folder tells STACKLOOM which projects were opened
  recently.
- **Graph data without the engine.** `graph.db` has two tables, `nodes` (qualified_name, kind,
  name, file_path, language, range, parent, is_test) and `edges` (kind, source, target,
  confidence). `state.json` holds centrality and clusters. STACKLOOM can show an existing graph
  by reading these files with `sqlite3`, without importing CodeCortex. This matches the brief's
  rule that viewing must not trigger indexing.
- `codecortex.visualization.graph_exporter.GraphExporter` produces the JSON shape the CodeCortex
  explorer uses (nodes with centrality, fan-in/out, hotspot flag, cluster). STACKLOOM's reader
  returns the same shape so either source works in the UI.
- Existing maps: CodeCortex, OBEvolve, GrantChain.

## 6. ResearchOS admin: what to reuse

`ResearchOS/admin` (about 2,000 lines of stdlib Python plus 538 lines of tests) already solves
much of STACKLOOM phases 1–2:

| Capability | Source | Plan |
|---|---|---|
| Registry validation (no secrets, no hard-coded ports, loopback only, argv-only commands) | `project_registry.validate_registry` | port |
| Secret redaction | `redact` | port, extend |
| Discovery with inferred launch commands (Next, Vite, Laravel, FastAPI, static) | `discover`, `infer_project` | port, extend for monorepos and more stacks |
| Port book: pool, pinned/auto, conflict report naming the holder, nothing killed | `ensure_ports`, `set_port`, `port_owners` | port into SQLite |
| Process supervision with PID + kernel start-time check, process groups, SIGTERM then SIGKILL | `_start_processes`, `_kill_entries` | port |
| Compose control through a generated override file, project files untouched | `write_compose_override`, `_compose_base` | port |
| Command approval by fingerprint of the command shape | `approve_command` | port |
| Read-only Git summary | `git_summary` | port |
| Panel: loopback bind, Host check, token, fixed actions only | `panel.py` | ideas only; STACKLOOM uses accounts and sessions |

STACKLOOM copies and adapts this code and does not import ResearchOS. It can import the
ResearchOS registry once (`stackloom import ros`) so the 24 launch definitions and current port
assignments carry over.

The ResearchOS UI guide (`ResearchOS/UI-DESIGN.md`, operator profile) sets the look: neutral
grey surfaces, one blue accent, semantic green/amber/red, 6 px radius, 14 px base type, monospace
for IDs, ports and paths, light and dark tokens.

## 7. What has to be built

- Accounts, sessions, CSRF and audit log (the panel only has a per-run token).
- SQLite state for registry, ports, tasks, activity and settings (ResearchOS uses JSON files).
- A background task manager.
- Workspace-wide Docker inventory: containers, images, volumes, networks, Compose projects
  started outside STACKLOOM. ResearchOS only controls its own compose apps.
- Database adapters, connection manager, explorer and query editor.
- CodeCortex map management and the graph explorer.
- Git write operations, the environment manager, backups, diagnostics.
- React dashboard, logo, PyPI package, Homebrew tap.

## 8. Risks

1. **Two supervisors.** If `ros` and STACKLOOM both manage the same app, each may think the
   other's process is foreign. During migration STACKLOOM detects running apps by port and
   compose labels and treats processes it did not start as external: it shows them and never
   stops them.
2. **CodeCortex map location.** The brief's conceptual layout puts maps under
   `~/.stackloom/codecortex/`. Coding agents look in `<project>/.codecortex/`, so moving the
   maps would hide them from agents. STACKLOOM leaves them in place (the folder ignores itself
   in Git and holds no source changes) and records each one in its own database.
3. **Default admin password.** The brief asks for `admin` / `1234567890@`. It is accepted only
   for the first login, must be changed before anything else works, and can be replaced with
   `STACKLOOM_ADMIN_PASSWORD` at setup.
4. **Secrets in the workspace.** `Lab/oracle-cloud` holds keys. Discovery skips folders without
   code markers and the environment views show key names only, never values.
5. **Docker down.** Most Docker and database discovery depends on the daemon. Every view must
   say so plainly and offer the next step.
