# STACKLOOM

One workspace. Every project. Complete control.

STACKLOOM is a local control centre for a development workspace. It finds the
projects in your workspace folders, keeps one registry of them, and keeps a
CodeCortex map of each project current, so a coding agent that opens a project
can query its code graph straight away. It runs on your machine, binds to
127.0.0.1 and needs no database server.

© 2026 Nafees Mansoor (<https://www.nafees.info>)

## Install and run

```bash
pipx install stackloom      # or: pip install stackloom, or: brew install <tap>/stackloom
stackloom                   # first run sets up ~/.stackloom, then opens the dashboard
```

Database drivers are optional: `pipx inject stackloom 'psycopg[binary]' PyMySQL pymongo redis keyring`
(or `pip install 'stackloom[all]'`). SQLite needs nothing.

The first run asks which folder holds your projects and creates the account
`admin`. The first-run password is in [docs/INSTALLATION.md](docs/INSTALLATION.md);
you must change it at the first sign-in.

## What it does

- **Workspace**: finds projects in your folders (stack, components, monorepos,
  nested repositories) and keeps one registry. Registering never touches a project.
- **Runtime**: starts, stops and restarts apps after you approve their command,
  assigns ports from one range without clashes, checks health, keeps logs, and
  shows apps started elsewhere without touching them.
- **Docker**: every container, Compose project, image, volume and network on the
  machine, with plain-language actions ("Start application"). Volumes are never
  removed as a side effect.
- **Databases**: PostgreSQL, MySQL/MariaDB, SQLite, MongoDB and Redis through one
  connection manager, a table browser, a query editor and backups. Read-only by
  default; passwords stay in the keychain or the project's own `.env`.
- **CodeCortex**: one engine (`codecortex-engine`), one map per project in
  `<project>/.codecortex/` where coding agents read it, refreshed automatically
  for projects opened in Claude Code, and an interactive graph explorer.
- **Development**: Git status, diffs, commits and branches for every repository;
  env files with secrets hidden; diagnostics; handover reports.
- **System**: background tasks, notifications, an audit log and a backup manager.

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for a tour.

## Commands

| Command | What it does |
|---|---|
| `stackloom` | start the dashboard (or reuse the running one) and open it |
| `stackloom status` | workspace summary and recently opened projects |
| `stackloom discover [--adopt PATH]` | find unregistered projects; register one |
| `stackloom projects [ID]` | list projects, or show one |
| `stackloom codecortex [list\|map\|refresh\|rebuild\|recent] [ID] [--wait]` | project maps |
| `stackloom agent open [DIR]` | a coding agent opened DIR: refresh its map |
| `stackloom agent hook install` | add the Claude Code SessionStart hook |
| `stackloom import researchos [DIR]` | copy the ResearchOS admin registry |
| `stackloom workspace add DIR` | manage another folder |
| `stackloom start\|stop\|restart [ID]` | run a project (the one in this folder by default) |
| `stackloom logs [ID]` | a project's log |
| `stackloom launch ID on\|off` | allow or forbid starting it from STACKLOOM |
| `stackloom ports [set ID SERVICE PORT \| auto ID]` | the port registry |
| `stackloom docker [ps\|images\|volumes\|networks\|compose]` | Docker inventory |
| `stackloom databases [discover\|test ID\|query ID SQL\|backup ID]` | database connections |
| `stackloom git` | Git state of every repository |
| `stackloom report diagnose\|handover [ID]` | checks, or a handover report |
| `stackloom backup [now\|verify ID\|restore FILE]` | STACKLOOM's own backups |
| `stackloom update` | check PyPI for a newer version |
| `stackloom dashboard [--stop]` | print the dashboard address, or stop it |
| `stackloom doctor` | check Python, CodeCortex, Docker, Git and the hook |
| `stackloom admin reset-password USER` | recover an account from the terminal |

## Development

```bash
uv venv --python 3.12 .venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest
cd frontend && pnpm install && pnpm build    # writes stackloom/web/dist
python scripts/brand.py --png                # logo set (needs Google Chrome for PNGs)
python scripts/api_doc.py                    # docs/API.md
```

Releases: push a `v*` tag. `.github/workflows/release.yml` builds the dashboard and
the package, tests the wheel in a clean environment and publishes to PyPI with trusted
publishing. Homebrew only accepts PyPI uploads that are at least a day old, so the
formula comes a day later: run the Release workflow by hand with the version number. It
generates the formula, builds it from source, runs its test and attaches the file to
the run.

`STACKLOOM_HOME` points STACKLOOM at another data folder, which is useful for tests.

## Licence

MIT. © 2026 Nafees Mansoor ([nafees.info](https://www.nafees.info)). See [LICENSE](LICENSE).
