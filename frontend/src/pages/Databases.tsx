import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, csrfToken } from "../api";
import { withConfirm } from "../actions";
import { Box, DataTable, NoteView, Tabs, useAction } from "../components";
import { bytes, when } from "../format";
import { useApi } from "../hooks";
import { SqlEditor } from "../SqlEditor";
import { Empty, ErrorNote, Loading, PageHead } from "../ui";

interface Conn {
  id: string; name: string; engine: string; host: string; port: number | null; database: string; username: string; path: string;
  project_id: string | null; container: string; read_only: boolean; password_source: string; source: string; has_session_password: boolean;
}
interface Candidate extends Partial<Conn> { engine: string; name: string; evidence: string }

const ENGINE_LABEL: Record<string, string> = { sqlite: "SQLite", postgres: "PostgreSQL", mysql: "MySQL", mariadb: "MariaDB", mongodb: "MongoDB", redis: "Redis" };

export function Databases({ id }: { id?: string }) {
  if (id) return <Explorer id={id} />;
  return <Connections />;
}

function Connections() {
  const { data, error, loading, reload } = useApi<Conn[]>("/api/db/connections");
  const [found, setFound] = useState<Candidate[] | null>(null);
  const [adding, setAdding] = useState<Partial<Conn> | null>(null);
  const act = useAction(reload);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  const discover = () => act.run("Discover database connections", async () => {
    setFound(await api.get<Candidate[]>("/api/db/discover"));
    return { message: "Discovery finished. Each result is unverified until you test it." };
  });
  return (
    <>
      <PageHead title="Databases" lede="One place for every database: in Docker, on this Mac, or a file. Passwords stay in the keychain, the project's own .env, or memory.">
        <button className="btn" onClick={discover} disabled={!!act.busy}>Discover database connections</button>
        <button className="btn btn-primary" onClick={() => setAdding({ engine: "postgres", host: "127.0.0.1", read_only: true, password_source: "session" })}>Add connection</button>
      </PageHead>
      <NoteView note={act.note} />
      {adding && <ConnForm initial={adding} onClose={() => setAdding(null)} onSaved={() => { setAdding(null); reload(); }} />}
      {found && (
        <Box title="Found" actions={<button className="btn btn-sm" onClick={() => setFound(null)}>Hide</button>}>
          {found.length === 0 ? <Empty>Nothing new found.</Empty> : found.map((f, i) => (
            <div className="row" key={i}>
              <div className="row-main">
                <div className="row-title">{f.name} <span className="chip">{ENGINE_LABEL[f.engine] ?? f.engine}</span></div>
                <div className="meta"><span className="mono">{f.path || `${f.host}:${f.port ?? "?"}${f.database ? "/" + f.database : ""}`}</span><span>{f.evidence}</span></div>
              </div>
              <button className="btn btn-sm" onClick={() => setAdding({ ...f, read_only: true })}>Review and add</button>
            </div>))}
        </Box>
      )}
      <Box title="Connections">
        {data.length === 0 ? <Empty>No connections yet. Discover them, or add one.</Empty> : data.map((c) => (
          <div className="row" key={c.id}>
            <div className="row-main">
              <div className="row-title"><a href={`#/databases/${encodeURIComponent(c.id)}`}>{c.name}</a> <span className="chip">{ENGINE_LABEL[c.engine] ?? c.engine}</span></div>
              <div className="meta">
                <span className="mono">{c.path || `${c.host}:${c.port}${c.database ? "/" + c.database : ""}`}</span>
                <span className={`pill ${c.read_only ? "info" : "warn"}`}>{c.read_only ? "Read-only" : "Administrative"}</span>
                {c.project_id && <a href={`#/projects/${encodeURIComponent(c.project_id)}`}>{c.project_id}</a>}
                {c.container && <span>container {c.container}</span>}
              </div>
            </div>
            <div className="actions">
              <button className="btn btn-sm" onClick={() => act.run(`Test ${c.name}`, async () => {
                const r = await api.post<{ version: string; ms: number }>(`/api/db/connections/${c.id}/test`);
                return { message: `Connected: ${r.version} (${r.ms} ms).` };
              })}>Test</button>
              <button className="btn btn-sm" onClick={() => setAdding(c)}>Edit</button>
              <button className="btn btn-sm btn-danger" onClick={() => { if (window.confirm(`Forget the connection ${c.name}? The database itself is not touched.`))
                act.run("Remove connection", () => api.del(`/api/db/connections/${c.id}`), "Connection removed."); }}>Forget</button>
            </div>
          </div>))}
      </Box>
    </>
  );
}

function ConnForm({ initial, onClose, onSaved }: { initial: Partial<Conn>; onClose: () => void; onSaved: () => void }) {
  const [c, setC] = useState<Partial<Conn> & { password?: string }>(initial);
  const [error, setError] = useState("");
  const set = (k: string, v: unknown) => setC({ ...c, [k]: v });
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setError("");
    try {
      await api.post("/api/db/connections", { ...c, port: c.port ? Number(c.port) : null, password: c.password || null });
      onSaved();
    } catch (err) { setError((err as ApiError).message); }
  };
  const sqlite = c.engine === "sqlite";
  const typed = c.password_source === "session" || c.password_source === "keychain";
  return (
    <Box title={c.id ? `Edit ${c.name}` : "New connection"} actions={<button className="btn btn-sm" onClick={onClose}>Cancel</button>}>
      <form className="box-body" onSubmit={submit}>
        {error && <ErrorNote message={error} />}
        <div className="grid" style={{ marginBottom: 0 }}>
          <div className="field"><label htmlFor="cn">Name</label><input id="cn" className="input" value={c.name ?? ""} onChange={(e) => set("name", e.target.value)} required /></div>
          <div className="field"><label htmlFor="ce">Engine</label>
            <select id="ce" className="select" value={c.engine} onChange={(e) => set("engine", e.target.value)}>
              {Object.entries(ENGINE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select></div>
          {sqlite ? (
            <div className="field" style={{ gridColumn: "span 2" }}><label htmlFor="cp">SQLite file</label>
              <input id="cp" className="input mono" placeholder="/Users/you/app/data.db" value={c.path ?? ""} onChange={(e) => set("path", e.target.value)} required /></div>
          ) : <>
            <div className="field"><label htmlFor="ch">Host</label><input id="ch" className="input mono" value={c.host ?? ""} onChange={(e) => set("host", e.target.value)} required /></div>
            <div className="field"><label htmlFor="cpt">Port</label><input id="cpt" className="input mono" inputMode="numeric" value={c.port ?? ""} onChange={(e) => set("port", e.target.value)} /></div>
            <div className="field"><label htmlFor="cd">Database (optional)</label><input id="cd" className="input mono" value={c.database ?? ""} onChange={(e) => set("database", e.target.value)} /></div>
            <div className="field"><label htmlFor="cu">User (optional)</label><input id="cu" className="input mono" autoComplete="off" value={c.username ?? ""} onChange={(e) => set("username", e.target.value)} /></div>
            <div className="field"><label htmlFor="cs">Password comes from</label>
              <select id="cs" className="select" value={c.password_source?.startsWith("env:") ? c.password_source : c.password_source}
                onChange={(e) => set("password_source", e.target.value)}>
                <option value="none">No password</option>
                <option value="session">Ask now, keep in memory until STACKLOOM stops</option>
                <option value="keychain">The macOS keychain</option>
                {c.password_source?.startsWith("env:") && <option value={c.password_source}>The project's env file ({c.password_source.split("|").pop()})</option>}
              </select></div>
            {typed && <div className="field"><label htmlFor="cpw">Password {c.id ? "(leave empty to keep)" : ""}</label>
              <input id="cpw" className="input" type="password" autoComplete="new-password" value={c.password ?? ""} onChange={(e) => set("password", e.target.value)} /></div>}
          </>}
        </div>
        <label className="small" style={{ display: "flex", gap: 8, alignItems: "center", margin: "4px 0 14px", minHeight: 40 }}>
          <input type="checkbox" checked={c.read_only ?? true} onChange={(e) => set("read_only", e.target.checked)} />
          Read-only (recommended). Turn off for administration: changing data, tables and databases.
        </label>
        <button className="btn btn-primary">Save connection</button>
      </form>
    </Box>
  );
}

interface DbInfo { engine: string; kind: string; read_only: boolean; server: Record<string, unknown>; databases: { name: string; size_bytes?: number; keys?: number }[] }

function Explorer({ id }: { id: string }) {
  const info = useApi<DbInfo>(`/api/db/${encodeURIComponent(id)}/databases`);
  const [database, setDatabase] = useState("");
  const [tab, setTab] = useState("tables");
  const [pw, setPw] = useState("");
  useEffect(() => {
    if (info.data && !database) setDatabase(info.data.databases[0]?.name ?? "");
  }, [info.data, database]);
  if (info.loading) return <Loading what="Connecting…" />;
  if (info.error || !info.data) {
    const needsPassword = /password/i.test(info.error);
    return (
      <>
        <p className="small"><a href="#/databases">Databases</a></p>
        <ErrorNote message={info.error} onRetry={info.reload} />
        {needsPassword && <form className="toolbar" onSubmit={async (e) => { e.preventDefault();
          await api.post(`/api/db/connections/${encodeURIComponent(id)}/password`, { password: pw }); setPw(""); info.reload(); }}>
          <label className="sr-only" htmlFor="dbpw">Password</label>
          <input id="dbpw" className="input" type="password" autoComplete="off" placeholder="Password" value={pw} onChange={(e) => setPw(e.target.value)} required />
          <button className="btn btn-primary">Connect</button>
        </form>}
      </>
    );
  }
  const d = info.data;
  const tabs: [string, string][] = d.kind === "sql" ? [["tables", "Tables"], ["query", "Query editor"], ["admin", "Server"], ["backups", "Backups"]]
    : d.kind === "document" ? [["tables", "Collections"], ["admin", "Server"]] : [["keys", "Keys"], ["admin", "Server"]];
  return (
    <>
      <p className="small"><a href="#/databases">Databases</a></p>
      <PageHead title={id} lede={<>{String(d.server.version ?? "")} · <span className={`pill ${d.read_only ? "info" : "warn"}`}>{d.read_only ? "Read-only" : "Administrative"}</span></>}>
        {d.databases.length > 1 && <>
          <label className="sr-only" htmlFor="dbsel">Database</label>
          <select id="dbsel" className="select" style={{ width: "auto" }} value={database} onChange={(e) => setDatabase(e.target.value)}>
            {d.databases.map((x) => <option key={x.name} value={x.name}>{x.name}{x.size_bytes ? ` (${bytes(x.size_bytes)})` : ""}</option>)}
          </select></>}
      </PageHead>
      <Tabs value={tab} onChange={setTab} tabs={tabs} />
      {tab === "tables" && <Tables id={id} database={database} kind={d.kind} readOnly={d.read_only} />}
      {tab === "query" && <QueryEditor id={id} database={database} readOnly={d.read_only} />}
      {tab === "keys" && <RedisKeys id={id} />}
      {tab === "admin" && <ServerAdmin id={id} engine={d.engine} database={database} readOnly={d.read_only} databases={d.databases} reload={info.reload} />}
      {tab === "backups" && <DbBackups id={id} database={database} engine={d.engine} readOnly={d.read_only} />}
    </>
  );
}

function Tables({ id, database, kind, readOnly }: { id: string; database: string; kind: string; readOnly: boolean }) {
  const list = useApi<{ name: string; type: string; rows: number | null }[]>(`/api/db/${encodeURIComponent(id)}/tables?database=${encodeURIComponent(database)}`);
  const [table, setTable] = useState("");
  if (list.loading) return <Loading />;
  if (list.error || !list.data) return <ErrorNote message={list.error} onRetry={list.reload} />;
  return (
    <div className="split">
      <section className="box" style={{ alignSelf: "start" }}>
        <div className="box-head"><h2>{kind === "document" ? "Collections" : "Tables"}</h2><span className="small muted">{list.data.length}</span></div>
        {list.data.length === 0 ? <Empty>None.</Empty> : list.data.map((t) => (
          <button key={t.name} className="list-btn" aria-current={table === t.name} onClick={() => setTable(t.name)}>
            {t.name} <span className="muted small">{t.rows ?? ""}{t.type !== "table" && t.type !== "base table" && t.type !== "collection" ? ` · ${t.type}` : ""}</span>
          </button>))}
      </section>
      <div>{table ? <TableView key={`${database}/${table}`} id={id} database={database} table={table} kind={kind} readOnly={readOnly}
        onDropped={() => { setTable(""); list.reload(); }} /> : <Empty>Choose a table to browse it.</Empty>}</div>
    </div>
  );
}

interface Page { columns: string[]; rows: unknown[][]; total: number; limit: number; offset: number }
interface Structure { columns: { name: string; type?: string; nullable?: boolean; default?: unknown; pk?: boolean }[]; indexes: Record<string, unknown>[]; foreign_keys: { column: string; references: string }[] }

function TableView({ id, database, table, kind, readOnly, onDropped }: { id: string; database: string; table: string; kind: string; readOnly: boolean; onDropped: () => void }) {
  const [tab, setTab] = useState("browse");
  const [offset, setOffset] = useState(0);
  const [order, setOrder] = useState("");
  const [filter, setFilter] = useState("{}");
  const base = `/api/db/${encodeURIComponent(id)}`;
  const q = `database=${encodeURIComponent(database)}&table=${encodeURIComponent(table)}`;
  const page = useApi<Page>(kind === "document" ? null : `${base}/browse?${q}&limit=50&offset=${offset}${order ? `&order=${encodeURIComponent(order)}` : ""}`);
  const structure = useApi<Structure>(kind === "sql" ? `${base}/table?${q}` : null);
  const [docs, setDocs] = useState<{ documents: unknown[]; total: number } | null>(null);
  const act = useAction(() => { page.reload(); structure.reload(); });
  const pk = (structure.data?.columns ?? []).filter((c) => c.pk).map((c) => c.name);
  const keyOf = (row: unknown[]) => Object.fromEntries(pk.map((k) => [k, row[page.data!.columns.indexOf(k)]]));
  const findDocs = async () => setDocs(await api.post(`${base}/find`, { database, collection: table, filter, limit: 50, skip: 0 }));
  useEffect(() => { if (kind === "document") findDocs().catch(() => undefined); }, [kind]); // eslint-disable-line
  return (
    <section className="box">
      <div className="box-head"><h2 className="mono">{table}</h2>
        {kind === "sql" && !readOnly && <button className="btn btn-sm btn-danger" onClick={() => act.run(`Drop ${table}`,
          () => withConfirm((confirm) => api.post(`${base}/drop-table`, { database, table, confirm }))).then(onDropped)}>Drop table…</button>}
      </div>
      <div className="box-body">
        <NoteView note={act.note} />
        {kind === "sql" && <Tabs value={tab} onChange={setTab} tabs={[["browse", "Browse"], ["structure", "Structure"], ...(readOnly ? [] : [["insert", "Insert row"]] as [string, string][])]} />}
        {kind === "document" ? (
          <>
            <form className="toolbar" onSubmit={(e) => { e.preventDefault(); act.run("Find", async () => { await findDocs(); return { message: "Done." }; }); }}>
              <label className="sr-only" htmlFor="mf">Filter</label>
              <input id="mf" className="input mono" value={filter} onChange={(e) => setFilter(e.target.value)} />
              <button className="btn">Find</button>
            </form>
            {docs && <><p className="small muted">{docs.total} documents match; showing {docs.documents.length}.</p>
              <pre className="log" style={{ maxHeight: 520 }}>{JSON.stringify(docs.documents, null, 2)}</pre></>}
          </>
        ) : tab === "browse" ? (page.loading ? <Loading /> : page.error || !page.data ? <ErrorNote message={page.error} /> : (
          <>
            <div className="toolbar" style={{ marginBottom: 8 }}>
              <span className="small muted">Rows {page.data.total ? offset + 1 : 0}–{Math.min(offset + 50, page.data.total)} of {page.data.total}</span>
              <button className="btn btn-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button>
              <button className="btn btn-sm" disabled={offset + 50 >= page.data.total} onClick={() => setOffset(offset + 50)}>Next</button>
            </div>
            <div className="table-scroll">
              <table>
                <thead><tr>{page.data.columns.map((c) => <th scope="col" key={c}><button className="list-btn" style={{ border: 0, padding: 0, minHeight: 0 }}
                  onClick={() => setOrder(c)}>{c}{order === c ? " ↓" : ""}</button></th>)}{!readOnly && pk.length > 0 && <th />}</tr></thead>
                <tbody>{page.data.rows.map((r, i) => (
                  <tr key={i}>{r.map((v, j) => <td className="cell" key={j} title={String(v ?? "NULL")}>{v === null ? <span className="muted">NULL</span> : String(v)}</td>)}
                    {!readOnly && pk.length > 0 && <td><div className="actions">
                      <button className="btn btn-sm" onClick={() => {
                        const col = window.prompt(`Column to change (${page.data!.columns.filter((c) => !pk.includes(c)).join(", ")}):`);
                        if (!col) return;
                        const value = window.prompt(`New value for ${col} (empty for NULL):`, String(r[page.data!.columns.indexOf(col)] ?? ""));
                        if (value === null) return;
                        act.run("Update row", () => withConfirm((confirm) => api.post(`${base}/rows?op=update`, { database, table, key: keyOf(r), values: { [col]: value === "" ? null : value }, confirm })));
                      }}>Edit</button>
                      <button className="btn btn-sm btn-danger" onClick={() => act.run("Delete row", () => withConfirm((confirm) => api.post(`${base}/rows?op=delete`, { database, table, key: keyOf(r), confirm })))}>Delete</button>
                    </div></td>}
                  </tr>))}</tbody>
              </table>
            </div>
            {!readOnly && pk.length === 0 && <p className="small muted">This table has no primary key, so rows are changed through the query editor.</p>}
          </>
        )) : tab === "structure" ? (structure.loading ? <Loading /> : structure.data && (
          <>
            <DataTable columns={["Column", "Type", "Null", "Default", "Key"]} rows={structure.data.columns.map((c) => [
              <span className="mono">{c.name}</span>, c.type ?? "", c.nullable ? "yes" : "no", c.default == null ? "" : String(c.default), c.pk ? "primary" : ""])} />
            <h3 style={{ margin: "16px 0 8px" }}>Indexes</h3>
            <DataTable columns={["Name", "Detail"]} empty="No indexes." rows={structure.data.indexes.map((x) => [
              <span className="mono">{String(x.name)}</span>, <span className="mono small">{String(x.definition ?? (x.columns as string[] | undefined)?.join(", ") ?? "")}{x.unique ? " (unique)" : ""}</span>])} />
            <h3 style={{ margin: "16px 0 8px" }}>Relationships</h3>
            <DataTable columns={["Column", "References"]} empty="No foreign keys." rows={structure.data.foreign_keys.map((f) => [<span className="mono">{f.column}</span>, <span className="mono">{f.references}</span>])} />
          </>
        )) : <InsertRow columns={structure.data?.columns ?? []} onInsert={(values) => act.run("Insert row", () => api.post(`${base}/rows?op=insert`, { database, table, values }), "Row inserted.")} />}
      </div>
    </section>
  );
}

function InsertRow({ columns, onInsert }: { columns: Structure["columns"]; onInsert: (v: Record<string, unknown>) => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  return (
    <form onSubmit={(e) => { e.preventDefault(); onInsert(Object.fromEntries(Object.entries(values).filter(([, v]) => v !== ""))); }}>
      <div className="grid">
        {columns.map((c) => (
          <div className="field" key={c.name}><label htmlFor={`ins-${c.name}`}>{c.name} <span className="muted small">{c.type}{c.pk ? ", key" : ""}</span></label>
            <input id={`ins-${c.name}`} className="input mono" value={values[c.name] ?? ""} placeholder={c.default == null ? "" : `default ${c.default}`}
              onChange={(e) => setValues({ ...values, [c.name]: e.target.value })} /></div>))}
      </div>
      <p className="small muted">Empty fields use the column's default. Values are sent as parameters, never pasted into SQL.</p>
      <button className="btn btn-primary">Insert row</button>
    </form>
  );
}

interface Result { columns: string[]; rows: unknown[][]; rowcount: number; truncated: boolean; ms: number }

function QueryEditor({ id, database, readOnly }: { id: string; database: string; readOnly: boolean }) {
  const [sql, setSql] = useState("SELECT 1;");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const history = useApi<{ id: number; sql: string; at: string; ms: number | null; rows: number | null; error: string }[]>(`/api/db/${encodeURIComponent(id)}/history`);
  const run = async () => {
    setBusy(true); setError("");
    try {
      const r = await withConfirm((confirm) => api.post<Result>(`/api/db/${encodeURIComponent(id)}/query`, { database, sql, confirm, limit: 500 }));
      if (r) setResult(r);
    } catch (e) { setError((e as ApiError).message); setResult(null); }
    setBusy(false);
    history.reload();
  };
  const exportCsv = async () => {
    const response = await fetch(`/api/db/${encodeURIComponent(id)}/export`, { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
      body: JSON.stringify({ database, sql }) });
    if (!response.ok) { setError((await response.json().catch(() => ({ detail: "Export failed." }))).detail); return; }
    const url = URL.createObjectURL(await response.blob());
    const a = document.createElement("a"); a.href = url; a.download = "query.csv"; a.click(); URL.revokeObjectURL(url);
  };
  return (
    <div className="cols">
      <div>
        <label htmlFor="sql" className="small" style={{ fontWeight: 600 }}>SQL {readOnly ? "(read-only connection: only reads run)" : "(statements that change data ask first)"}</label>
        <SqlEditor id="sql" value={sql} onChange={setSql} onRun={run} />
        <div className="actions" style={{ margin: "8px 0 16px" }}>
          <button className="btn btn-primary" onClick={run} disabled={busy}>{busy ? "Running…" : "Run (⌘ Enter)"}</button>
          <button className="btn" onClick={exportCsv} disabled={busy}>Export CSV</button>
        </div>
        {error && <ErrorNote message={error} />}
        {result && (
          <section className="box">
            <div className="box-head"><h2>Result</h2><span className="small muted">
              {result.columns.length ? `${result.rows.length} rows${result.truncated ? " (first 500)" : ""}` : `${result.rowcount} rows affected`} · {result.ms} ms</span></div>
            {result.columns.length > 0 && <DataTable columns={result.columns} rows={result.rows.map((r) => r.map((v) => v === null ? <span className="muted">NULL</span> : <span className="mono small">{String(v)}</span>))} />}
          </section>
        )}
      </div>
      <Box title="History">
        {history.data?.length ? history.data.map((h) => (
          <button key={h.id} className="list-btn" onClick={() => setSql(h.sql)} title="Load into the editor">
            <div className="mono small" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{h.sql}</div>
            <div className="small muted">{when(h.at)} · {h.error ? <span style={{ color: "var(--bad)" }}>error</span> : `${h.rows ?? 0} rows, ${h.ms ?? 0} ms`}</div>
          </button>)) : <Empty>Queries you run appear here.</Empty>}
      </Box>
    </div>
  );
}

function RedisKeys({ id }: { id: string }) {
  const [pattern, setPattern] = useState("*");
  const keys = useApi<{ key: string; type: string; ttl: number }[]>(`/api/db/${encodeURIComponent(id)}/keys?pattern=${encodeURIComponent(pattern)}`);
  const [value, setValue] = useState<{ key: string; data: unknown } | null>(null);
  return (
    <div className="split">
      <section className="box" style={{ alignSelf: "start" }}>
        <div className="box-head"><label className="sr-only" htmlFor="rp">Pattern</label>
          <input id="rp" className="input mono" value={pattern} onChange={(e) => setPattern(e.target.value || "*")} /></div>
        {keys.loading ? <Loading /> : keys.error ? <ErrorNote message={keys.error} /> : (keys.data ?? []).map((k) => (
          <button key={k.key} className="list-btn" aria-current={value?.key === k.key}
            onClick={async () => setValue({ key: k.key, data: await api.get(`/api/db/${encodeURIComponent(id)}/key?key=${encodeURIComponent(k.key)}`) })}>
            <span className="mono small">{k.key}</span> <span className="muted small">{k.type}{k.ttl > 0 ? ` · ttl ${k.ttl}s` : ""}</span>
          </button>))}
      </section>
      <div>{value ? <Box title={<span className="mono">{value.key}</span>}><pre className="log" style={{ margin: 16 }}>{JSON.stringify(value.data, null, 2)}</pre></Box>
        : <Empty>Choose a key to see its value.</Empty>}</div>
    </div>
  );
}

function ServerAdmin({ id, engine, readOnly, databases, reload }: { id: string; engine: string; database: string; readOnly: boolean; databases: { name: string }[]; reload: () => void }) {
  const data = useApi<{ variables: { name: string; value: string }[]; processes: Record<string, unknown>[]; users: Record<string, unknown>[] }>(`/api/db/${encodeURIComponent(id)}/admin`);
  const [q, setQ] = useState("");
  const act = useAction(reload);
  if (data.loading) return <Loading />;
  if (data.error || !data.data) return <ErrorNote message={data.error} />;
  const d = data.data;
  return (
    <>
      <NoteView note={act.note} />
      {["postgres", "mysql", "mariadb"].includes(engine) && (
        <Box title="Databases" actions={!readOnly && <button className="btn btn-sm" onClick={() => { const n = window.prompt("Name of the new database:");
          if (n) act.run("Create database", () => api.post(`/api/db/${encodeURIComponent(id)}/databases`, { name: n }), `Created ${n}.`); }}>Create database</button>}>
          <DataTable columns={["Database", ""]} rows={databases.map((x) => [<span className="mono">{x.name}</span>, !readOnly &&
            <button className="btn btn-sm btn-danger" onClick={() => { const typed = window.prompt(`Type ${x.name} to drop it. A backup is made first.`);
              if (typed === x.name) act.run(`Drop ${x.name}`, () => api.post(`/api/db/${encodeURIComponent(id)}/databases/drop`, { name: x.name, confirm: true })); }}>Drop…</button>])} />
        </Box>)}
      {d.processes.length > 0 && <Box title="Active connections"><DataTable columns={Object.keys(d.processes[0])} rows={d.processes.map((p) => Object.values(p).map((v) => <span className="small mono">{String(v ?? "")}</span>))} /></Box>}
      {d.users.length > 0 && <Box title="Users and roles"><DataTable columns={Object.keys(d.users[0])} rows={d.users.map((u) => Object.values(u).map((v) => String(v)))} />
        <p className="box-body small muted" style={{ margin: 0 }}>STACKLOOM shows users and roles but never changes them; use the database's own tools for that.</p></Box>}
      <Box title="Server variables" actions={<><label className="sr-only" htmlFor="vq">Filter</label><input id="vq" className="input" style={{ minWidth: 180 }} placeholder="Filter" value={q} onChange={(e) => setQ(e.target.value)} /></>}>
        <DataTable columns={["Name", "Value"]} rows={d.variables.filter((v) => !q || v.name.includes(q)).slice(0, 200).map((v) => [<span className="mono small">{v.name}</span>, <span className="mono small">{v.value}</span>])} />
      </Box>
    </>
  );
}

function DbBackups({ id, database, engine, readOnly }: { id: string; database: string; engine: string; readOnly: boolean }) {
  const list = useApi<{ items: { id: number; target: string; path: string; size: number; created_at: string; exists: boolean; verified_at: string | null }[] }>("/api/backups?kind=database");
  const act = useAction(list.reload);
  const mine = (list.data?.items ?? []).filter((b) => b.target.startsWith(`${id}/`));
  return (
    <>
      <NoteView note={act.note} />
      <Box title="Backups" actions={<button className="btn btn-sm btn-primary" onClick={() => act.run(`Back up ${database || id}`, () => api.post(`/api/db/${encodeURIComponent(id)}/backup`, { database, sql: "" }))}>Back up now</button>}>
        <DataTable columns={["Made", "Database", "Size", "Checked", ""]} empty="No backups of this connection yet." rows={mine.map((b) => [
          when(b.created_at), <span className="mono">{b.target.split("/").slice(1).join("/")}</span>, bytes(b.size), b.verified_at ? when(b.verified_at) : "-",
          <div className="actions">
            <button className="btn btn-sm" onClick={() => act.run("Verify", async () => { const r = await api.post<{ ok: boolean; detail: string }>(`/api/backups/${b.id}/verify`); if (!r.ok) throw new ApiError(400, r.detail); return { message: r.detail }; })}>Verify</button>
            <a className="btn btn-sm" href={`/api/backups/${b.id}/download`}>Download</a>
            {engine === "sqlite" && !readOnly && <button className="btn btn-sm btn-danger" onClick={() => act.run("Restore", () => withConfirm((confirm) => api.post(`/api/db/${encodeURIComponent(id)}/restore/${b.id}`, { confirm })))}>Restore</button>}
          </div>])} />
        {engine !== "sqlite" && <p className="box-body small muted" style={{ margin: 0 }}>Server backups use {engine === "postgres" ? "pg_dump (custom format); restore with pg_restore" : "mysqldump; restore with the mysql client"}.</p>}
      </Box>
    </>
  );
}
