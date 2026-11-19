import { useState } from "react";
import { api, ApiError } from "../api";
import { withConfirm } from "../actions";
import { Box, DataTable, NoteView, useAction } from "../components";
import { bytes, when } from "../format";
import { useApi } from "../hooks";
import { Mark } from "../Logo";
import { Empty, ErrorNote, Loading, PageHead } from "../ui";

interface Check { check: string; status: string; detail: string; fix: string }

export function Diagnostics() {
  const { data, error, loading, reload } = useApi<{ project: string; name: string; problems: Check[] }[]>("/api/diagnostics");
  if (loading) return <Loading what="Checking every project…" />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  const bad = data.filter((d) => d.problems.length);
  return (
    <>
      <PageHead title="Diagnostics" lede={`${bad.length} of ${data.length} projects need attention. Checks only read; nothing is changed.`}>
        <button className="btn" onClick={reload}>Check again</button>
      </PageHead>
      <Box title="Projects that need attention">
        {bad.length === 0 ? <Empty>Every project passed its checks.</Empty> : bad.map((d) => (
          <div className="row" key={d.project} style={{ display: "block" }}>
            <div className="row-title"><a href={`#/projects/${encodeURIComponent(d.project)}/diagnostics`}>{d.name}</a></div>
            {d.problems.map((p, i) => <div key={i} className="small" style={{ marginTop: 4 }}><span className="pill bad">{p.check}</span> {p.detail}
              {p.fix && <span className="muted"> · {p.fix}</span>}</div>)}
          </div>))}
      </Box>
    </>
  );
}

interface BackupItem { id: number; kind: string; target: string; path: string; size: number; created_at: string; verified_at: string | null; exists: boolean; note: string }

export function Backups() {
  const { data, error, loading, reload } = useApi<{ items: BackupItem[]; settings: { daily_stackloom: boolean; keep_per_kind: number } }>("/api/backups");
  const act = useAction(reload);
  const [keep, setKeep] = useState<string | null>(null);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  const KIND: Record<string, string> = { stackloom: "STACKLOOM", database: "Database", volume: "Docker volume", map: "Project map", config: "Config file" };
  return (
    <>
      <PageHead title="Backups" lede="Each backup says exactly what it holds. A container backup does not include its volumes; volumes are backed up on their own.">
        <button className="btn btn-primary" onClick={() => act.run("Back up STACKLOOM", () => api.post("/api/backups/stackloom"), "Saved a backup of the registry and settings.")}>Back up STACKLOOM now</button>
      </PageHead>
      <NoteView note={act.note} />
      <Box title="Schedule and retention">
        <form className="box-body toolbar" onSubmit={(e) => { e.preventDefault(); act.run("Save", () => api.post("/api/backups/settings",
          { daily_stackloom: data.settings.daily_stackloom, keep_per_kind: Number(keep ?? data.settings.keep_per_kind) }), "Saved."); }}>
          <label style={{ display: "flex", gap: 8, alignItems: "center", minHeight: 40 }}>
            <input type="checkbox" checked={data.settings.daily_stackloom} onChange={(e) => act.run("Save", () => api.post("/api/backups/settings",
              { daily_stackloom: e.target.checked, keep_per_kind: data.settings.keep_per_kind }), e.target.checked ? "Daily backups on." : "Daily backups off.")} />
            Back up STACKLOOM's registry and settings once a day
          </label>
          <label htmlFor="keep" className="small">Keep the newest</label>
          <input id="keep" className="input mono" style={{ maxWidth: 80 }} inputMode="numeric" value={keep ?? String(data.settings.keep_per_kind)} onChange={(e) => setKeep(e.target.value)} />
          <span className="small">of each target</span>
          <button className="btn">Save</button>
        </form>
      </Box>
      <Box title="History">
        <DataTable columns={["Made", "What", "Target", "Size", "Checked", ""]} empty="No backups yet." rows={data.items.map((b) => [
          when(b.created_at), KIND[b.kind] ?? b.kind, <span className="mono small">{b.target}</span>, b.exists ? bytes(b.size) : <span className="pill bad">Missing</span>,
          b.verified_at ? when(b.verified_at) : "-",
          <div className="actions">
            <button className="btn btn-sm" onClick={() => act.run("Verify", async () => { const r = await api.post<{ ok: boolean; detail: string }>(`/api/backups/${b.id}/verify`); if (!r.ok) throw new ApiError(400, r.detail); return { message: r.detail }; })}>Verify</button>
            {b.exists && <a className="btn btn-sm" href={`/api/backups/${b.id}/download`}>Download</a>}
            <button className="btn btn-sm btn-danger" onClick={() => act.run("Delete backup", () => withConfirm((confirm) => api.post(`/api/backups/${b.id}/delete`, { confirm })))}>Delete</button>
          </div>])} />
        <p className="box-body small muted" style={{ margin: 0 }}>To restore STACKLOOM itself, stop the dashboard and run <code>stackloom backup restore &lt;file&gt;</code>. SQLite databases restore from their database page.</p>
      </Box>
    </>
  );
}

interface SystemInfo { version: string; copyright: string; copyright_url: string; python: string; platform: string; codecortex: string | null; home: string;
  drivers: Record<string, boolean>; hook_installed: boolean; docker: { available: boolean; server_version?: string; reason?: string } }

export function About() {
  const { data, error, loading } = useApi<SystemInfo>("/api/system");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} />;
  const EXTRA: Record<string, string> = { postgres: "psycopg[binary]", mysql: "PyMySQL", mongodb: "pymongo", redis: "redis", keychain: "keyring" };
  return (
    <>
      <PageHead title="About STACKLOOM" />
      <Box title={<span style={{ display: "inline-flex", gap: 10, alignItems: "center" }}><Mark size={28} /> STACKLOOM {data.version}</span>}>
        <div className="box-body">
          <p style={{ marginTop: 0 }}>One workspace. Every project. Complete control.</p>
          <dl className="kv">
            <dt>Copyright</dt><dd><a href={data.copyright_url} target="_blank" rel="noreferrer">{data.copyright}</a></dd>
            <dt>Python</dt><dd>{data.python}</dd>
            <dt>System</dt><dd className="small">{data.platform}</dd>
            <dt>CodeCortex engine</dt><dd>{data.codecortex ?? "not importable"}</dd>
            <dt>Docker</dt><dd>{data.docker.available ? `engine ${data.docker.server_version}` : data.docker.reason}</dd>
            <dt>Claude Code hook</dt><dd>{data.hook_installed ? "installed" : <>not installed (<code>stackloom agent hook install</code>)</>}</dd>
            <dt>Data folder</dt><dd className="path">{data.home}</dd>
          </dl>
        </div>
      </Box>
      <Box title="Database drivers">
        <DataTable columns={["Engine", "Driver", "Install"]} rows={Object.entries(data.drivers).map(([k, ok]) => [k, ok ? <span className="pill ok">Installed</span> : <span className="pill">Not installed</span>,
          ok ? "" : <code>pipx inject stackloom {EXTRA[k]}</code>])} />
        <p className="box-body small muted" style={{ margin: 0 }}>SQLite needs nothing. Drivers stay optional so the base install is small.</p>
      </Box>
    </>
  );
}
