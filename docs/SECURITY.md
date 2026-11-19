# STACKLOOM security notes

STACKLOOM can see every project in your workspace and will later start
processes, containers and database sessions. These are the rules it follows now.

## Network

- The dashboard binds to 127.0.0.1 only.
- Requests whose `Host` header is not `127.0.0.1`, `localhost` or `[::1]` get
  HTTP 421. This blocks DNS-rebinding attacks from web pages.
- Responses carry a strict Content-Security-Policy (`default-src 'self'`,
  `frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff` and
  `Referrer-Policy: no-referrer`. API responses are not cached.
- The dashboard loads no external scripts, fonts or images.

## Accounts and sessions

- Passwords are hashed with Argon2id (19 MiB, 2 passes, 1 lane; OWASP's
  recommended minimum). Older hashes are upgraded at the next sign-in.
- The first administrator is created once, in a locked transaction, only when no
  account exists. Its first-run password must be changed before anything else
  works.
- After five failed sign-ins for a username, each further attempt waits longer
  (up to five minutes).
- Sessions are random 256-bit tokens in an HttpOnly, SameSite=Strict cookie; the
  database stores only their SHA-256. They expire after 12 hours.
- Every request that changes something must carry the session's CSRF token in
  `X-CSRF-Token`.
- Sign-ins, password changes, registrations, scans and map refreshes are written
  to the activity log with the user, target and result.

## Data

- `~/.stackloom` is created with mode 700 and the database with mode 600.
- The registry refuses entries that look like credentials (tokens, keys,
  passwords in URLs). Env files are recorded by name only; their values are never
  read into the registry or shown.
- Logs, task output and activity details pass through a redaction filter for
  tokens, passwords, keys and credentials in URLs.
- STACKLOOM writes nothing into registered projects except CodeCortex maps in
  `<project>/.codecortex/`, which carries its own `.gitignore`.
- Reading Claude Code's session folders, STACKLOOM reads only the `cwd` field of
  the newest session file. Conversation content is never read.

## Processes

- Child processes are started from argument lists, never through a shell.
- A recorded process ID is trusted only while its kernel start time still
  matches, so a reused PID is never mistaken for STACKLOOM's.
- Map refreshes refuse the home folder, the filesystem root, folders without code
  markers, folders that hold other projects, and folders with more than 50,000
  files.

## Docker

- Removing a container never removes its volumes. `compose down` keeps volumes
  unless "remove with volumes" is chosen and confirmed a second time.
- A volume attached to a container, an image a container uses, and the built-in
  networks cannot be removed.
- Container environment values that look secret are masked in the configuration view.
- Running a command inside a container needs confirmation, runs without a shell
  or TTY, has a 60-second limit, and is written to the activity log.
- Names passed to Docker are checked against a strict pattern, so nothing typed
  can become an extra option.

## Databases

- Passwords are never stored in STACKLOOM's database. They come from the macOS
  keychain, the project's own env file (read at connect time), or memory.
- Connections are read-only by default. A read-only connection is enforced by the
  database itself (`mode=ro` for SQLite, `READ ONLY` sessions for PostgreSQL and
  MySQL), not only by the dashboard.
- The query editor runs one statement at a time. On an administrative connection,
  anything other than a read needs confirmation, and is audited.
- Statements STACKLOOM writes itself (browse, row edits, drops) use parameters for
  values and check table and column names against the live schema before quoting them.
- Dropping a table or a database makes a backup first. Users, roles and
  permissions are shown but never changed.

## Git and files

- Git writes (commit, pull, push, branch, stash, abort) need confirmation. Pull is
  fast-forward only. Paths are checked to stay inside the repository.
- Diffs and handover reports pass through the redaction filter.
- Environment files: values of secret-looking keys are never sent to the browser;
  comparisons use checksums; every edit is preceded by a backup, and the file keeps
  its permissions.
- Graph source excerpts are read only from files inside the project.

## Reporting a problem

Contact Nafees Mansoor through <https://www.nafees.info>.
