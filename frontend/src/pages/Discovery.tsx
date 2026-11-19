import { useState } from "react";
import { api, type ApiError, type Task } from "../api";
import { ago } from "../format";
import { useApi } from "../hooks";
import { Empty, ErrorNote, Loading, PageHead } from "../ui";

interface Candidate {
  path: string; name: string; group: string; kind: string; stack: string[]; monorepo: boolean;
  components: { name: string; stack: string[] }[]; nested_repos: string[]; parent?: string; found_at: string;
  launch?: { command?: string[] };
}

export function Discovery() {
  const { data, error, loading, reload } = useApi<Candidate[]>("/api/discovery/candidates");
  const [task, setTask] = useState<Task | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const scan = async () => {
    setNote(null);
    try {
      let t = await api.post<Task>("/api/discovery/scan");
      setTask(t);
      while (t.status === "queued" || t.status === "running") {
        await new Promise((r) => setTimeout(r, 1000));
        t = await api.get<Task>(`/api/tasks/${t.id}`);
        setTask(t);
      }
      setNote({ ok: t.status === "done", text: t.message });
      reload();
    } catch (e) { setNote({ ok: false, text: (e as ApiError).message }); }
  };
  const adopt = async (c: Candidate) => {
    setNote(null);
    try {
      await api.post("/api/discovery/adopt", { path: c.path });
      setNote({ ok: true, text: `Registered ${c.name}. Its start command stays disabled until you review it.` });
      reload();
    } catch (e) { setNote({ ok: false, text: (e as ApiError).message }); }
  };
  const running = task && (task.status === "queued" || task.status === "running");

  return (
    <>
      <PageHead title="Discovery" lede="Finds code folders in your workspace that are not registered yet. It only reads files.">
        <button className="btn btn-primary" onClick={scan} disabled={!!running}>{running ? "Scanning…" : "Scan the workspace"}</button>
      </PageHead>
      <div aria-live="polite">
        {note && (note.ok ? <div className="notice notice-ok">{note.text}</div> : <ErrorNote message={note.text} />)}
      </div>
      {loading ? <Loading /> : error ? <ErrorNote message={error} onRetry={reload} /> : (
        <div className="box">
          <div className="box-head"><h2>Not registered</h2>
            {data?.length ? <span className="small muted">from the scan {ago(data[0].found_at)}</span> : null}</div>
          {!data?.length ? <Empty>Nothing waiting. Run a scan to look for new projects.</Empty> : data.map((c) => (
            <div className="row" key={c.path}>
              <div className="row-main">
                <div className="row-title">{c.name} <span className="muted small">{c.kind}{c.monorepo ? ", monorepo" : ""}</span></div>
                <div className="path">{c.path}</div>
                <div className="meta">
                  <span>group: {c.group}</span>
                  {c.stack.map((s) => <span className="chip" key={s}>{s}</span>)}
                  {c.components.length > 0 && <span>{c.components.length} components ({c.components.map((x) => x.name).join(", ")})</span>}
                  {c.parent && <span>own Git repository inside {c.parent.split("/").pop()}</span>}
                  {c.launch?.command && <span className="mono">{c.launch.command.join(" ")}</span>}
                </div>
              </div>
              <button className="btn btn-sm" onClick={() => adopt(c)}>Register</button>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
