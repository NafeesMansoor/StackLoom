import { useState } from "react";
import { api, type MapRecord } from "../api";
import { withConfirm } from "../actions";
import { Box, DataTable, NoteView, StatePill, Tabs, useAction } from "../components";
import { ago, bytes, mapPill, when } from "../format";
import { useApi, useText } from "../hooks";
import { Empty, ErrorNote, Loading, PageHead, Pill } from "../ui";

interface Detail {
  id: string; name?: string; group: string; kind?: string; path: string; source: string; runtime?: string;
  stack?: string[]; components?: { name: string; stack: string[] }[]; nested_repos?: string[]; docs?: string[];
  notes?: string; safe_to_launch?: boolean; launch?: { type: string }; map: MapRecord; created_at: string;
  dependencies?: Record<string, { name: string; version: string }[]>;
}

const TABS: [string, string][] = [["overview", "Overview"], ["runtime", "Runtime"], ["docker", "Docker"], ["databases", "Databases"],
  ["environment", "Environment"], ["codecortex", "CodeCortex"], ["logs", "Logs"], ["diagnostics", "Checks"]];

export function Project({ id, tab = "overview" }: { id: string; tab?: string }) {
  const { data, error, loading, reload } = useApi<Detail>(`/api/projects/${encodeURIComponent(id)}`, (d) => d.map.status === "refreshing", 2000);
  const act = useAction(reload);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error || "Not found."} onRetry={reload} />;
  const go = (t: string) => { window.location.hash = `#/projects/${encodeURIComponent(id)}${t === "overview" ? "" : `/${t}`}`; };
  const open = (target: string) => act.run(`Open in ${target}`, () => api.post(`/api/projects/${encodeURIComponent(id)}/open`, { target }), "Opened.");
  return (
    <>
      <p className="small"><a href="#/projects">Projects</a> / {data.group}</p>
      <PageHead title={data.name || data.id} lede={<span className="path">{data.path}</span>}>
        <button className="btn" onClick={() => open("folder")}>Open folder</button>
        <button className="btn" onClick={() => open("terminal")}>Terminal</button>
        <button className="btn" onClick={() => open("vscode")}>VS Code</button>
        <button className="btn btn-primary" onClick={() => open("claude")}>Open in Claude Code</button>
      </PageHead>
      <NoteView note={act.note} />
      <Tabs value={tab} onChange={go} tabs={TABS} />
      {tab === "overview" && <Overview data={data} onMove={() => { const g = window.prompt("Move to which group?", data.group);
        if (g) act.run("Move project", () => api.post(`/api/projects/${encodeURIComponent(id)}/group`, { path: g }), `Moved to ${g}.`); }} />}
      {tab === "runtime" && <Runtime id={id} />}
      {tab === "docker" && <ProjectDocker id={id} />}
      {tab === "databases" && <ProjectDatabases id={id} />}
      {tab === "environment" && <Environment id={id} />}
      {tab === "codecortex" && <CodeCortex data={data} reload={reload} />}
      {tab === "logs" && <Logs id={id} />}
      {tab === "diagnostics" && <Checks id={id} launchEnabled={!!data.safe_to_launch} hasLaunch={!!data.launch} reload={reload} />}
    </>
  );
}

function Overview({ data, onMove }: { data: Detail; onMove: () => void }) {
  const stack = data.stack?.length ? data.stack : data.runtime ? [data.runtime] : [];
  const git = useApi<{ status: { branch: string; changed: unknown[]; untracked: unknown[] }; log: { subject: string; date: string }[] }>(
    `/api/git/${encodeURIComponent(data.id)}`);
  const changes = git.data ? git.data.status.changed.length + git.data.status.untracked.length : 0;
  const [label, tone] = mapPill(data.map.status);
  return (
    <div className="cols">
      <Box title="About">
        <div className="box-body">
          <dl className="kv">
            <dt>ID</dt><dd className="mono">{data.id}</dd>
            <dt>Group</dt><dd>{data.group} <button className="btn btn-sm" onClick={onMove}>Move</button></dd>
            <dt>Kind</dt><dd>{data.kind ?? "-"}</dd>
            <dt>Stack</dt><dd><div className="chips">{stack.length ? stack.map((s) => <span className="chip" key={s}>{s}</span>) : "Not detected"}</div></dd>
            {data.components?.length ? <><dt>Components</dt><dd>{data.components.map((c) => (
              <div key={c.name}><span className="mono">{c.name}/</span> <span className="muted small">{c.stack.join(", ") || "-"}</span></div>))}</dd></> : null}
            {data.nested_repos?.length ? <><dt>Nested repositories</dt><dd>{data.nested_repos.map((r) => <div className="path" key={r}>{r}</div>)}</dd></> : null}
            {data.docs?.length ? <><dt>Docs</dt><dd>{data.docs.map((d) => <div className="path" key={d}>{d}</div>)}</dd></> : null}
            <dt>Registered</dt><dd>{when(data.created_at)} <span className="muted small">from {data.source}</span></dd>
            {data.notes && <><dt>Notes</dt><dd>{data.notes}</dd></>}
          </dl>
        </div>
      </Box>
      <div>
        {data.dependencies && Object.keys(data.dependencies).length > 0 && (
          <Box title="Dependencies">
            {Object.entries(data.dependencies).map(([file, items]) => (
              <details key={file} className="box-body small" style={{ borderTop: "1px solid var(--line)", paddingTop: 8, paddingBottom: 8 }}>
                <summary>{file} <span className="muted">({items.length})</span></summary>
                {items.map((d) => <div key={d.name} className="mono">{d.name} <span className="muted">{d.version}</span></div>)}
              </details>))}
          </Box>)}
        <Box title="Code map" actions={<Pill label={label} tone={tone} />}>
          <div className="box-body small">{data.map.status === "ready" ? `${data.map.stats.nodes} symbols in ${data.map.stats.files} files, refreshed ${ago(data.map.last_refresh)}.`
            : "No map yet. Build it on the CodeCortex tab."}</div>
        </Box>
        <Box title="Git" actions={git.data && <a className="small" href={`#/git/${encodeURIComponent(data.id)}`}>Open</a>}>
          <div className="box-body small">{git.loading ? "Reading…" : git.error || !git.data ? "Not a Git repository." : <>
            <span className="mono">{git.data.status.branch}</span> · {changes || "no"} uncommitted changes
            {git.data.log[0] && <div className="muted">Last commit {ago(git.data.log[0].date)}: {git.data.log[0].subject}</div>}
          </>}</div>
        </Box>
      </div>
    </div>
  );
}

interface RuntimeData {
  status: { state: string; detail?: string; processes?: Record<string, number>; containers?: Record<string, string>; since?: string; owners?: Record<string, { pid: number; command: string }[]> };
  services: { name: string; port: number | null; pinned: boolean; url: string | null; compose_service?: string }[];
  health: Record<string, string>; commands: { name: string; command: string[]; cwd: string }[]; approved: boolean; launch_enabled: boolean;
  task: { id: number; kind: string } | null;
}

function Runtime({ id }: { id: string }) {
  const { data, error, loading, reload } = useApi<RuntimeData>(`/api/projects/${encodeURIComponent(id)}/runtime`, (d) => !!d.task, 2000);
  const act = useAction(reload);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  const st = data.status.state;
  const up = ["running", "partial"].includes(st);
  const base = `/api/projects/${encodeURIComponent(id)}`;
  if (!data.commands.length) return <Empty>This project has no start command. Projects found by discovery get one suggested when their stack is recognised.</Empty>;
  return (
    <>
      <NoteView note={act.note} />
      {data.status.detail && <div className={`notice notice-${st === "external" ? "info" : "warn"}`}>{data.status.detail}</div>}
      <Box title={<span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>Status <StatePill state={st} /></span>} actions={<>
        {up ? <>
          <button className="btn" disabled={!!act.busy} onClick={() => act.run("Restart", () => api.post(`${base}/restart`))}>Restart</button>
          <button className="btn" disabled={!!act.busy} onClick={() => act.run("Stop", () => api.post(`${base}/stop`))}>Stop</button>
        </> : st !== "external" && (data.launch_enabled
          ? <button className="btn btn-primary" disabled={!!act.busy} onClick={() => act.run("Start", () => withConfirm((approve) => api.post(`${base}/start`, { approve })))}>
              {data.approved ? "Start" : "Approve and start"}</button>
          : <button className="btn" onClick={() => act.run("Turn on launching", () => withConfirm(async (confirm) => {
              if (!confirm && !window.confirm("Let STACKLOOM run this project's start command (shown below)?")) return null;
              return api.post(`${base}/launch`, { enabled: true, confirm: true });
            }), "Launching turned on. Start it when ready.")}>Turn on launching</button>)}
      </>}>
        <div className="box-body">
          {data.status.since && <p className="small muted" style={{ marginTop: 0 }}>Running since {when(data.status.since)}</p>}
          <div className="small muted">Start command {data.approved ? "(approved)" : "(you will be asked to approve it once)"}</div>
          <pre className="log">{data.commands.map((c) => `[${c.name}] ${c.command.join(" ")}\n    in ${c.cwd}`).join("\n")}</pre>
          {data.status.containers && Object.keys(data.status.containers).length > 0 && (
            <div className="chips" style={{ marginTop: 8 }}>{Object.entries(data.status.containers).map(([k, v]) => <span key={k} className="chip">{k}: {v}</span>)}</div>)}
        </div>
      </Box>
      <Box title="Services and ports">
        <DataTable columns={["Service", "Port", "Address", "Health", ""]} empty="No services declared." rows={data.services.map((s) => [
          <span className="mono">{s.name}</span>,
          <span className="mono">{s.port ? `${s.port}${s.pinned ? " (pinned)" : ""}` : "assigned at first start"}</span>,
          s.url && (up || st === "external") ? <a href={s.url} target="_blank" rel="noreferrer">{s.url}</a> : <span className="muted">{s.url ?? "-"}</span>,
          data.health[s.name] ? <StatePill state={data.health[s.name]} /> : "-",
          !up && <div className="actions">
            <button className="btn btn-sm" onClick={() => { const v = window.prompt(`Pin ${s.name} to port:`, String(s.port ?? ""));
              if (v) act.run("Pin port", () => api.post(`/api/ports/${encodeURIComponent(id)}/${s.name}`, { port: Number(v) }), `Pinned to ${v}.`); }}>Pin port</button>
            {s.pinned && <button className="btn btn-sm" onClick={() => act.run("Unpin", () => api.post(`/api/ports/${encodeURIComponent(id)}/${s.name}/auto`), "Unpinned.")}>Unpin</button>}
          </div>])} />
      </Box>
    </>
  );
}

function ProjectDocker({ id }: { id: string }) {
  const { data, error, loading, reload } = useApi<{ available: boolean; reason?: string; containers: { name: string; image: string; state: string; health: string; status: string; ports: string; compose_service: string }[] }>(
    `/api/projects/${encodeURIComponent(id)}/containers`);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  if (!data.available) return <div className="notice notice-warn">{data.reason}</div>;
  return (
    <Box title="Containers of this project" actions={<a className="small" href="#/docker/compose">All Compose projects</a>}>
      <DataTable columns={["Container", "Service", "Image", "State", "Ports"]} empty="No containers carry this project's folder in their Compose labels."
        rows={data.containers.map((c) => [c.name, c.compose_service, <span className="mono small">{c.image}</span>, <StatePill state={c.health || c.state} />, <span className="mono small">{c.ports}</span>])} />
    </Box>
  );
}

function ProjectDatabases({ id }: { id: string }) {
  const { data, loading } = useApi<{ id: string; name: string; engine: string; project_id: string | null; read_only: boolean }[]>("/api/db/connections");
  if (loading) return <Loading />;
  const mine = (data ?? []).filter((c) => c.project_id === id);
  return (
    <Box title="Database connections" actions={<a className="small" href="#/databases">Manage connections</a>}>
      {mine.length === 0 ? <Empty>No connections belong to this project. Use “Discover database connections” on the Databases page; it reads this project's env files and Docker containers.</Empty>
        : mine.map((c) => <div className="row" key={c.id}><a href={`#/databases/${encodeURIComponent(c.id)}`}>{c.name}</a>
          <span className="actions"><span className="chip">{c.engine}</span><span className={`pill ${c.read_only ? "info" : "warn"}`}>{c.read_only ? "Read-only" : "Administrative"}</span></span></div>)}
    </Box>
  );
}

function Environment({ id }: { id: string }) {
  const base = `/api/env/${encodeURIComponent(id)}`;
  const list = useApi<{ files: { path: string; type: string; example: boolean }[]; missing: { file: string; missing_file: boolean; keys: string[] }[] }>(base);
  const [file, setFile] = useState<string | null>(null);
  const [cmp, setCmp] = useState<string>("");
  const content = useApi<{ path: string; type: string; keys: { key: string; set: boolean; secret: boolean; value: string | null }[]; note?: string }>(
    file ? `${base}/file?path=${encodeURIComponent(file)}` : null);
  const diff = useApi<{ only_in_a: string[]; only_in_b: string[]; different: string[]; same: string[] }>(
    file && cmp ? `${base}/compare?a=${encodeURIComponent(file)}&b=${encodeURIComponent(cmp)}` : null);
  const act = useAction(() => content.reload());
  if (list.loading) return <Loading />;
  if (list.error || !list.data) return <ErrorNote message={list.error} />;
  const envFiles = list.data.files.filter((f) => f.type === "env");
  return (
    <>
      <NoteView note={act.note} />
      {list.data.missing.map((m) => <div key={m.file} className="notice notice-warn">{m.missing_file ? `${m.file} does not exist; its example lists ${m.keys.length} variables.`
        : `${m.file} is missing or leaves empty: ${m.keys.join(", ")}.`}</div>)}
      <div className="split">
        <section className="box" style={{ alignSelf: "start" }}>
          <div className="box-head"><h2>Files</h2></div>
          {list.data.files.length === 0 ? <Empty>No configuration files found.</Empty> : list.data.files.map((f) => (
            <button key={f.path} className="list-btn" aria-current={file === f.path} onClick={() => { setFile(f.path); setCmp(""); }}>
              <span className="mono small">{f.path}</span> {f.example && <span className="muted small">example</span>}</button>))}
        </section>
        <div>{!file ? <Empty>Choose a file. Secret values are never shown; their keys and whether they are set are.</Empty> : content.loading ? <Loading /> : content.data && (
          <Box title={<span className="mono">{file}</span>} actions={content.data.type === "env" && <>
            <label className="sr-only" htmlFor="cmpf">Compare with</label>
            <select id="cmpf" className="select" style={{ width: "auto" }} value={cmp} onChange={(e) => setCmp(e.target.value)}>
              <option value="">Compare with…</option>{envFiles.filter((f) => f.path !== file).map((f) => <option key={f.path} value={f.path}>{f.path}</option>)}
            </select>
            <button className="btn btn-sm" onClick={() => { const k = window.prompt("Key to add or change:"); if (!k) return; const v = window.prompt(`Value for ${k}:`); if (v === null) return;
              act.run(`Set ${k}`, () => withConfirm((confirm) => api.post(base, { file, key: k, value: v, confirm })), `Saved ${k}. The previous file was backed up.`); }}>Set a value</button>
          </>}>
            {content.data.note ? <div className="box-body small muted">{content.data.note}</div> : (
              <DataTable columns={["Key", "Value"]} empty="No keys." rows={content.data.keys.map((k) => [
                <span className="mono">{k.key}</span>,
                !k.set ? <span className="pill warn">Empty</span> : k.secret ? <span className="muted">•••••• (secret, set)</span> : <span className="mono small">{String(k.value)}</span>])} />)}
            {diff.data && (
              <div className="box-body">
                <h3>Compared with {cmp}</h3>
                <dl className="kv">
                  <dt>Only here</dt><dd className="mono small">{diff.data.only_in_a.join(", ") || "-"}</dd>
                  <dt>Only there</dt><dd className="mono small">{diff.data.only_in_b.join(", ") || "-"}</dd>
                  <dt>Different value</dt><dd className="mono small">{diff.data.different.join(", ") || "-"}</dd>
                  <dt>Same value</dt><dd className="mono small">{diff.data.same.length} keys</dd>
                </dl>
                <p className="small muted">Values are compared by checksum, so secrets stay hidden. STACKLOOM never copies values between files.</p>
              </div>)}
          </Box>)}
        </div>
      </div>
    </>
  );
}

function CodeCortex({ data, reload }: { data: Detail; reload: () => void }) {
  const act = useAction(reload);
  const base = `/api/codecortex/${encodeURIComponent(data.id)}`;
  const [label, tone] = mapPill(data.map.status);
  const [check, setCheck] = useState<{ ok: boolean; problems: string[]; notes: string[] } | null>(null);
  return (
    <>
      <NoteView note={act.note} />
      <Box title="Project map" actions={<Pill label={label} tone={tone} />}>
        <div className="box-body">
          {data.map.status === "none" && <p style={{ marginTop: 0 }}>No map yet. Building one lets coding agents answer questions about this code without reading every file.
            It is saved in <code>.codecortex/</code> inside the project, which Git ignores.</p>}
          <dl className="kv">
            <dt>Symbols</dt><dd>{data.map.stats.nodes ?? "-"}</dd>
            <dt>Relationships</dt><dd>{data.map.stats.edges ?? "-"}</dd>
            <dt>Files</dt><dd>{data.map.stats.files ?? "-"}</dd>
            <dt>Languages</dt><dd>{data.map.stats.languages?.join(", ") || "-"}</dd>
            <dt>Size</dt><dd>{bytes(data.map.stats.size_bytes)}</dd>
            <dt>Refreshed</dt><dd>{ago(data.map.last_refresh)}</dd>
            <dt>Opened by an agent</dt><dd>{ago(data.map.last_opened)}</dd>
            <dt>Location</dt><dd className="path">{data.map.map_dir ?? `${data.path}/.codecortex`}</dd>
            {data.map.error && <><dt>Last error</dt><dd style={{ color: "var(--bad)" }}>{data.map.error}</dd></>}
          </dl>
          {check && <div className={`notice notice-${check.ok ? "ok" : "error"}`} style={{ marginTop: 12 }}>
            {check.ok ? "The map is valid." : check.problems.join(" ")} {check.notes.join(" ")}</div>}
          <div className="actions" style={{ marginTop: 16 }}>
            <button className="btn btn-primary" disabled={data.map.status === "refreshing"} onClick={() => act.run("Refresh map", () => api.post(`${base}/refresh`, { rebuild: false }))}>
              {data.map.status === "none" ? "Build project map" : "Refresh (changed files only)"}</button>
            {data.map.status === "ready" && <>
              <a className="btn" href={`#/graph/${encodeURIComponent(data.id)}`}>Open graph explorer</a>
              <button className="btn" onClick={() => act.run("Validate", async () => { const r = await api.get<typeof check>(`${base}/validate`); setCheck(r); return { message: "Checked." }; })}>Validate</button>
              <button className="btn" onClick={() => act.run("Back up map", () => api.post(`${base}/backup`), "Saved a copy of the map.")}>Back up</button>
              <button className="btn" onClick={() => { if (window.confirm("Rebuild the whole map? This re-parses every file.")) act.run("Rebuild", () => api.post(`${base}/refresh`, { rebuild: true })); }}>Rebuild from scratch</button>
              <button className="btn" onClick={() => act.run("Connect to coding agent", () => withConfirm((confirm) => api.post(`${base}/connect-agent`, { confirm })))}>Connect to Claude Code</button>
              <button className="btn btn-danger" onClick={() => act.run("Delete map", () => withConfirm((confirm) => api.post(`${base}/delete`, { confirm })))}>Delete map</button>
            </>}
          </div>
          <p className="small muted">“Connect to Claude Code” runs <code>codecortex install</code> for this project: it adds a short section to its CLAUDE.md and a hook to its .claude/settings.json.</p>
        </div>
      </Box>
    </>
  );
}

function Logs({ id }: { id: string }) {
  const [lines, setLines] = useState(300);
  const log = useText(`/api/projects/${encodeURIComponent(id)}/logs?lines=${lines}`);
  return (
    <Box title="Log" actions={<>
      <select className="select" aria-label="Lines" style={{ width: "auto" }} value={lines} onChange={(e) => setLines(Number(e.target.value))}>
        {[100, 300, 1000, 3000].map((n) => <option key={n} value={n}>Last {n} lines</option>)}
      </select>
      <button className="btn btn-sm" onClick={log.reload}>Reload</button></>}>
      {log.loading ? <Loading /> : <pre className="log" style={{ margin: 16, maxHeight: "60vh" }}>{log.data ?? log.error}</pre>}
      <p className="box-body small muted" style={{ margin: 0 }}>STACKLOOM's log of starts and stops plus the app's own output, and container logs for Compose apps. Secrets are masked.</p>
    </Box>
  );
}

interface Check { check: string; status: string; detail: string; fix: string }

function Checks({ id, launchEnabled, hasLaunch, reload }: { id: string; launchEnabled: boolean; hasLaunch: boolean; reload: () => void }) {
  const checks = useApi<Check[]>(`/api/diagnostics/${encodeURIComponent(id)}`);
  const [report, setReport] = useState<{ markdown: string; file: string } | null>(null);
  const act = useAction(reload);
  return (
    <>
      <NoteView note={act.note} />
      <Box title="Checks" actions={<button className="btn btn-sm" onClick={checks.reload}>Run again</button>}>
        {checks.loading ? <Loading /> : checks.error ? <ErrorNote message={checks.error} /> : (checks.data ?? []).map((c, i) => (
          <div className="row" key={i}>
            <div className="row-main"><div className="row-title">{c.check}</div><div className="meta"><span>{c.detail}</span>{c.fix && c.status !== "ok" && <span>Fix: {c.fix}</span>}</div></div>
            <Pill label={c.status === "ok" ? "OK" : c.status === "problem" ? "Problem" : "Check"} tone={c.status === "ok" ? "ok" : c.status === "problem" ? "bad" : "warn"} />
          </div>))}
      </Box>
      <Box title="Handover report" actions={<button className="btn btn-sm btn-primary" onClick={() => act.run("Handover report", async () => {
        setReport(await api.post(`/api/projects/${encodeURIComponent(id)}/handover`)); return { message: "Report written." }; })}>Generate</button>}>
        {report ? <><p className="box-body small muted" style={{ margin: 0 }}>Saved to <span className="path">{report.file}</span>. Secrets removed.</p>
          <pre className="log" style={{ margin: 16, maxHeight: 480 }}>{report.markdown}</pre></>
          : <div className="box-body small muted">A Markdown summary for whoever takes over: stack, how to start it, ports, env key names, Git state, map and checks.</div>}
      </Box>
      {hasLaunch && <Box title="Launch from STACKLOOM" actions={<button className={`btn btn-sm ${launchEnabled ? "btn-danger" : ""}`}
        onClick={() => act.run(launchEnabled ? "Turn off launching" : "Turn on launching",
          () => api.post(`/api/projects/${encodeURIComponent(id)}/launch`, { enabled: !launchEnabled, confirm: true }), launchEnabled ? "Launching turned off." : "Launching turned on.")}>
        {launchEnabled ? "Turn off" : "Turn on"}</button>}>
        <div className="box-body small">{launchEnabled ? "STACKLOOM may run this project's start command after you approve it." : "STACKLOOM will not start this project."}</div>
      </Box>}
    </>
  );
}
