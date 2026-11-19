# Installing STACKLOOM

## Requirements

- macOS (Linux and Windows are planned), Python 3.11 or newer.
- Git. Docker Desktop is optional; STACKLOOM detects it when it is running.

Node is not needed: the dashboard ships prebuilt inside the package.

## Install

```bash
pipx install stackloom
```

`pip install stackloom` works too. The package installs the `stackloom` command,
FastAPI, uvicorn, argon2-cffi and the CodeCortex engine (`codecortex-engine`).

With Homebrew, from the STACKLOOM tap:

```bash
brew install <tap>/stackloom
```

The formula is generated and tested by the release workflow
(`packaging/homebrew/`, `scripts/make_formula.py`). `brew services start stackloom`
keeps the dashboard running in the background.

### Database drivers

SQLite works out of the box. For the others, add the driver you need:

```bash
pipx inject stackloom 'psycopg[binary]'   # PostgreSQL
pipx inject stackloom PyMySQL             # MySQL and MariaDB
pipx inject stackloom pymongo             # MongoDB
pipx inject stackloom redis               # Redis
pipx inject stackloom keyring             # keep database passwords in the macOS keychain
```

With pip: `pip install 'stackloom[postgres,mysql,mongodb,redis,secrets]'`, or `[all]`.
Backups of server databases use `pg_dump` and `mysqldump` when they are installed
(`brew install libpq mysql-client`).

### Updating

`stackloom update` checks PyPI and prints the right command (`pipx upgrade
stackloom`, `brew upgrade stackloom` or pip). The database upgrades itself on the
next start; take a backup first with `stackloom backup now` if you like.

## First run

```bash
stackloom
```

1. STACKLOOM creates `~/.stackloom/` (settings, database, logs). Set
   `STACKLOOM_HOME` to use another folder.
2. It asks which folder holds your projects. Add more later with
   `stackloom workspace add DIR` or on the Settings page.
3. It creates the first administrator account:

   | Username | Password |
   |---|---|
   | `admin` | `1234567890@` |

   To start with a different password, set it before the first run:
   `STACKLOOM_ADMIN_PASSWORD='…' stackloom`.
4. It starts the dashboard on 127.0.0.1 and opens it in your browser.

At the first sign-in STACKLOOM asks for a new password (at least 10 characters,
not containing the username) and refuses every other request until you set one.
The first-run password works only for that step. If you forget your password, run
`stackloom admin reset-password admin` in a terminal.

## Bring in existing projects

```bash
stackloom import researchos ~/Desktop/Claude/ResearchOS   # projects and port assignments
stackloom discover                                         # what is not registered yet
stackloom discover --adopt ~/Code/new-app                  # register one
```

The import only reads the ResearchOS files. Use one of the two admins to start
and stop a given app, not both.

## Keep coding agents up to date

While the dashboard runs, STACKLOOM checks once a minute which projects you
opened in Claude Code and refreshes their CodeCortex maps. To refresh at the
moment a session starts, even with the dashboard closed, add the hook:

```bash
stackloom agent hook install     # adds one SessionStart entry to ~/.claude/settings.json
stackloom agent hook uninstall   # removes only that entry
```

The hook returns in about 0.15 s and the refresh runs in the background, so a
session never waits for it. The first map of a project is a full build (a few
seconds for most projects, a few minutes for very large ones); after that only
changed files are parsed.

## Dashboard address and port

`stackloom` reuses a running dashboard. The port comes from `--port`, then
`STACKLOOM_PORT`, then the last port used, then the highest free port in the pool
(4100–4999 by default). `stackloom dashboard` prints the address and
`stackloom dashboard --stop` stops it.

## Uninstall

```bash
stackloom agent hook uninstall
stackloom dashboard --stop
pipx uninstall stackloom
rm -rf ~/.stackloom            # settings, registry, logs
```

Project maps stay in each project's `.codecortex/` folder; delete those folders
too if you no longer want them.
