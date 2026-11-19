import { useState } from "react";
import { api } from "../api";
import { withConfirm } from "../actions";
import { Box, DataTable, NoteView, useAction } from "../components";
import { ago } from "../format";
import { useApi, useText } from "../hooks";
import { Empty, ErrorNote, Loading, PageHead } from "../ui";

interface RepoSummary { project: string; name: string; repo: string; branch: string; changed: number; ahead: number; behind: number;
  conflicts: number; operation: string | null; remotes: { name: string; url: string }[]; last_commit: { date: string; subject: string } | null; error?: string }

export function GitList() {
  const { data, error, loading, reload } = useApi<RepoSummary[]>("/api/git");
  if (loading) return <Loading what="Reading repositories…" />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  return (
    <>
      <PageHead title="Git repositories" lede="Every repository in the workspace. Reading is free; anything that changes a repository or talks to its remote asks first.">
        <button className="btn" onClick={reload}>Refresh</button>
      </PageHead>
      <Box title={`${data.length} repositories`}>
        {data.length === 0 ? <Empty>No registered project is in a Git repository.</Empty> : data.map((r) => (
          <div className="row" key={r.repo}>
            <div className="row-main">
              <div className="row-title"><a href={`#/git/${encodeURIComponent(r.project)}`}>{r.name}</a> <span className="mono small muted">{r.branch}</span></div>
              <div className="meta">
                <span>{r.remotes.map((x) => x.url).join(", ") || "no remote"}</span>
                {r.last_commit && <span>last commit {ago(r.last_commit.date)}: {r.last_commit.subject}</span>}
              </div>
            </div>
            <div className="actions">
              {r.conflicts > 0 && <span className="pill bad">{r.conflicts} conflicts</span>}
              {r.operation && <span className="pill warn">{r.operation} in progress</span>}
              {r.ahead > 0 && <span className="pill info">ahead {r.ahead}</span>}
              {r.behind > 0 && <span className="pill warn">behind {r.behind}</span>}
              <span className={`pill ${r.changed ? "warn" : "ok"}`}>{r.changed ? `${r.changed} changed` : "Clean"}</span>
            </div>
          </div>))}
      </Box>
    </>
  );
}

interface RepoDetail {
  repo: string;
  status: { branch: string; upstream: string | null; ahead: number; behind: number; operation: string | null; clean: boolean;
    changed: { path: string; xy: string; staged: boolean; unstaged: boolean }[]; untracked: string[]; conflicts: string[]; remotes: { name: string; url: string }[] };
  log: { short: string; author: string; date: string; subject: string }[];
  branches: { current: boolean; name: string; remote: boolean; commit: string; upstream: string }[];
  stashes: { ref: string; message: string }[];
}

export function GitRepo({ project }: { project: string }) {
  const { data, error, loading, reload } = useApi<RepoDetail>(`/api/git/${encodeURIComponent(project)}`);
  const [file, setFile] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const act = useAction(reload);
  const diff = useText(file !== null ? `/api/git/${encodeURIComponent(project)}/diff${file ? `?path=${encodeURIComponent(file)}` : ""}` : null);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  const st = data.status;
  const git = (action: string, extra: Record<string, unknown> = {}, label = action) =>
    act.run(`git ${label}`, async () => {
      const r = await withConfirm((confirm) => api.post<{ output: string }>(`/api/git/${encodeURIComponent(project)}`, { action, confirm, ...extra }));
      return r && { message: (r.output || "Done.").trim().split("\n").slice(-3).join(" ") };
    });
  const files = [...st.changed.map((c) => c.path), ...st.untracked];
  return (
    <>
      <p className="small"><a href="#/git">Git repositories</a></p>
      <PageHead title={project} lede={<><span className="mono">{st.branch}</span>{st.upstream ? ` tracking ${st.upstream}` : ", no upstream"} · <span className="path">{data.repo}</span></>}>
        <button className="btn" onClick={() => git("fetch")}>Fetch</button>
        <button className="btn" onClick={() => git("pull")} disabled={!st.upstream}>Pull{st.behind ? ` (${st.behind})` : ""}</button>
        <button className="btn" onClick={() => git("push")} disabled={!st.remotes.length}>Push{st.ahead ? ` (${st.ahead})` : ""}</button>
      </PageHead>
      <NoteView note={act.note} />
      {st.operation && <div className="notice notice-warn">A {st.operation} is in progress{st.conflicts.length ? ` with ${st.conflicts.length} conflicted files` : ""}.
        Resolve the conflicts in your editor and commit, or <button className="btn btn-sm" onClick={() => git("abort", {}, `abort ${st.operation}`)}>Abort the {st.operation}</button></div>}
      <div className="cols">
        <div>
          <Box title={st.clean ? "Working tree clean" : `${files.length} changed files`} actions={files.length > 0 && <button className="btn btn-sm" onClick={() => setFile("")}>Full diff</button>}>
            {st.conflicts.map((c) => <div className="row" key={c}><span className="mono small">{c}</span><span className="pill bad">Conflict</span></div>)}
            {files.map((f) => (
              <div className="row" key={f}>
                <label style={{ display: "flex", gap: 8, alignItems: "center", minHeight: 32 }} className="mono small">
                  <input type="checkbox" checked={picked.includes(f)} onChange={() => setPicked(picked.includes(f) ? picked.filter((x) => x !== f) : [...picked, f])} />{f}
                </label>
                <div className="actions">
                  <span className="muted small">{st.untracked.includes(f) ? "new" : st.changed.find((c) => c.path === f)?.xy.replace(/\./g, "·")}</span>
                  {!st.untracked.includes(f) && <button className="btn btn-sm" onClick={() => setFile(f)}>Diff</button>}
                </div>
              </div>))}
            {files.length > 0 && (
              <form className="box-body" onSubmit={(e) => { e.preventDefault(); git("commit", { message, files: picked }); setMessage(""); setPicked([]); }}>
                <div className="field"><label htmlFor="cm">Commit message</label>
                  <textarea id="cm" className="input textarea" value={message} onChange={(e) => setMessage(e.target.value)} required /></div>
                <div className="actions">
                  <button className="btn btn-primary" disabled={!picked.length}>Commit {picked.length || ""} selected</button>
                  <button type="button" className="btn" onClick={() => git("stash_push", {}, "stash")}>Stash all changes</button>
                </div>
              </form>)}
          </Box>
          {file !== null && <Box title={file || "All changes"} actions={<button className="btn btn-sm" onClick={() => setFile(null)}>Close</button>}>
            {diff.loading ? <Loading /> : <pre className="log" style={{ margin: 16, maxHeight: 480 }}>{diff.data || diff.error || "No differences."}</pre>}
          </Box>}
          <Box title="Recent commits">
            <DataTable columns={["Commit", "Message", "Author", "When"]} rows={data.log.map((c) => [<span className="mono">{c.short}</span>, c.subject, c.author, ago(c.date)])} />
          </Box>
        </div>
        <div>
          <Box title="Branches" actions={<button className="btn btn-sm" onClick={() => { const b = window.prompt("New branch name:"); if (b) git("switch", { branch: b, create: true }, `switch -c ${b}`); }}>New branch</button>}>
            {data.branches.filter((b) => !b.remote).map((b) => (
              <div className="row" key={b.name}>
                <span className="mono small" style={{ wordBreak: "break-all" }}>{b.current ? "● " : ""}{b.name}{b.upstream ? <span className="muted"> → {b.upstream}</span> : null}</span>
                {!b.current && <button className="btn btn-sm" onClick={() => git("switch", { branch: b.name }, `switch ${b.name}`)}>Switch</button>}
              </div>))}
            {data.branches.some((b) => b.remote) && <details className="box-body small">
              <summary>{data.branches.filter((b) => b.remote).length} remote branches</summary>
              {data.branches.filter((b) => b.remote).map((b) => <div key={b.name} className="mono" style={{ wordBreak: "break-all" }}>{b.name}</div>)}
            </details>}
          </Box>
          <Box title="Stashes">
            {data.stashes.length === 0 ? <Empty>No stashes.</Empty> : data.stashes.map((s, i) => (
              <div className="row" key={s.ref}><span className="small">{s.message}</span>
                {i === 0 && <button className="btn btn-sm" onClick={() => git("stash_pop", {}, "stash pop")}>Apply and drop</button>}</div>))}
          </Box>
          <Box title="Remotes">{st.remotes.length === 0 ? <Empty>No remote.</Empty> : st.remotes.map((r) => <div className="row" key={r.name}><span className="mono small">{r.name}</span><span className="path">{r.url}</span></div>)}</Box>
        </div>
      </div>
    </>
  );
}
