import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { Core } from "cytoscape";
import { api, type ProjectRow } from "../api";
import { NoteView, useAction } from "../components";
import type { GEdge, GNode } from "../GraphCanvas";
import { useApi } from "../hooks";
import { Empty, ErrorNote, Loading, PageHead } from "../ui";

const GraphCanvas = lazy(() => import("../GraphCanvas").then((m) => ({ default: m.GraphCanvas })));

interface Summary { node_kinds: Record<string, number>; edge_kinds: Record<string, number>; default_node_kinds: string[]; default_edge_kinds: string[];
  nodes: number; edges: number; languages: string[]; derived_stale: boolean }
interface GraphData { nodes: GNode[]; edges: GEdge[]; total_matching: number; truncated: boolean; summary: Summary }
interface NodeDetail { id: string; name: string; kind: string; file: string; abs_file: string; line: number; end_line: number; language: string;
  centrality: Record<string, number | null>; incoming: { kind: string; id: string; name: string | null; node_kind: string | null }[];
  outgoing: { kind: string; id: string; name: string | null; node_kind: string | null }[]; source: string }

const LEGEND: [string, string][] = [["File/module", "#4285d4"], ["Class", "#16a36a"], ["Function", "#e6a23c"], ["Endpoint", "#dc5757"], ["Test", "#8a93b7"]];

export function Graph({ project }: { project?: string }) {
  const projects = useApi<ProjectRow[]>("/api/projects");
  const withMaps = (projects.data ?? []).filter((p) => p.map_status === "ready");
  const [chosen, setChosen] = useState(project ?? "");
  useEffect(() => { if (!chosen && withMaps.length) setChosen(withMaps[0].id); }, [withMaps.length]); // eslint-disable-line
  return (
    <>
      <PageHead title="Graph explorer" lede="Explore a project's CodeCortex map. Viewing never re-indexes; build or refresh maps on the Project maps page.">
        <label className="sr-only" htmlFor="gp">Project</label>
        <select id="gp" className="select" style={{ width: "auto" }} value={chosen}
          onChange={(e) => { setChosen(e.target.value); window.location.hash = `#/graph/${encodeURIComponent(e.target.value)}`; }}>
          {withMaps.length === 0 && <option value="">No project has a map yet</option>}
          {withMaps.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </PageHead>
      {projects.loading ? <Loading /> : !chosen ? <Empty>Build a map on the <a href="#/codecortex">Project maps</a> page first.</Empty>
        : <Explorer key={chosen} project={chosen} />}
    </>
  );
}

function Explorer({ project }: { project: string }) {
  const summary = useApi<Summary>(`/api/graph/${encodeURIComponent(project)}/summary`);
  const [nodeKinds, setNodeKinds] = useState<string[] | null>(null);
  const [edgeKinds, setEdgeKinds] = useState<string[] | null>(null);
  const [limit, setLimit] = useState(300);
  const [focus, setFocus] = useState<string | null>(null);
  const [layout, setLayout] = useState("force");
  const [highlight, setHighlight] = useState<"none" | "hotspots" | "neighbours">("neighbours");
  const [selected, setSelected] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<{ id: string; name: string; kind: string; file: string }[]>([]);
  const cy = useRef<Core | null>(null);
  const act = useAction();
  const dark = useMemo(() => document.documentElement.getAttribute("data-theme") === "dark" ||
    (!document.documentElement.getAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches), []);
  useEffect(() => { if (summary.data && !nodeKinds) { setNodeKinds(summary.data.default_node_kinds); setEdgeKinds(summary.data.default_edge_kinds); } }, [summary.data]); // eslint-disable-line
  const query = nodeKinds && edgeKinds ? `/api/graph/${encodeURIComponent(project)}?node_kinds=${nodeKinds.join(",")}&edge_kinds=${edgeKinds.join(",")}`
    + `&limit=${limit}${focus ? `&focus=${encodeURIComponent(focus)}&depth=2` : ""}` : null;
  const graph = useApi<GraphData>(query);
  const detail = useApi<NodeDetail>(selected ? `/api/graph/${encodeURIComponent(project)}/node?id=${encodeURIComponent(selected)}` : null);

  useEffect(() => {
    if (q.trim().length < 2) { setHits([]); return; }
    const t = setTimeout(() => api.get<typeof hits>(`/api/graph/${encodeURIComponent(project)}/search?q=${encodeURIComponent(q)}`).then(setHits).catch(() => setHits([])), 250);
    return () => clearTimeout(t);
  }, [q, project]);

  if (summary.loading) return <Loading />;
  if (summary.error || !summary.data) return <ErrorNote message={summary.error} onRetry={summary.reload} />;
  const s = summary.data;
  const toggle = (list: string[] | null, set: (v: string[]) => void, k: string) => set(list?.includes(k) ? list.filter((x) => x !== k) : [...(list ?? []), k]);
  const top = [...(graph.data?.nodes ?? [])].sort((a, b) => b.centrality - a.centrality).slice(0, 12);
  const pick = (id: string) => {
    if (graph.data?.nodes.some((n) => n.id === id)) setSelected(id);
    else { setFocus(id); setSelected(id); }
  };
  const exportPng = () => {
    if (!cy.current) return;
    const a = document.createElement("a");
    a.href = cy.current.png({ full: true, scale: 2, bg: dark ? "#1c1f25" : "#ffffff" });
    a.download = `${project}-graph.png`; a.click();
  };
  const exportUrl = (fmt: string) => `/api/graph/${encodeURIComponent(project)}/export?fmt=${fmt}&node_kinds=${(nodeKinds ?? []).join(",")}&edge_kinds=${(edgeKinds ?? []).join(",")}`;

  return (
    <>
      <NoteView note={act.note} />
      {s.derived_stale && <div className="notice notice-warn">Centrality and clusters come from an earlier build. Rebuild the map to recompute them.</div>}
      <div className="box"><div className="box-body" style={{ display: "grid", gap: 10 }}>
        <div className="toolbar">
          <div className="seg" role="group" aria-label="Layout">
            {[["force", "Force"], ["hierarchy", "Hierarchy"], ["circle", "Circle"], ["grid", "Grid"]].map(([k, l]) => (
              <button key={k} aria-pressed={layout === k} onClick={() => setLayout(k)}>{l}</button>))}
          </div>
          <div className="seg" role="group" aria-label="Highlight">
            {[["neighbours", "Neighbours"], ["hotspots", "Hotspots"], ["none", "Nothing"]].map(([k, l]) => (
              <button key={k} aria-pressed={highlight === k} onClick={() => setHighlight(k as typeof highlight)}>{l}</button>))}
          </div>
          <label className="small" htmlFor="glim">Nodes</label>
          <select id="glim" className="select" style={{ width: "auto" }} value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
            {[100, 300, 600, 1200, 2500].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          {focus && <button className="btn btn-sm" onClick={() => setFocus(null)}>Show whole map</button>}
          <span style={{ flex: 1 }} />
          <button className="btn btn-sm" onClick={exportPng}>PNG</button>
          <a className="btn btn-sm" href={exportUrl("json")}>JSON</a>
          <a className="btn btn-sm" href={exportUrl("graphml")}>GraphML</a>
        </div>
        <div className="checks" aria-label="Symbol kinds">
          <span className="small muted">Symbols:</span>
          {Object.entries(s.node_kinds).map(([k, n]) => (
            <label key={k}><input type="checkbox" checked={nodeKinds?.includes(k) ?? false} onChange={() => toggle(nodeKinds, setNodeKinds, k)} />{k} <span className="muted">{n}</span></label>))}
        </div>
        <div className="checks" aria-label="Relationship kinds">
          <span className="small muted">Relationships:</span>
          {Object.entries(s.edge_kinds).map(([k, n]) => (
            <label key={k}><input type="checkbox" checked={edgeKinds?.includes(k) ?? false} onChange={() => toggle(edgeKinds, setEdgeKinds, k)} />{k} <span className="muted">{n}</span></label>))}
        </div>
      </div></div>

      <div className="graph-wrap">
        <div>
          {graph.loading ? <Loading what="Loading the map…" /> : graph.error || !graph.data ? <ErrorNote message={graph.error} onRetry={graph.reload} /> : (
            <>
              <Suspense fallback={<Loading what="Loading the graph view…" />}>
                <GraphCanvas nodes={graph.data.nodes} edges={graph.data.edges} layout={layout} selected={selected} highlight={highlight}
                  onSelect={setSelected} onReady={(c) => { cy.current = c; }} dark={dark} />
              </Suspense>
              <div className="toolbar" style={{ marginTop: 8, justifyContent: "space-between" }}>
                <span className="small muted">{graph.data.nodes.length} symbols and {graph.data.edges.length} relationships shown
                  {graph.data.truncated ? ` (the ${graph.data.nodes.length} most central of ${graph.data.total_matching})` : ""}{focus ? ", around the chosen symbol" : ""}.</span>
                <span className="legend">{LEGEND.map(([l, c]) => <span key={l}><i style={{ background: c }} />{l}</span>)}<span><i style={{ border: "2px solid #dc5757" }} />hotspot</span></span>
              </div>
            </>
          )}
        </div>
        <div>
          <section className="box">
            <div className="box-head"><label htmlFor="gq"><h2>Find a symbol</h2></label></div>
            <div className="box-body" style={{ paddingBottom: 8 }}>
              <input id="gq" className="input" placeholder="Function, class or file name" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            {hits.map((h) => <button key={h.id} className="list-btn" onClick={() => pick(h.id)}><span className="mono small">{h.name}</span> <span className="muted small">{h.kind} · {h.file}</span></button>)}
          </section>
          {selected && detail.data ? (
            <section className="box">
              <div className="box-head"><h2 className="mono" style={{ wordBreak: "break-all" }}>{detail.data.name}</h2>
                <button className="btn btn-sm" onClick={() => { setFocus(detail.data!.id); }}>Focus</button></div>
              <div className="box-body">
                <dl className="kv">
                  <dt>Kind</dt><dd>{detail.data.kind}</dd>
                  <dt>File</dt><dd className="path">{detail.data.file}:{detail.data.line}</dd>
                  <dt>Called by</dt><dd>{detail.data.centrality.fan_in ?? 0}</dd>
                  <dt>Calls</dt><dd>{detail.data.centrality.fan_out ?? 0}</dd>
                  <dt>Centrality</dt><dd>{(detail.data.centrality.composite_score ?? 0).toFixed(4)}</dd>
                </dl>
                <div className="actions" style={{ margin: "10px 0" }}>
                  <a className="btn btn-sm" href={`vscode://file${detail.data.abs_file}:${detail.data.line || 1}`}>Open in VS Code</a>
                  <button className="btn btn-sm" onClick={() => { navigator.clipboard?.writeText(`${detail.data!.abs_file}:${detail.data!.line}`); }}>Copy path</button>
                </div>
                {detail.data.source && <pre className="log" style={{ maxHeight: 220 }}>{detail.data.source}</pre>}
                <Relations title="Incoming" items={detail.data.incoming} onPick={pick} />
                <Relations title="Outgoing" items={detail.data.outgoing} onPick={pick} />
              </div>
            </section>
          ) : selected && detail.error ? <ErrorNote message={detail.error} /> : (
            <section className="box">
              <div className="box-head"><h2>Most connected</h2></div>
              {top.map((n) => <button key={n.id} className="list-btn" onClick={() => setSelected(n.id)}>
                <span className="mono small">{n.name}</span> <span className="muted small">{n.kind}{n.hotspot ? " · hotspot" : ""}</span></button>)}
            </section>
          )}
        </div>
      </div>
    </>
  );
}

function Relations({ title, items, onPick }: { title: string; items: NodeDetail["incoming"]; onPick: (id: string) => void }) {
  const [all, setAll] = useState(false);
  if (!items.length) return null;
  const shown = all ? items : items.slice(0, 8);
  return (
    <>
      <h3 style={{ margin: "12px 0 4px" }}>{title} ({items.length})</h3>
      {shown.map((r, i) => (
        <button key={i} className="list-btn" style={{ paddingLeft: 0 }} onClick={() => r.name && onPick(r.id)} disabled={!r.name}>
          <span className="chip">{r.kind}</span> <span className="mono small">{r.name ?? r.id.split("/").pop()}</span>
          {!r.name && <span className="muted small"> (outside the map)</span>}
        </button>))}
      {items.length > 8 && <button className="btn btn-sm" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${items.length}`}</button>}
    </>
  );
}

