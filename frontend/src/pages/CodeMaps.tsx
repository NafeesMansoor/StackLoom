import { useState } from "react";
import { api, type ApiError, type MapRecord } from "../api";
import { ago, mapPill } from "../format";
import { useApi } from "../hooks";
import { Empty, ErrorNote, Loading, PageHead, Pill } from "../ui";

export function CodeMaps() {
  const { data, error, loading, reload } = useApi<MapRecord[]>("/api/codecortex/maps",
    (d) => d.some((m) => m.status === "refreshing"), 2500);
  const [filter, setFilter] = useState("all");
  const [note, setNote] = useState("");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;

  const refresh = async (id: string) => {
    setNote("");
    try { await api.post(`/api/codecortex/${encodeURIComponent(id)}/refresh`, { rebuild: false }); reload(); }
    catch (e) { setNote((e as ApiError).message); }
  };
  const rows = data
    .filter((m) => filter === "all" || (filter === "ready" ? m.status === "ready" : filter === "missing" ? m.status === "none" || m.status === "error" : m.status === "refreshing"))
    .sort((a, b) => (b.last_opened ?? "").localeCompare(a.last_opened ?? "") || (a.name ?? "").localeCompare(b.name ?? ""));
  const count = (s: string[]) => data.filter((m) => s.includes(m.status)).length;

  return (
    <>
      <PageHead title="Project maps" lede={<>One CodeCortex engine, one map per project, saved in each project's <code>.codecortex/</code> where coding agents look for it.
        Projects opened in Claude Code are refreshed automatically.</>} />
      {note && <ErrorNote message={note} />}
      <div className="box">
        <div className="box-head">
          <div className="seg" role="group" aria-label="Filter maps">
            {[["all", `All ${data.length}`], ["ready", `Ready ${count(["ready"])}`], ["refreshing", `Refreshing ${count(["refreshing"])}`],
              ["missing", `No map ${count(["none", "error"])}`]].map(([k, l]) => (
              <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l}</button>))}
          </div>
        </div>
        {rows.length === 0 ? <Empty>No projects in this view.</Empty> : rows.map((m) => {
          const [label, tone] = mapPill(m.status);
          return (
            <div className="row" key={m.project_id}>
              <div className="row-main">
                <div className="row-title"><a href={`#/projects/${encodeURIComponent(m.project_id)}`}>{m.name ?? m.project_id}</a></div>
                <div className="meta">
                  {m.stats.nodes !== undefined && <span>{m.stats.nodes} symbols</span>}
                  {m.stats.files !== undefined && <span>{m.stats.files} files</span>}
                  {m.stats.languages?.length ? <span>{m.stats.languages.join(", ")}</span> : null}
                  <span>refreshed {ago(m.last_refresh)}</span>
                  {m.last_opened && <span>opened {ago(m.last_opened)}</span>}
                  {m.error && <span style={{ color: "var(--bad)" }}>Error: {m.error}</span>}
                </div>
              </div>
              <div className="actions">
                <Pill label={label} tone={tone} />
                <button className="btn btn-sm" disabled={m.status === "refreshing"} onClick={() => refresh(m.project_id)}>
                  {m.status === "none" ? "Build map" : "Refresh"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
