# Using STACKLOOM

This guide follows the dashboard's menu. Every page has a command-line twin;
`stackloom --help` lists them.

## Getting going

1. Run `stackloom`. The first time, it asks for your workspace folder, creates
   the `admin` account and opens the dashboard.
2. Sign in and choose a new password.
3. Open **Discovery** and press **Scan the workspace**. Register the projects you
   want STACKLOOM to look after. If you used the ResearchOS admin before, run
   `stackloom import researchos` instead; it brings every app with its ports.
4. Open a project. On **CodeCortex**, press **Build project map**.
5. On **Runtime**, review the start command, then **Approve and start**.

From then on, projects you open in Claude Code get their maps refreshed for you.

## Workspace

**Projects** lists everything registered, with its stack and map state. A project
page has tabs:

| Tab | What you can do |
|---|---|
| Overview | See the stack, components, nested repositories, declared dependencies and Git state; move the project to another group; open it in Finder, Terminal, VS Code or Claude Code |
| Runtime | Start, stop and restart; see each service's port, address and health; pin a port |
| Docker | See the containers whose Compose labels point at this project |
| Databases | See the connections that belong to it |
| Environment | Read env files (secret values hidden), compare two files, spot missing variables, set a value (the old file is backed up first) |
| CodeCortex | Build, refresh, validate, back up or delete the map; open the graph; connect the project to Claude Code |
| Logs | STACKLOOM's own log of the app, plus container logs |
| Checks | Run diagnostics, write a handover report, turn launching on or off |

**Discovery** reads folders and never changes them. A folder with `frontend/`
and `backend/` stays one project with two components; a Git repository inside
another project becomes its own project.

## Runtime

**Services** shows every app that has a start command. "Running outside
STACKLOOM" means the app answers on its port but STACKLOOM did not start it; it
is shown and never stopped.

Starting asks you once to approve the exact command. If the command changes,
STACKLOOM asks again. Starting is refused, and nothing is stopped, when a port is
taken by something else.

**Ports** lists every assigned port, whether it is in use and by which program.
Ports come from a range (4100–4999 by default), stay the same between starts, and
move only while the app is stopped. Pin a port to keep it fixed.

## Docker

The Docker pages show everything the engine knows, including containers you
started elsewhere. If Docker Desktop is not running, the page says so;
STACKLOOM never starts it for you.

- **Containers**: start, stop, restart, pause, remove, read logs, see the
  configuration (secret environment values hidden) and run a one-off command.
- **Compose projects**: **Start application**, stop, restart, build, pull, logs,
  status and configuration, for the whole project or one service. **Remove
  containers** keeps the data; **Remove with volumes** deletes it and asks twice.
- **Images**: pull, tag, remove unused images, clear dangling ones.
- **Volumes**: create, back up, and remove volumes that no container uses.
- **Networks**: create, connect and disconnect containers, remove unused networks.

## Databases

**Discover database connections** looks in project env files (`DATABASE_URL` and
similar), SQLite files, Docker containers and the usual local ports. Results are
unverified until you test them.

Each connection is **read-only** by default. Turn that off to edit data. The
password comes from the macOS keychain, the project's own env file, or is typed
and kept in memory until STACKLOOM stops.

Opening a connection shows its tables (or collections, or keys). You can browse
pages of rows, sort by a column, see columns, indexes and relationships, and edit
or delete a row by its primary key. In the **Query editor**, ⌘ Enter runs the
statement. Anything that changes data asks first; results export to CSV; earlier
queries are in the history. **Server** shows connections, users and settings.
**Backups** makes a dump (SQLite copy, `pg_dump`, `mysqldump`) and, for SQLite,
restores one. Dropping a table or database always makes a backup first.

Create and alter tables with SQL in the query editor.

## Code intelligence

**Project maps** lists every project's CodeCortex map: ready, refreshing or
missing, with symbol and file counts and when an agent last opened it.

**Graph explorer** draws a map. Choose a layout (force, hierarchy, circle, grid),
the kinds of symbols and relationships to show, and how many nodes. Search for a
symbol, click a node to see who calls it and what it calls, with its source, and
press **Focus** to show only its neighbourhood. **Hotspots** highlights the most
central code. Export PNG, JSON or GraphML. Viewing never re-indexes.

## Development

**Git repositories** shows every repository's branch, changes and remote state.
A repository page shows the changed files and their diffs, and lets you commit
selected files, stash, switch or create branches, fetch, pull (fast-forward only)
and push. During a merge or rebase it lists conflicted files and offers to abort.
Every change asks first.

**Diagnostics** checks every project for missing dependencies, empty
environment variables, missing tools, port conflicts, Git problems and maps.

## System

**Tasks** lists background jobs with their output. **Backups** keeps one history
for every kind of backup, verifies each by checksum, and makes a daily backup of
STACKLOOM's own registry and settings (you set how many to keep). The bell in
the top bar collects finished and failed jobs, and apps that stopped by
themselves. **Settings** holds the workspace folders. **About** lists versions and
which database drivers are installed.

## Recovering

- Forgotten password: `stackloom admin reset-password admin`.
- STACKLOOM's own data: stop the dashboard (`stackloom dashboard --stop`), then
  `stackloom backup restore <file>`. The current database is kept beside it.
- Everything STACKLOOM writes lives in `~/.stackloom`, apart from the maps in
  each project's `.codecortex/`.
