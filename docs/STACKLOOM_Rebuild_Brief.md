# STACKLOOM
## Unified Development Operating System
### Complete Product Vision, Architecture and Rebuild Brief

**Product name:** STACKLOOM  
**Tagline:** One workspace. Every project. Complete control.  
**Product category:** Local Development Operating System  
**Primary package name:** `stackloom`  
**Primary CLI command:** `stackloom`  
**Deployment model:** Local-first, self-hosted, lightweight  
**Primary platform:** macOS initially, with architecture designed for Linux and Windows compatibility.

---

# 1. Product Vision

STACKLOOM is a unified Development Operating System designed to manage an entire development workspace from one central application.

Modern development environments often contain numerous independent projects, applications, APIs, databases, Docker containers, background workers, frontend applications, and supporting services. Each project may use different technologies, dependencies, ports, runtime configurations, and startup procedures.

Managing this environment becomes increasingly difficult as the number of projects grows.

STACKLOOM aims to solve this problem by providing a single control center for the entire development workspace.

Think of STACKLOOM as a combination of:

- **cPanel:** Comprehensive management of projects, applications, services, configurations, and system operations.
- **phpMyAdmin:** A unified interface for discovering, connecting to, and administering databases.
- **Docker Desktop:** Centralized container, image, volume, network, and Compose management.
- **GitHub-style interface:** A clean, familiar developer dashboard with repositories, navigation, activity, and project organization.
- **Code intelligence platform:** Centralized CodeCortex integration for code analysis, project maps, dependency graphs, and visualization.
- **Development control center:** A single place to start, stop, monitor, configure, troubleshoot, and maintain applications.

STACKLOOM should work for both technical developers and non-technical Claude Code application developers.

A user should not need to remember which terminal command starts a project, which port an application uses, where its database is running, or how to access its logs.

The goal is simple:

**Install STACKLOOM, run one command, open the dashboard, and manage the entire development workspace.**

This is not intended to be another heavyweight IDE or cloud development platform. It should be a lightweight, fast, local operating layer that coordinates existing projects and tools.

---

# 2. Core Architectural Decisions

The following decisions are confirmed and must be respected throughout implementation.

| Area | Decision |
|---|---|
| Product scope | Entire development workspace |
| CodeCortex | One centralized installation |
| CodeCortex project maps | One independent map per project |
| Project structure | Existing structures must be preserved |
| Runtime management | Centralized |
| Docker management | Workspace-wide |
| Database management | Unified multi-database administration |
| Interface | GitHub-inspired, similar to ResearchOS |
| Deployment | Local-first |
| Installation | PyPI and Homebrew |
| Performance | Extremely lightweight and fast |
| Operating model | One command to install, one command to launch |

### 2.1 Non-negotiable principles

1. Never duplicate CodeCortex engines across projects.
2. Never force projects into a new directory structure.
3. Never modify project source code merely to register or manage it.
4. Preserve each project's independent Git repository and dependencies.
5. Detect and manage existing Docker environments instead of recreating them unnecessarily.
6. Support existing services and databases without requiring users to migrate them.
7. Keep STACKLOOM itself independent from the projects it manages.
8. Prefer native system tools and existing runtimes over unnecessary dependencies.
9. Do not introduce heavyweight infrastructure when a lightweight alternative exists.
10. Every operation must have an appropriate status, result, and error message.

---

# 3. Workspace Discovery and Project Management

STACKLOOM must understand the entire development workspace, not just a manually maintained project list.

## 3.1 Automatic project discovery

Scan the configured workspace and discover projects using recognizable indicators, including:

- `.git`
- `package.json`
- `pnpm-workspace.yaml`
- `yarn.lock`
- `pyproject.toml`
- `requirements.txt`
- `Pipfile`
- `Cargo.toml`
- `go.mod`
- `composer.json`
- `Gemfile`
- `pom.xml`
- `build.gradle`
- `Dockerfile`
- `docker-compose.yml`
- `compose.yaml`
- `.devcontainer`
- `CLAUDE.md`
- Other recognized development configuration files.

Identify:

- Standalone applications
- Monorepos
- Nested repositories
- Frontend and backend projects
- APIs and microservices
- Docker-based applications
- Database-backed applications
- Libraries and packages
- CLI tools
- Documentation and research projects

Avoid treating every directory as a separate project. Understand parent workspaces, nested repositories, and related services.

## 3.2 Project registry

Maintain a centralized project registry.

Each project should have:

- Unique identifier
- Project name
- Description
- Absolute path
- Project type
- Technology stack
- Git repository information
- Runtime information
- Associated services
- Docker Compose configuration, if applicable
- Database connections
- Environment file references
- Ports
- Health-check configuration
- Documentation references
- Project URLs
- CodeCortex map identifier
- Last activity
- Current status

Do not store raw passwords, API keys, or database credentials in the project registry.

## 3.3 Project operations

Every project should have a dedicated management page with the following capabilities:

- Open project directory
- Open project in Claude Code
- Open project in terminal
- Start project
- Stop project
- Restart project
- Run development or production commands
- View logs
- Inspect configuration
- View environment variable names and their configured status
- Manage ports
- View dependencies
- Inspect Git status
- View Docker resources
- View database connections
- Run health checks
- Generate project diagnostics
- Generate project handover reports
- Re-index using CodeCortex
- View project architecture graphs

Projects should be grouped into user-configurable categories.

---

# 4. Docker and Container Management

Docker management is a major feature of STACKLOOM.

The objective is to provide a centralized interface comparable to Docker Desktop and selected cPanel administration capabilities.

STACKLOOM should automatically discover existing Docker environments across the entire workspace.

## 4.1 Docker discovery

Detect and inventory:

- Docker Engine
- Docker Desktop
- Docker Compose
- Dockerfiles
- Compose files
- Running containers
- Stopped containers
- Images
- Volumes
- Networks
- Container registries
- Build configurations
- Project-to-container relationships

Discover Compose projects even when they were started outside STACKLOOM.

Do not assume that all containers belong to STACKLOOM.

Identify containers using Docker labels and Compose metadata wherever possible.

## 4.2 Docker dashboard

Provide a dedicated Docker section showing:

- Docker Engine status
- Docker version
- Total containers
- Running containers
- Stopped containers
- Images
- Volumes
- Networks
- CPU and memory usage where available
- Container health
- Resource consumption
- Recent container activity

Provide filters for running, stopped, unhealthy, and all containers.

## 4.3 Container operations

From the dashboard, users should be able to:

- Start containers
- Stop containers
- Restart containers
- Pause and unpause containers
- Create containers from supported configurations
- Remove containers
- Inspect container configuration
- View container logs
- Follow live logs
- Execute commands inside containers
- Open an interactive terminal
- Inspect environment variables with secret masking
- Inspect port mappings
- Inspect mounted volumes
- Inspect networks
- View health-check status
- Monitor resource usage
- Restart policies
- View container metadata

Destructive operations such as removing containers must require confirmation.

Never automatically remove persistent data or volumes when deleting a container.

## 4.4 Image management

Support:

- List images
- Inspect images
- Pull images
- Build images
- Tag images
- Remove unused images
- View image layers and sizes where supported
- Identify dangling images
- Identify images used by existing containers

## 4.5 Volume management

Support:

- List volumes
- Inspect volumes
- Identify associated containers
- View mount points and metadata
- Create volumes
- Remove unused volumes
- Backup volumes
- Restore volumes

Before deleting a volume, show its associated containers and warn about potential data loss.

## 4.6 Network management

Support:

- List networks
- Inspect networks
- Create networks
- Remove unused networks
- View connected containers
- Inspect network configuration
- Connect and disconnect containers where supported

## 4.7 Docker Compose management

This is particularly important for Claude Code-generated applications.

For every discovered Compose project, provide:

- Compose project name
- Project directory
- Compose file locations
- Services
- Containers
- Port mappings
- Volumes
- Networks
- Environment configuration
- Current status

Provide common operations:

- `up`
- `down`
- `restart`
- `stop`
- `start`
- `build`
- `pull`
- `logs`
- `ps`
- `config`
- `exec`

Also provide controls for individual services.

The interface should make it easy for non-technical users to start an entire application without knowing Docker Compose commands.

STACKLOOM must distinguish between stopping containers and destroying a Compose project with its resources.

Never use `down -v` or equivalent volume-destructive operations without explicit user confirmation.

---

# 5. Unified Database Administration

Database administration should be a first-class feature, inspired by phpMyAdmin.

The objective is to provide a single database control center regardless of whether a database is installed locally, hosted inside Docker, or running as an external service.

Do not restrict database discovery to databases created by STACKLOOM.

## 5.1 Database discovery

Discover database servers and connections using:

- Docker container metadata
- Docker Compose configurations
- Recognized database ports
- Project configuration files
- Environment variable references
- Existing database client configurations
- Manually registered connections

Potential database engines include:

- PostgreSQL
- MySQL
- MariaDB
- SQLite
- MongoDB
- Redis
- Microsoft SQL Server
- Other databases through an extensible adapter system.

Do not assume that a port being open proves a database is available. Validate connections using the relevant protocol or driver.

## 5.2 Database dashboard

Display:

- Database engine
- Connection name
- Host
- Port
- Server version
- Connection status
- Database count
- Storage information where supported
- Associated project
- Docker container association
- Recent activity where available

Provide a unified connection manager.

Users should be able to register databases manually when automatic discovery is insufficient.

## 5.3 Database administration interface

Aim for the usability and depth of phpMyAdmin.

For supported engines, provide:

**Database operations**
- List databases
- Create databases
- Rename databases where supported
- Drop databases
- Inspect database metadata

**Table operations**
- List tables
- Create tables
- Alter tables
- Drop tables
- Browse table contents
- Insert records
- Edit records
- Delete records
- View indexes
- Inspect constraints
- Inspect relationships

**Query editor**
- SQL editor for SQL databases
- Query execution
- Syntax highlighting
- Query history
- Result tables
- Pagination
- Export results
- Execution timing
- Error reporting

For MongoDB and other non-relational databases, provide appropriate native document and collection interfaces rather than forcing SQL concepts onto them.

**Administration**
- Inspect users and roles where supported
- Manage permissions where supported
- Inspect server variables
- View active connections
- View process lists
- Inspect database size
- Backup and restore
- Import and export
- Database health checks

## 5.4 Database connection architecture

Use a modular adapter architecture.

Each database engine should have its own adapter implementing a common interface.

Do not install every database driver by default.

Use optional dependencies or extras so users only install the database drivers they need.

For example:

- `stackloom[postgres]`
- `stackloom[mysql]`
- `stackloom[mongodb]`
- `stackloom[redis]`

The core application must remain lightweight.

## 5.5 Database security

Database access is powerful and must be treated accordingly.

- Never expose database ports publicly by default.
- Store credentials using the operating system's secure credential store where available.
- Never store passwords in plaintext in the project registry.
- Mask credentials in the interface and logs.
- Require confirmation for destructive operations.
- Support read-only connections.
- Clearly distinguish read-only and administrative access.
- Provide database backups before risky operations.
- Use parameterized queries for application-generated operations.
- Apply appropriate access controls to SQL execution and database administration.
- Do not silently change database users, passwords, or permissions.

STACKLOOM should provide comprehensive database administration, but it must not bypass the database's own authentication and permission system.

---

# 6. Centralized Runtime and Service Management

STACKLOOM must manage services across the workspace.

Supported service types should include:

- Node.js
- Next.js
- React
- Vite
- Vue
- Angular
- Python
- FastAPI
- Flask
- Django
- PHP
- Laravel
- Go
- Rust
- Java
- Docker Compose
- Static applications
- Background workers
- Custom commands

## 6.1 Service discovery

Inspect project configuration files and identify likely startup commands.

Examples:

- `npm run dev`
- `pnpm dev`
- `yarn dev`
- `uvicorn app.main:app --reload`
- `python manage.py runserver`
- `php artisan serve`
- `docker compose up`

Do not automatically execute discovered commands without appropriate approval.

## 6.2 Service management

Provide:

- Start
- Stop
- Restart
- Live logs
- Health status
- Port information
- Process information
- Runtime version
- Startup command
- Dependency status
- Resource usage where available

Support multiple services per project.

A project might have:

- Frontend
- Backend API
- Worker
- Scheduler
- Database
- Cache
- Reverse proxy

Represent service dependencies and startup order.

## 6.3 Port management

Implement a centralized port registry.

Requirements:

- Automatic port allocation
- Manual port assignment
- Pinned ports
- Port conflict detection
- Port availability checks
- Service-to-port mapping
- Project-to-port mapping

Use configurable port ranges, with a sensible default range such as 4100–4999.

Support placeholders such as:

`${PORT:frontend}`

`${PORT:backend}`

`${PORT:api}`

Never terminate an unrelated process simply because it occupies a desired port.

Verify process identity before stopping any managed process.

---

# 7. Centralized CodeCortex Integration

CodeCortex is an existing project and must be integrated rather than reimplemented.

STACKLOOM must use one centralized CodeCortex installation.

Do not create separate CodeCortex installations inside individual projects.

## 7.1 Architecture

Separate the CodeCortex engine from project-specific data.

Conceptually:

```text
STACKLOOM/
├── core/
│   └── codecortex/
│       ├── engine/
│       ├── parsers/
│       ├── analyzers/
│       ├── graph/
│       ├── retrieval/
│       └── shared/
│
├── data/
│   └── codecortex/
│       └── project-maps/
│           ├── project-a/
│           ├── project-b/
│           └── project-c/
```

This is a conceptual layout. Inspect the existing CodeCortex repository and reuse its actual architecture where possible.

Shared components:

- Parsers
- Language support
- AST analysis
- CFG analysis
- DFG analysis
- Dependency analysis
- Graph engine
- Retrieval engine
- Indexing engine
- Shared caches where appropriate

Project-specific components:

- Source inventory
- Project index
- Symbol data
- Dependency graph
- Call graph
- Analysis results
- Indexing metadata
- Graph configuration

Each project must have an independent CodeCortex map.

## 7.2 CodeCortex management interface

Provide a dedicated CodeCortex section with:

- Registered projects
- Indexing status
- Last indexing time
- Supported languages
- Indexed files
- Symbols
- Graph statistics
- Indexing errors
- Rebuild controls
- Incremental indexing
- Validation
- Export where supported
- Delete map with confirmation

Allow users to select any registered project and inspect its CodeCortex map.

## 7.3 Interactive Graph Explorer

A major requirement is the ability to view and generate CodeCortex graphs directly from the STACKLOOM interface.

Do not limit this to a static image.

Build an interactive graph exploration experience.

Features should include:

- Generate a graph for a selected project
- View an existing graph without rebuilding it
- Regenerate graphs when required
- Switch graph types where supported
- Force-directed layout
- Hierarchical layout
- Circular layout
- Grid layout
- Zoom and pan
- Search functions, classes, files, and symbols
- Filter nodes by type
- Filter relationships by type
- Inspect node metadata
- Inspect incoming and outgoing relationships
- Highlight dependencies
- Highlight call relationships
- Explore module relationships
- Identify highly connected nodes
- Identify potential hotspots
- Select a node and navigate to its source file
- Export supported graph formats

The interface should clearly distinguish between:

1. CodeCortex indexing
2. Graph generation
3. Graph visualization

Viewing an existing graph must not trigger a full indexing operation.

Use CodeCortex's existing graph data and capabilities. Do not invent graph semantics or duplicate its analysis engine.

## 7.4 Cross-project intelligence

Keep project maps isolated by default.

Optionally provide a future cross-project view for discovering relationships between shared libraries, dependencies, or related applications.

This must not merge independent project maps or compromise their boundaries.

---

# 8. Git and Repository Management

Provide a centralized Git overview for every discovered repository.

Features:

- Repository status
- Current branch
- Changed files
- Untracked files
- Recent commits
- Remote information
- Fetch
- Pull
- Push
- Branch management
- Commit creation
- Diff viewer
- Stash management
- Merge and rebase workflows
- Conflict visibility

Git operations must use the correct repository path.

Initially, read-only Git inspection can be enabled by default. Mutating operations should require explicit user actions and confirmation.

Never assume all projects share the same Git provider or remote.

---

# 9. Environment and Configuration Management

Provide a centralized configuration manager.

Support common configuration formats:

- `.env`
- `.env.local`
- `.env.development`
- `.env.production`
- JSON
- YAML
- TOML
- Application-specific configuration files

Features:

- Discover configuration files
- Show configuration keys
- Mask secret values
- Edit supported configuration files
- Compare environment configurations
- Detect missing required variables
- Identify configuration differences
- Associate configuration with services
- Provide backup before editing

Never expose secrets in logs, diagnostic reports, or ordinary dashboard views.

Do not automatically copy production credentials into development environments.

---

# 10. Dashboard and User Interface

The dashboard must have a GitHub-inspired visual language, similar in overall feel to the existing ResearchOS interface.

The goal is a clean, modern, structured developer administration interface.

Reference:

**GitHub-inspired admin dashboard reference:**

https://github.com/Corporationakht/LocalCodeCli/blob/main/assets/admin-page.png

Use this screenshot as a visual reference for:

- Navigation hierarchy
- Dashboard composition
- Project presentation
- Information density
- Administrative controls
- Status visibility
- Content organization

Do not copy the screenshot literally. STACKLOOM must have its own visual identity.

Also inspect the existing ResearchOS interface and reuse successful UI patterns where appropriate.

## 10.1 Design principles

- GitHub-inspired layout
- Professional developer-tool appearance
- Light mode first
- Dark mode architecture supported for later
- Compact but readable
- Clear typography
- Consistent spacing
- Minimal visual clutter
- Fast navigation
- Responsive layout
- Strong information hierarchy
- Clear status indicators
- Accessible controls

Avoid excessive gradients, decorative cards, oversized headings, and unnecessary animations.

The application should feel like a mature development administration platform.

## 10.2 Main navigation

Suggested sidebar:

```text
STACKLOOM

Overview

WORKSPACE
  Projects
  Groups
  Discovery
  Recent Activity

RUNTIME
  Services
  Ports
  Processes
  Logs

DOCKER
  Overview
  Containers
  Compose Projects
  Images
  Volumes
  Networks

DATABASES
  Connections
  Database Explorer
  Query Editor
  Backups

CODE INTELLIGENCE
  CodeCortex
  Project Maps
  Graph Explorer

DEVELOPMENT
  Git Repositories
  Environment
  Terminal
  Diagnostics

SYSTEM
  Tasks
  Notifications
  Settings
  Security
  About
```

Navigation can evolve after inspecting the existing ResearchOS UI.

## 10.3 Overview dashboard

The main dashboard should provide an immediate understanding of the entire development environment.

Suggested widgets:

- Total projects
- Active projects
- Running services
- Running containers
- Database connections
- Active ports
- CodeCortex indexed projects
- System resource usage
- Recent activity
- Service health
- Docker health
- Database health
- Projects requiring attention

Provide quick actions:

- Add project
- Discover projects
- Start project
- Open Docker
- Open database manager
- Explore CodeCortex
- Run diagnostics

Do not overwhelm the user with all information at once. Prioritize the most useful operational information.

## 10.4 Project detail page

Each project should have a comprehensive overview with tabs or sections for:

- Overview
- Services
- Docker
- Databases
- Git
- Environment
- CodeCortex
- Logs
- Files
- Settings

The project page should connect related resources.

For example, a Dockerized application should show its containers, Compose services, database connections, exposed ports, and CodeCortex map together.

---

# 11. Non-Technical User Experience

STACKLOOM must not assume that every user understands Docker, databases, terminals, or application runtimes.

A Claude Code user should be able to manage projects through understandable actions.

Examples:

Instead of requiring:

`docker compose up -d`

Provide:

**Start Application**

Instead of requiring:

`docker compose logs -f backend`

Provide:

**View Backend Logs**

Instead of requiring users to identify database ports manually, provide:

**Discover Database Connections**

Instead of requiring users to understand indexing commands, provide:

**Build Project Map**

Provide a guided workflow for:

1. Discovering a project
2. Registering it
3. Identifying its technologies
4. Detecting services
5. Detecting Docker resources
6. Discovering database connections
7. Building its CodeCortex map
8. Starting the application

Show technical details when needed, but keep common operations simple.

Provide clear explanations for errors and actionable suggestions.

---

# 12. CLI and Terminal Integration

The CLI should be powerful but simple.

Primary commands:

```bash
stackloom
stackloom start
stackloom stop
stackloom restart
stackloom status
stackloom doctor
stackloom discover
stackloom projects
stackloom docker
stackloom databases
stackloom codecortex
stackloom logs
stackloom update
```

Examples:

```bash
stackloom
```

Launch the dashboard.

```bash
stackloom start my-project
```

Start a project.

```bash
stackloom status
```

Show the workspace status.

```bash
stackloom doctor
```

Run diagnostics.

```bash
stackloom discover
```

Scan and discover projects.

```bash
stackloom docker
```

Show Docker status and resources.

```bash
stackloom codecortex map my-project
```

Inspect the project's CodeCortex map.

CLI and UI must use the same backend services and registry. Avoid maintaining separate business logic.

Provide an integrated terminal experience where practical, but do not make a full terminal emulator a prerequisite for the first release.

---

# 13. Installation and First-Run Experience

This is one of the most important product requirements.

STACKLOOM must be extremely easy to install and launch.

A user should not need to manually configure Python environments, install a frontend, configure a database, or edit several configuration files.

## 13.1 PyPI installation

Target:

```bash
pip install stackloom
```

Or preferably:

```bash
pipx install stackloom
```

The package should install the CLI and required backend dependencies.

The first launch should:

1. Check the environment.
2. Identify the operating system.
3. Check available runtimes.
4. Check Docker availability.
5. Initialize the STACKLOOM home directory.
6. Initialize the lightweight internal database.
7. Create the administrator account.
8. Discover the configured development workspace.
9. Start the local backend.
10. Open the dashboard in the browser.

## 13.2 Homebrew installation

Provide a Homebrew formula or tap so macOS users can install STACKLOOM using a simple command.

Target experience:

```bash
brew install stackloom
stackloom
```

The actual formula and package publishing strategy must be validated before release.

## 13.3 One-command startup

The normal user experience should be:

```bash
stackloom
```

This command should:

- Start the local service if it is not already running.
- Check whether another STACKLOOM instance is active.
- Perform lightweight health checks.
- Start the dashboard.
- Open the browser when appropriate.
- Avoid creating duplicate backend processes.

Provide optional commands for headless operation and custom ports.

## 13.4 First-run administrator account

Requested initial administrator credentials:

```text
Username: admin
Password: 1234567890@
```

Implementation requirements:

- Use these as the first-run bootstrap credentials.
- Require a password change on the first successful login.
- Allow a secure environment-variable override for initial setup.
- Hash passwords using a suitable password-hashing algorithm such as Argon2id.
- Never store the password in plaintext.
- Never print the password in logs.
- Protect the setup process against repeated unauthorized account creation.
- Bind the dashboard to localhost by default.

Do not use a permanently shared default administrator password in production releases.

## 13.5 Dependency philosophy

Keep installation lightweight.

The base installation should not automatically install:

- Docker Engine
- Database servers
- Multiple database drivers
- Large AI models
- Heavy graph-processing libraries
- Unnecessary frontend development dependencies

Detect and integrate existing system installations.

Use optional dependencies for features that require additional libraries.

Do not bundle large external applications when STACKLOOM can communicate with an existing installation.

---

# 14. Lightweight Architecture and Performance

STACKLOOM must be designed as a lightweight local control plane.

Performance is a core product requirement, not an optional optimization.

## 14.1 Backend

Recommended:

- Python 3.11+
- FastAPI or an equally lightweight API framework
- SQLite for internal state and metadata
- Async operations where appropriate
- Native subprocess management
- Docker Engine API or Docker CLI integration
- Modular service adapters

Reuse the existing CodeCortex engine rather than rebuilding it.

## 14.2 Frontend

Recommended:

- React
- TypeScript
- Next.js only if its benefits justify its runtime overhead
- Lightweight component library or carefully selected UI primitives
- Efficient graph visualization library
- Minimal client-side dependencies

Consider a prebuilt static frontend so normal users do not need Node.js simply to run STACKLOOM.

The production installation must not require a frontend development server.

## 14.3 Performance requirements

Set measurable targets and benchmark them on a normal developer machine.

Initial targets:

- Fast CLI startup
- Dashboard available within a few seconds on a warm start
- Low idle CPU usage
- Low baseline memory consumption
- No continuous full-workspace scanning
- No unnecessary background polling
- Incremental discovery and indexing
- Lazy loading of heavy dashboard sections
- Efficient database queries
- Bounded log buffers
- Controlled background task concurrency

Do not load CodeCortex analysis engines until required.

Do not initialize Docker integrations when Docker is unavailable.

Do not load database adapters that are not installed or needed.

Use caching intelligently, with explicit invalidation when project configurations change.

---

# 15. Security and Operational Safety

STACKLOOM is a powerful local administration tool.

It can control projects, processes, containers, databases, and files. Security must therefore be treated as a core architectural requirement.

Requirements:

- Localhost-only binding by default.
- Authentication for administrative actions.
- Secure password hashing.
- CSRF protection where applicable.
- Host header validation.
- Secure session management.
- Command approval for potentially unsafe operations.
- Process identity verification before termination.
- Secret redaction.
- Safe path handling.
- Protection against directory traversal.
- Confirmation for destructive operations.
- Backups before high-risk changes.
- Audit logs for administrative operations.
- Explicit permission boundaries for remote access.
- No unrestricted shell execution through unauthenticated endpoints.

The UI should distinguish routine operations from destructive operations.

Examples of high-risk operations:

- Deleting databases
- Dropping tables
- Removing Docker volumes
- Deleting images in use
- Removing containers
- Terminating processes
- Overwriting configuration files
- Executing arbitrary SQL
- Running arbitrary shell commands

Require appropriate confirmation and, where practical, show the consequences before execution.

---

# 16. Backup, Restore and Recovery

Provide a centralized backup manager.

Support backups for:

- STACKLOOM registry
- Internal SQLite database
- Project configuration files
- Docker volumes
- Supported databases
- CodeCortex project maps
- STACKLOOM settings

Provide:

- Manual backups
- Scheduled backups
- Backup history
- Restore workflows
- Backup verification
- Retention settings
- Export and import

Never assume that backing up a Docker container automatically backs up its persistent data.

Make backup scope explicit.

---

# 17. Notifications, Tasks and Activity

Provide a centralized activity system.

Track events such as:

- Project started
- Project stopped
- Service failed
- Container became unhealthy
- Database connection lost
- Port conflict detected
- CodeCortex indexing completed
- Backup completed
- Configuration changed
- Destructive operation performed

Provide a background task manager for long-running operations.

Examples:

- Docker image builds
- Database backups
- Database restores
- CodeCortex indexing
- Graph generation
- Project discovery
- Diagnostics

Display task status, progress where available, logs, completion state, and errors.

Do not block the dashboard while these operations run.

---

# 18. STACKLOOM Branding and Logo

Create a distinctive visual identity for STACKLOOM.

The name combines the idea of a development stack with a loom that brings multiple components together.

The logo should communicate:

- Connected projects
- Multiple technologies
- Unified development environment
- Structured systems
- Intelligence and orchestration

Avoid generic cloud icons, generic gear icons, or an overly literal computer illustration.

Explore a geometric symbol inspired by interwoven layers, connected nodes, or an abstract stack.

The logo should be:

- Minimal
- Distinctive
- Modern
- Recognizable at small sizes
- Suitable for a developer tool
- Appropriate for both light and dark backgrounds

Deliver:

1. Primary logo with wordmark
2. Standalone symbol
3. Monochrome version
4. Light-background version
5. Dark-background version
6. Application icon
7. Favicon
8. SVG source files
9. PNG exports in appropriate sizes
10. A short brand and color specification

The logo must be original and must not imitate GitHub, Docker, phpMyAdmin, or other existing brands.

Use the logo consistently in the application, CLI welcome screen, documentation, PyPI project page, and Homebrew presentation.

---

# 19. Recommended Internal Structure

The following is a conceptual architecture, not a mandatory directory structure. Inspect existing repositories before deciding how to organize the implementation.

```text
STACKLOOM/
│
├── stackloom/
│   ├── cli/
│   ├── api/
│   ├── core/
│   │   ├── workspace/
│   │   ├── projects/
│   │   ├── runtime/
│   │   ├── processes/
│   │   ├── ports/
│   │   ├── docker/
│   │   ├── databases/
│   │   ├── git/
│   │   ├── environment/
│   │   ├── codecortex/
│   │   ├── security/
│   │   ├── backups/
│   │   └── tasks/
│   │
│   ├── adapters/
│   │   ├── runtimes/
│   │   ├── databases/
│   │   ├── docker/
│   │   └── integrations/
│   │
│   ├── models/
│   ├── services/
│   └── utilities/
│
├── frontend/
│
├── assets/
│   ├── logo/
│   └── icons/
│
├── docs/
│   ├── INVENTORY.md
│   ├── ARCHITECTURE.md
│   ├── INSTALLATION.md
│   ├── SECURITY.md
│   ├── USER_GUIDE.md
│   ├── API.md
│   └── CHANGELOG.md
│
├── tests/
│
├── pyproject.toml
└── README.md
```

Runtime data should be stored separately from the installed package, in an operating-system-appropriate application data directory.

Conceptually:

```text
~/.stackloom/
├── config/
├── registry/
├── database/
├── state/
├── logs/
├── backups/
├── tasks/
└── codecortex/
    └── project-maps/
```

Do not place user data inside the Python package installation directory.

---

# 20. Implementation Strategy

Do not attempt to build every feature in one pass.

First inspect the existing workspace and repositories.

In particular, inspect:

1. ResearchOS and its service-management implementation.
2. The existing CodeCortex repository and integration interfaces.
3. Existing projects and their runtime configurations.
4. Existing Docker environments and Compose projects.
5. Existing database servers and connection patterns.
6. Existing frontend and backend technology choices.

Create:

`docs/INVENTORY.md`

Document what already exists, what can be reused, and what needs to be developed.

Do not modify or restructure existing projects during this inspection phase.

## Phase 0: Discovery and Architecture

- Inspect the workspace.
- Inspect ResearchOS.
- Inspect CodeCortex.
- Inventory projects.
- Inventory Docker resources.
- Identify database engines.
- Identify existing runtime and port configurations.
- Prepare the architecture.
- Identify reuse opportunities.
- Document risks and dependencies.

Produce an implementation plan before making substantial changes.

## Phase 1: STACKLOOM Core

- CLI
- Application bootstrap
- Internal SQLite database
- Project registry
- Workspace discovery
- Authentication
- Configuration management
- Logging
- Task manager
- Lightweight API

## Phase 2: Workspace and Runtime Management

- Project dashboard
- Service discovery
- Start and stop operations
- Process management
- Port management
- Health checks
- Logs
- Project details

## Phase 3: Docker Management

- Docker discovery
- Container dashboard
- Compose project discovery
- Container operations
- Image management
- Volume management
- Network management
- Resource monitoring
- Container terminal and logs

## Phase 4: Database Administration

- Database discovery
- Connection manager
- PostgreSQL adapter
- MySQL/MariaDB adapter
- SQLite support
- Database explorer
- Query editor
- Backup and restore
- Additional adapters

Prioritize a reliable core and extend through adapters.

## Phase 5: CodeCortex

- Centralized engine integration
- Independent project maps
- Indexing management
- Incremental indexing
- Graph generation
- Interactive graph explorer
- Project-level code intelligence

## Phase 6: Git, Configuration and Diagnostics

- Git dashboard
- Configuration manager
- Environment comparison
- Diagnostics
- Project handover reports
- Backup and restore

## Phase 7: Packaging and Release

- PyPI package
- Homebrew formula or tap
- Installation testing
- Upgrade and migration testing
- Documentation
- Branding
- Logo and icons
- Release automation

---

# 21. Testing Requirements

Test STACKLOOM with realistic development environments.

Include:

- Node.js frontend and backend projects
- Python API projects
- Monorepos
- Docker Compose applications
- PostgreSQL containers
- MySQL containers
- SQLite projects
- MongoDB where supported
- Projects with multiple services
- Projects with conflicting ports
- Projects with missing environment variables
- Projects with invalid startup commands
- Projects with nested Git repositories
- Projects with no Docker configuration
- Projects that are already running outside STACKLOOM

Test destructive-operation protections.

Test that STACKLOOM never accidentally stops unrelated processes or deletes unrelated Docker resources.

Test that the dashboard remains responsive while indexing, building images, backing up databases, or running diagnostics.

Test installation in a clean environment using the intended PyPI and Homebrew workflows.

---

# 22. Definition of Done

STACKLOOM's first stable release should satisfy the following:

- [ ] Installs through a straightforward PyPI workflow.
- [ ] Has a working Homebrew installation path.
- [ ] Starts through one CLI command.
- [ ] Opens a local authenticated dashboard.
- [ ] Has a distinctive original logo and visual identity.
- [ ] Uses a GitHub-inspired dashboard design.
- [ ] Discovers projects across the workspace.
- [ ] Manages multiple services per project.
- [ ] Tracks and allocates ports safely.
- [ ] Discovers existing Docker environments.
- [ ] Manages Docker containers and Compose projects.
- [ ] Manages images, volumes, and networks.
- [ ] Discovers and connects to supported databases.
- [ ] Provides a practical database administration interface.
- [ ] Integrates one centralized CodeCortex engine.
- [ ] Maintains independent CodeCortex maps per project.
- [ ] Generates and displays interactive CodeCortex graphs.
- [ ] Provides centralized Git and configuration views.
- [ ] Has logs, diagnostics, backups, and task tracking.
- [ ] Protects credentials and destructive operations.
- [ ] Remains lightweight and responsive.
- [ ] Does not require changes to existing project structures.

---

# 23. Instructions to the Coding Agent

You are building STACKLOOM, a unified Development Operating System.

Do not treat this as a simple dashboard or project launcher.

The goal is to create a polished, lightweight local administration platform that brings workspace management, application runtime management, Docker administration, database administration, and CodeCortex intelligence into one coherent product.

Follow these instructions carefully:

1. Inspect before implementing.
2. Reuse existing ResearchOS capabilities where appropriate, without making STACKLOOM dependent on ResearchOS.
3. Inspect and integrate the existing CodeCortex implementation. Do not create another CodeCortex engine.
4. Maintain one independent CodeCortex map per project.
5. Discover and manage existing Docker resources rather than assuming all resources were created by STACKLOOM.
6. Design database integrations through modular adapters.
7. Make the application usable by both technical and non-technical Claude Code developers.
8. Follow the GitHub-inspired UI direction and inspect the supplied dashboard reference.
9. Create an original STACKLOOM logo and brand assets.
10. Keep the installation and startup experience extremely simple.
11. Prioritize lightweight architecture, fast startup, low idle resource consumption, and responsive UI.
12. Avoid unnecessary dependencies and heavyweight background services.
13. Never compromise security for convenience.
14. Do not silently perform destructive operations.
15. Preserve all existing projects, repositories, data, and configurations.
16. Maintain documentation and tests throughout development.

**Most importantly, do not build an unnecessarily complicated system.** STACKLOOM should feel simple to use on the surface, while providing powerful capabilities underneath.

The ideal experience is that a user installs STACKLOOM, runs `stackloom`, opens the dashboard, and immediately has a clear picture of their entire development environment.

They should be able to manage their projects, containers, databases, services, and code intelligence without jumping between multiple tools and terminal windows.

**STACKLOOM is intended to become the operating system for the development workspace.**
