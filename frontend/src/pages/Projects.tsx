import { useMemo, useState } from "react";
import { type ProjectRow } from "../api";
import { ago, mapPill } from "../format";
import { useApi } from "../hooks";
import { Empty, ErrorNote, Loading, PageHead, Pill } from "../ui";

export function Projects() {
  const { data, error, loading, reload } = useApi<ProjectRow[]>("/api/projects");
  const [q, setQ] = useState("");
  const [group, setGroup] = useState("");
  const groups = useMemo(() => [...new Set((data ?? []).map((p) => p.group))].sort(), [data]);
  const rows = useMemo(() => (data ?? []).filter((p) =>
    (!group || p.group === group) &&
    (!q || `${p.id} ${p.name} ${p.path} ${p.stack.join(" ")}`.toLowerCase().includes(q.toLowerCase()))), [data, q, group]);

  if (loading) return <Loading />;
  if (error) return <ErrorNote message={error} onRetry={reload} />;
  return (
    <>
      <PageHead title="Projects" lede={`${data?.length ?? 0} registered. Registering a project never changes its files.`}>
        <a className="btn btn-primary" href="#/discovery">Discover projects</a>
      </PageHead>
      <div className="box">
        <div className="box-head">
          <div className="toolbar" style={{ flex: 1 }}>
            <label className="sr-only" htmlFor="pq">Filter projects</label>
            <input id="pq" className="input" placeholder="Filter by name, path or stack" value={q} onChange={(e) => setQ(e.target.value)} />
            <label className="sr-only" htmlFor="pg">Group</label>
            <select id="pg" className="select" style={{ width: "auto" }} value={group} onChange={(e) => setGroup(e.target.value)}>
              <option value="">All groups</option>
              {groups.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          </div>
        </div>
        {rows.length === 0 ? (
          <Empty>{data?.length ? "No project matches the filter." : <>No projects yet. <a href="#/discovery">Run discovery</a> or import the ResearchOS registry with <code>stackloom import researchos</code>.</>}</Empty>
        ) : rows.map((p) => {
          const [label, tone] = mapPill(p.map_status);
          return (
            <div className="row" key={p.id}>
              <div className="row-main">
                <div className="row-title"><a href={`#/projects/${encodeURIComponent(p.id)}`}>{p.name}</a>{" "}
                  <span className="muted small mono">{p.id}</span></div>
                <div className="meta">
                  <span>{p.group}</span><span>{p.kind}</span>
                  {p.stack.slice(0, 4).map((s) => <span key={s} className="chip">{s}</span>)}
                  {p.last_opened && <span>opened {ago(p.last_opened)}</span>}
                </div>
              </div>
              <Pill label={label} tone={tone} />
            </div>
          );
        })}
      </div>
    </>
  );
}
