import { useMemo, useState } from "react";
import { api } from "../api";
import { withConfirm } from "../actions";
import { Box, DataTable, NoteView, StatePill, useAction } from "../components";
import { useApi } from "../hooks";
import { ErrorNote, Loading, PageHead } from "../ui";

interface Svc {
  id: string; name: string; group: string; state: string; launch_enabled: boolean; type: string;
  services: { name: string; port: number | null; url: string | null }[];
}

export function Services() {
  const { data, error, loading, reload } = useApi<Svc[]>("/api/services");
  const [filter, setFilter] = useState("all");
  const act = useAction(reload);
  const rows = useMemo(() => (data ?? []).filter((s) => filter === "all" || (filter === "running"
    ? ["running", "partial", "external"].includes(s.state) : !["running", "partial", "external"].includes(s.state))), [data, filter]);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  const running = data.filter((s) => ["running", "partial"].includes(s.state)).length;
  return (
    <>
      <PageHead title="Services" lede={`${running} of ${data.length} apps running. Apps STACKLOOM did not start are shown and never stopped.`}>
        <button className="btn" onClick={reload}>Refresh</button>
      </PageHead>
      <NoteView note={act.note} />
      <Box title="Apps with a start command" actions={
        <div className="seg" role="group" aria-label="Filter">
          {[["all", "All"], ["running", "Running"], ["stopped", "Not running"]].map(([k, l]) => (
            <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l}</button>))}
        </div>}>
        {rows.length === 0 ? <div className="empty">No apps in this view.</div> : rows.map((s) => (
          <div className="row" key={s.id}>
            <div className="row-main">
              <div className="row-title"><a href={`#/projects/${encodeURIComponent(s.id)}/runtime`}>{s.name}</a></div>
              <div className="meta">
                <span>{s.group}</span><span>{s.type === "docker-compose" ? "Docker Compose" : "Process"}</span>
                {s.services.map((v) => v.url && ["running", "partial", "external"].includes(s.state)
                  ? <a key={v.name} href={v.url} target="_blank" rel="noreferrer">{v.name} :{v.port}</a>
                  : <span key={v.name} className="mono">{v.name}{v.port ? ` :${v.port}` : ""}</span>)}
                {!s.launch_enabled && <span>launch off</span>}
              </div>
            </div>
            <div className="actions">
              <StatePill state={s.state} />
              {["running", "partial"].includes(s.state) ? (
                <>
                  <button className="btn btn-sm" disabled={!!act.busy}
                    onClick={() => act.run(`Restart ${s.name}`, () => api.post(`/api/projects/${s.id}/restart`))}>Restart</button>
                  <button className="btn btn-sm" disabled={!!act.busy}
                    onClick={() => act.run(`Stop ${s.name}`, () => api.post(`/api/projects/${s.id}/stop`))}>Stop</button>
                </>
              ) : s.state !== "external" && (
                s.launch_enabled
                  ? <button className="btn btn-sm" disabled={!!act.busy} onClick={() => act.run(`Start ${s.name}`,
                    () => withConfirm((approve) => api.post(`/api/projects/${s.id}/start`, { approve })))}>Start</button>
                  : <a className="btn btn-sm" href={`#/projects/${encodeURIComponent(s.id)}/runtime`}>Review</a>
              )}
            </div>
          </div>
        ))}
      </Box>
    </>
  );
}

interface PortRow { project: string; service: string; port: number; pinned: boolean; in_use: boolean; owners: { pid: number; command: string }[] }

export function Ports() {
  const { data, error, loading, reload } = useApi<{ pool: [number, number]; dashboard: number | null; assignments: PortRow[] }>("/api/ports");
  const act = useAction(reload);
  const [range, setRange] = useState<[string, string] | null>(null);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  const pool = range ?? [String(data.pool[0]), String(data.pool[1])];
  return (
    <>
      <PageHead title="Ports" lede="Every service gets a port from the pool and keeps it. Pinned ports never move. Nothing is ever stopped to free a port." />
      <NoteView note={act.note} />
      <Box title="Assignments">
        <DataTable columns={["Port", "Project", "Service", "Mode", "Now", ""]} empty="No ports assigned yet. They are assigned at the first start."
          rows={data.assignments.map((r) => [
            <span className="mono">{r.port}</span>,
            <a href={`#/projects/${encodeURIComponent(r.project)}/runtime`}>{r.project}</a>,
            <span className="mono">{r.service}</span>,
            r.pinned ? "Pinned" : "Automatic",
            r.in_use ? <span>in use{r.owners.length ? ` by ${r.owners.map((o) => `${o.command} (${o.pid})`).join(", ")}` : ""}</span> : <span className="muted">free</span>,
            <div className="actions">
              <button className="btn btn-sm" onClick={() => {
                const v = window.prompt(`New port for ${r.project}/${r.service} (it will be pinned):`, String(r.port));
                if (v) act.run("Pin port", () => api.post(`/api/ports/${r.project}/${r.service}`, { port: Number(v) }), `Pinned ${r.service} to ${v}.`);
              }}>Change</button>
              {r.pinned && <button className="btn btn-sm" onClick={() => act.run("Unpin", () => api.post(`/api/ports/${r.project}/${r.service}/auto`), "Unpinned; a free port was chosen.")}>Unpin</button>}
            </div>,
          ])} />
      </Box>
      <Box title="Port range">
        <form className="box-body toolbar" onSubmit={(e) => { e.preventDefault(); act.run("Save range", () => api.post("/api/ports/pool", { start: Number(pool[0]), end: Number(pool[1]) }), "Saved the port range."); }}>
          <label htmlFor="ps" className="small">From</label>
          <input id="ps" className="input mono" style={{ maxWidth: 120 }} inputMode="numeric" value={pool[0]} onChange={(e) => setRange([e.target.value, pool[1]])} />
          <label htmlFor="pe" className="small">to</label>
          <input id="pe" className="input mono" style={{ maxWidth: 120 }} inputMode="numeric" value={pool[1]} onChange={(e) => setRange([pool[0], e.target.value])} />
          <button className="btn">Save range</button>
          {data.dashboard && <span className="small muted">The dashboard uses {data.dashboard}.</span>}
        </form>
      </Box>
    </>
  );
}
