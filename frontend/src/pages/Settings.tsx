import { useState, type FormEvent } from "react";
import { api, type ApiError } from "../api";
import { useApi } from "../hooks";
import { ErrorNote, Loading, PageHead } from "../ui";

interface Data { workspaces: string[]; port_pool: [number, number]; auto_refresh_maps: boolean; recent_window_hours: number; home: string }

export function Settings() {
  const { data, error, loading, reload } = useApi<Data>("/api/settings");
  const [path, setPath] = useState("");
  const [note, setNote] = useState("");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;

  const add = async (e: FormEvent) => {
    e.preventDefault(); setNote("");
    try { await api.post("/api/settings/workspaces", { path }); setPath(""); reload(); }
    catch (err) { setNote((err as ApiError).message); }
  };
  const remove = async (w: string) => {
    if (!confirm(`Stop managing ${w}? Projects stay registered and nothing on disk changes.`)) return;
    try { await api.del("/api/settings/workspaces", { path: w }); reload(); }
    catch (err) { setNote((err as ApiError).message); }
  };
  return (
    <>
      <PageHead title="Settings" />
      {note && <ErrorNote message={note} />}
      <section className="box">
        <div className="box-head"><h2>Workspace folders</h2></div>
        {data.workspaces.map((w) => (
          <div className="row" key={w}><span className="path">{w}</span>
            <button className="btn btn-sm btn-danger" onClick={() => remove(w)}>Remove</button></div>
        ))}
        <form className="box-body" onSubmit={add}>
          <div className="field" style={{ marginBottom: 8 }}>
            <label htmlFor="ws">Add a folder</label>
            <input id="ws" className="input mono" placeholder="/Users/you/Code" value={path} onChange={(e) => setPath(e.target.value)} required />
            <span className="field-help">Discovery looks for projects inside it. Nothing in the folder is changed.</span>
          </div>
          <button className="btn">Add folder</button>
        </form>
      </section>
      <section className="box">
        <div className="box-head"><h2>Coding agents</h2></div>
        <div className="box-body">
          <p style={{ marginTop: 0 }}>
            {data.auto_refresh_maps ? "While STACKLOOM runs, it checks once a minute which projects you opened in Claude Code in the last "
              + `${data.recent_window_hours} hours and refreshes their maps.` : "Automatic map refresh is turned off in config.toml."}
          </p>
          <p>For a refresh the moment a session starts, even when the dashboard is closed, add the Claude Code hook in a terminal:</p>
          <pre className="log">stackloom agent hook install</pre>
          <p className="small muted" style={{ marginBottom: 0 }}>It adds one SessionStart entry to ~/.claude/settings.json and keeps a backup. Remove it with <code>stackloom agent hook uninstall</code>.</p>
        </div>
      </section>
      <section className="box">
        <div className="box-head"><h2>This installation</h2></div>
        <div className="box-body">
          <dl className="kv">
            <dt>Data folder</dt><dd className="path">{data.home}</dd>
            <dt>Port range</dt><dd className="mono">{data.port_pool[0]}–{data.port_pool[1]}</dd>
          </dl>
        </div>
      </section>
    </>
  );
}
