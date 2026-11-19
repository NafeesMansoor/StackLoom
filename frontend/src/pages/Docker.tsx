import { useMemo, useState } from "react";
import { api } from "../api";
import { withConfirm } from "../actions";
import { Box, DataTable, NoteView, StatePill, Tabs, useAction } from "../components";
import { useApi, useText } from "../hooks";
import { Empty, ErrorNote, Loading, PageHead } from "../ui";

interface Engine { available: boolean; reason?: string; server_version?: string; context?: string; cpus?: number; memory?: number }
interface Overview { engine: Engine; containers?: number; running?: number; stopped?: number; paused?: number; unhealthy?: number;
  images?: number; volumes?: number; networks?: number; compose_projects?: number }
interface Container { id: string; name: string; image: string; state: string; status: string; health: string; ports: string;
  compose_project: string; compose_service: string; project: string | null; stats?: { cpu: string; memory: string } | null }

export function Docker({ tab: initial }: { tab?: string }) {
  const [tab, setTab] = useState(initial || "overview");
  const { data, error, loading, reload } = useApi<Overview>("/api/docker");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  if (!data.engine.available) {
    return (
      <>
        <PageHead title="Docker" />
        <div className="notice notice-warn">{data.engine.reason} STACKLOOM never starts Docker by itself.</div>
        <button className="btn" onClick={reload}>Check again</button>
      </>
    );
  }
  return (
    <>
      <PageHead title="Docker" lede={`Engine ${data.engine.server_version} · context ${data.engine.context || "default"} · every container on this machine, not only STACKLOOM's.`}>
        <button className="btn" onClick={reload}>Refresh</button>
      </PageHead>
      <Tabs value={tab} onChange={setTab} tabs={[["overview", "Overview"], ["containers", "Containers"], ["compose", "Compose projects"],
        ["images", "Images"], ["volumes", "Volumes"], ["networks", "Networks"]]} />
      {tab === "overview" && (
        <div className="grid">
          {([["Running", data.running], ["Stopped", data.stopped], ["Unhealthy", data.unhealthy], ["Compose projects", data.compose_projects],
            ["Images", data.images], ["Volumes", data.volumes], ["Networks", data.networks], ["Paused", data.paused]] as [string, number][]).map(([l, v]) => (
            <div className="stat" key={l}><div className="stat-label">{l}</div><div className="stat-value">{v ?? 0}</div></div>
          ))}
        </div>
      )}
      {tab === "containers" && <Containers />}
      {tab === "compose" && <Compose />}
      {tab === "images" && <Images />}
      {tab === "volumes" && <Volumes />}
      {tab === "networks" && <Networks />}
    </>
  );
}

function Containers() {
  const { data, error, loading, reload } = useApi<Container[]>("/api/docker/containers");
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState<string | null>(null);
  const act = useAction(reload);
  const rows = useMemo(() => (data ?? []).filter((c) => filter === "all" || (filter === "running" ? c.state === "running"
    : filter === "unhealthy" ? c.health === "unhealthy" : c.state !== "running")), [data, filter]);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  const doAction = (c: Container, action: string) => act.run(`${action} ${c.name}`,
    () => withConfirm((confirm) => api.post(`/api/docker/containers/${encodeURIComponent(c.name)}`, { action, confirm })));
  return (
    <>
      <NoteView note={act.note} />
      <Box title="Containers" actions={
        <div className="seg" role="group" aria-label="Filter containers">
          {[["all", "All"], ["running", "Running"], ["stopped", "Stopped"], ["unhealthy", "Unhealthy"]].map(([k, l]) => (
            <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l}</button>))}
        </div>}>
        {rows.length === 0 ? <Empty>No containers in this view.</Empty> : rows.map((c) => (
          <div className="row" key={c.id} style={{ display: "block" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, justifyContent: "space-between" }}>
              <div className="row-main">
                <div className="row-title">{c.name} <span className="muted small mono">{c.image}</span></div>
                <div className="meta">
                  <span>{c.status}</span>
                  {c.compose_project && <span>Compose: {c.compose_project}/{c.compose_service}</span>}
                  {c.project && <a href={`#/projects/${encodeURIComponent(c.project)}`}>{c.project}</a>}
                  {c.ports && <span className="mono">{c.ports}</span>}
                  {c.stats && <span>CPU {c.stats.cpu} · {c.stats.memory}</span>}
                </div>
              </div>
              <div className="actions">
                <StatePill state={c.health || c.state} />
                {c.state === "running" ? <>
                  <button className="btn btn-sm" onClick={() => doAction(c, "restart")}>Restart</button>
                  <button className="btn btn-sm" onClick={() => doAction(c, "pause")}>Pause</button>
                  <button className="btn btn-sm" onClick={() => doAction(c, "stop")}>Stop</button>
                </> : c.state === "paused" ? <button className="btn btn-sm" onClick={() => doAction(c, "unpause")}>Resume</button>
                  : <>
                    <button className="btn btn-sm" onClick={() => doAction(c, "start")}>Start</button>
                    <button className="btn btn-sm btn-danger" onClick={() => doAction(c, "remove")}>Remove</button>
                  </>}
                <button className="btn btn-sm" aria-expanded={open === c.name} onClick={() => setOpen(open === c.name ? null : c.name)}>Details</button>
              </div>
            </div>
            {open === c.name && <ContainerDetail name={c.name} running={c.state === "running"} />}
          </div>
        ))}
      </Box>
    </>
  );
}

function ContainerDetail({ name, running }: { name: string; running: boolean }) {
  const [tab, setTab] = useState("logs");
  const info = useApi<Record<string, unknown>>(tab === "config" ? `/api/docker/containers/${encodeURIComponent(name)}` : null);
  const logs = useText(tab === "logs" ? `/api/docker/containers/${encodeURIComponent(name)}/logs?lines=300` : null);
  const [cmd, setCmd] = useState("");
  const [out, setOut] = useState("");
  const act = useAction();
  const env = (info.data?.env as { key: string; value: string }[]) ?? [];
  return (
    <div style={{ marginTop: 12 }}>
      <Tabs value={tab} onChange={setTab} tabs={[["logs", "Logs"], ["config", "Configuration"], ["exec", "Run a command"]]} />
      {tab === "logs" && (logs.loading ? <Loading /> : <><pre className="log">{logs.data ?? logs.error}</pre>
        <button className="btn btn-sm" style={{ marginTop: 8 }} onClick={logs.reload}>Reload logs</button></>)}
      {tab === "config" && (info.loading ? <Loading /> : info.error ? <ErrorNote message={info.error} /> : (
        <dl className="kv">
          <dt>Image</dt><dd className="mono">{String(info.data?.image ?? "")}</dd>
          <dt>Command</dt><dd className="mono">{String(info.data?.command ?? "")}</dd>
          <dt>Restart policy</dt><dd>{JSON.stringify(info.data?.restart_policy)}</dd>
          <dt>Ports</dt><dd className="mono">{JSON.stringify(info.data?.ports)}</dd>
          <dt>Mounts</dt><dd>{((info.data?.mounts as { name: string; source: string; destination: string }[]) ?? []).map((m) => (
            <div key={m.destination} className="mono small">{m.name || m.source} → {m.destination}</div>))}</dd>
          <dt>Networks</dt><dd>{((info.data?.networks as string[]) ?? []).join(", ")}</dd>
          <dt>Environment</dt><dd>{env.map((e) => <div key={e.key} className="mono small">{e.key}={e.value}</div>)}</dd>
        </dl>))}
      {tab === "exec" && (running ? (
        <form onSubmit={(e) => { e.preventDefault(); act.run("Run command", async () => {
          const r = await withConfirm((confirm) => api.post<{ exit_code: number; output: string; seconds: number }>(
            `/api/docker/containers/${encodeURIComponent(name)}/exec`, { command: cmd, confirm }));
          if (r) setOut(`exit ${r.exit_code} after ${r.seconds}s\n\n${r.output}`);
          return r && { message: "Command finished." };
        }); }}>
          <div className="field">
            <label htmlFor={`cmd-${name}`}>Command (runs once, no shell, 60 s limit)</label>
            <input id={`cmd-${name}`} className="input mono" placeholder="ls -la /app" value={cmd} onChange={(e) => setCmd(e.target.value)} required />
          </div>
          <button className="btn" disabled={!!act.busy}>Run</button>
          <NoteView note={act.note} />
          {out && <pre className="log">{out}</pre>}
          <p className="small muted">For an interactive shell, open a terminal and run <code>docker exec -it {name} sh</code>.</p>
        </form>) : <p className="muted">Start the container to run commands in it.</p>)}
    </div>
  );
}

interface ComposeProject { name: string; status: string; working_dir: string; config_files: string[]; services: string[]; project: string | null;
  containers: { name: string; service: string; state: string; health: string; ports: string }[] }

function Compose() {
  const { data, error, loading, reload } = useApi<ComposeProject[]>("/api/docker/compose");
  const act = useAction(reload);
  const [output, setOutput] = useState<{ name: string; text: string } | null>(null);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  const run = (p: ComposeProject, action: string, label: string, service?: string, removeVolumes = false) =>
    act.run(`${label} ${p.name}`, async () => {
      const body = (confirm: boolean) => ({ action, working_dir: p.working_dir, config_files: p.config_files, service,
        confirm, remove_volumes: removeVolumes, confirm_volumes: removeVolumes && confirm });
      if (removeVolumes && !window.confirm(`Delete ${p.name} AND its volumes? The data in them is destroyed and cannot be recovered.`)) return null;
      const r = await withConfirm((confirm) => api.post<{ output?: string }>(`/api/docker/compose/${encodeURIComponent(p.name)}`, body(confirm || removeVolumes)));
      if (r && "output" in r && r.output) setOutput({ name: `${p.name} ${action}`, text: r.output });
      return r;
    });
  return (
    <>
      <NoteView note={act.note} />
      {data.length === 0 ? <Empty>No Compose projects on this machine yet.</Empty> : data.map((p) => (
        <Box key={p.name} title={<>{p.name} {p.project && <a className="small" href={`#/projects/${encodeURIComponent(p.project)}`}>({p.project})</a>}</>}
          actions={<>
            <button className="btn btn-sm btn-primary" disabled={!!act.busy} onClick={() => run(p, "up", "Start application")}>Start application</button>
            <button className="btn btn-sm" disabled={!!act.busy} onClick={() => run(p, "stop", "Stop")}>Stop</button>
            <button className="btn btn-sm" disabled={!!act.busy} onClick={() => run(p, "restart", "Restart")}>Restart</button>
          </>}>
          <div className="box-body">
            <div className="meta" style={{ marginTop: 0 }}><span>{p.status}</span><span className="path">{p.working_dir || p.config_files.join(", ")}</span></div>
            <DataTable columns={["Service", "Container", "State", "Ports", ""]} rows={p.containers.map((c) => [
              <span className="mono">{c.service}</span>, c.name, <StatePill state={c.health || c.state} />, <span className="mono small">{c.ports}</span>,
              <div className="actions">
                <button className="btn btn-sm" onClick={() => run(p, c.state === "running" ? "restart" : "start", c.state === "running" ? "Restart" : "Start", c.service)}>
                  {c.state === "running" ? "Restart" : "Start"}</button>
                <button className="btn btn-sm" onClick={() => run(p, "logs", "Logs", c.service)}>View {c.service} logs</button>
              </div>])} />
            <div className="actions" style={{ marginTop: 12 }}>
              <button className="btn btn-sm" onClick={() => run(p, "logs", "Logs")}>All logs</button>
              <button className="btn btn-sm" onClick={() => run(p, "ps", "Status")}>Status</button>
              <button className="btn btn-sm" onClick={() => run(p, "config", "Configuration")}>Configuration</button>
              <button className="btn btn-sm" onClick={() => run(p, "build", "Build")}>Build images</button>
              <button className="btn btn-sm" onClick={() => run(p, "pull", "Pull")}>Pull images</button>
              <button className="btn btn-sm btn-danger" onClick={() => run(p, "down", "Remove containers")}>Remove containers (keep data)</button>
              <button className="btn btn-sm btn-danger" onClick={() => run(p, "down", "Remove with volumes", undefined, true)}>Remove with volumes…</button>
            </div>
            {output && output.name.startsWith(p.name) && <pre className="log">{output.text}</pre>}
          </div>
        </Box>
      ))}
    </>
  );
}

interface Image { id: string; repository: string; tag: string; size: string; created: string; dangling: boolean; in_use: boolean }

function Images() {
  const { data, error, loading, reload } = useApi<Image[]>("/api/docker/images");
  const act = useAction(reload);
  const [ref, setRef] = useState("");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  return (
    <>
      <NoteView note={act.note} />
      <Box title="Images" actions={<button className="btn btn-sm btn-danger" onClick={() => act.run("Remove dangling images",
        () => withConfirm((confirm) => api.post("/api/docker/images/prune", { confirm })))}>Remove dangling</button>}>
        <form className="box-body toolbar" onSubmit={(e) => { e.preventDefault(); act.run(`Pull ${ref}`, () => api.post("/api/docker/images/pull", { name: ref })); }}>
          <label className="sr-only" htmlFor="pull">Image to pull</label>
          <input id="pull" className="input mono" placeholder="postgres:16" value={ref} onChange={(e) => setRef(e.target.value)} required />
          <button className="btn">Pull image</button>
        </form>
        <DataTable columns={["Repository", "Tag", "Size", "Created", "", ""]} rows={data.map((i) => [
          <span className="mono">{i.repository}</span>, <span className="mono">{i.tag}</span>, i.size, i.created,
          i.in_use ? <span className="pill ok">In use</span> : i.dangling ? <span className="pill warn">Dangling</span> : "",
          <div className="actions">
            <button className="btn btn-sm" onClick={() => { const t = window.prompt("New tag (repository:tag):"); if (t) act.run("Tag", () => api.post("/api/docker/images/tag", { source: i.dangling ? i.id : `${i.repository}:${i.tag}`, target: t })); }}>Tag</button>
            {!i.in_use && <button className="btn btn-sm btn-danger" onClick={() => act.run("Remove image", () => withConfirm((confirm) =>
              api.post("/api/docker/images/remove", { name: i.dangling ? i.id : `${i.repository}:${i.tag}`, confirm })))}>Remove</button>}
          </div>])} />
      </Box>
    </>
  );
}

function Volumes() {
  const { data, error, loading, reload } = useApi<{ name: string; driver: string; labels: string; containers: string[] }[]>("/api/docker/volumes");
  const act = useAction(reload);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  return (
    <>
      <NoteView note={act.note} />
      <Box title="Volumes" actions={<button className="btn btn-sm" onClick={() => { const n = window.prompt("Volume name:"); if (n) act.run("Create volume", () => api.post("/api/docker/volumes", { name: n })); }}>Create volume</button>}>
        <DataTable columns={["Volume", "Compose project", "Used by", ""]} rows={data.map((v) => [
          <span className="mono">{v.name}</span>, v.labels || "-", v.containers.join(", ") || <span className="muted">no container</span>,
          <div className="actions">
            <button className="btn btn-sm" onClick={() => act.run(`Back up ${v.name}`, () => api.post("/api/docker/volumes/backup", { name: v.name }))}>Back up</button>
            {!v.containers.length && <button className="btn btn-sm btn-danger" onClick={() => act.run("Remove volume",
              () => withConfirm((confirm) => api.post("/api/docker/volumes/remove", { name: v.name, confirm })))}>Remove</button>}
          </div>])} />
        <p className="box-body small muted" style={{ margin: 0 }}>Backups are written to STACKLOOM's backup folder; restore them from the command line with Docker. Removing a container never removes its volumes.</p>
      </Box>
    </>
  );
}

function Networks() {
  const { data, error, loading, reload } = useApi<{ name: string; driver: string; scope: string; builtin: boolean; containers: string[] }[]>("/api/docker/networks");
  const act = useAction(reload);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  return (
    <>
      <NoteView note={act.note} />
      <Box title="Networks" actions={<button className="btn btn-sm" onClick={() => { const n = window.prompt("Network name:"); if (n) act.run("Create network", () => api.post("/api/docker/networks", { name: n })); }}>Create network</button>}>
        <DataTable columns={["Network", "Driver", "Containers", ""]} rows={data.map((n) => [
          <span className="mono">{n.name}</span>, n.driver, n.containers.join(", ") || "-",
          <div className="actions">
            {!n.builtin && <button className="btn btn-sm" onClick={() => { const c = window.prompt(`Container to connect to ${n.name}:`); if (c) act.run("Connect", () => api.post(`/api/docker/networks/${encodeURIComponent(n.name)}/connect`, { container: c, connect: true })); }}>Connect</button>}
            {!n.builtin && n.containers.length > 0 && <button className="btn btn-sm" onClick={() => { const c = window.prompt(`Container to disconnect (${n.containers.join(", ")}):`); if (c) act.run("Disconnect", () => api.post(`/api/docker/networks/${encodeURIComponent(n.name)}/connect`, { container: c, connect: false })); }}>Disconnect</button>}
            {!n.builtin && !n.containers.length && <button className="btn btn-sm btn-danger" onClick={() => act.run("Remove network",
              () => withConfirm((confirm) => api.post("/api/docker/networks/remove", { name: n.name, confirm })))}>Remove</button>}
          </div>])} />
      </Box>
    </>
  );
}
