import { type Overview as Data } from "../api";
import { ago, when } from "../format";
import { useApi } from "../hooks";
import { Empty, ErrorNote, Loading, PageHead } from "../ui";

export function Overview() {
  const { data, error, loading, reload } = useApi<Data>("/api/overview", (d) => d.tasks_running > 0, 4000);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  const services = data.by_kind.service ?? 0;
  return (
    <>
      <PageHead title="Overview" lede={data.workspaces.length ? `Workspace: ${data.workspaces.join(", ")}` : undefined}>
        <a className="btn" href="#/discovery">Discover projects</a>
        <a className="btn btn-primary" href="#/projects">Open projects</a>
      </PageHead>
      {!data.workspaces.length && (
        <div className="notice notice-warn">
          No workspace folder is set yet. <a href="#/settings">Add one in Settings</a>, then run discovery.
        </div>
      )}
      <div className="grid">
        <Stat label="Projects" value={data.projects} note={`${data.groups} groups`} href="#/projects" />
        <Stat label="Apps with services" value={services} note="start and stop arrive in phase 2" />
        <Stat label="Project maps ready" value={data.maps.ready}
          note={data.maps.refreshing ? `${data.maps.refreshing} refreshing` : `${data.maps.missing} without a map`} href="#/codecortex" />
        <Stat label="Waiting for review" value={data.candidates} note="found by discovery" href="#/discovery" />
      </div>
      <div className="cols">
        <section className="box" aria-labelledby="recent-h">
          <div className="box-head">
            <h2 id="recent-h">Recently opened in Claude Code</h2>
            <a className="small" href="#/codecortex">All maps</a>
          </div>
          {data.recently_opened.length === 0 ? (
            <Empty>No Claude Code sessions in the last few days. Projects you open appear here, and their maps are refreshed for the agent.</Empty>
          ) : data.recently_opened.map((r) => (
            <div className="row" key={r.path}>
              <div className="row-main">
                <div className="row-title">
                  {r.project ? <a href={`#/projects/${encodeURIComponent(r.project)}`}>{r.name}</a> : r.name}
                  {!r.project && <span className="muted small"> · not registered</span>}
                </div>
                <div className="path">{r.path}</div>
              </div>
              <span className="small muted" title={when(r.last_opened)}>{ago(r.last_opened)}</span>
            </div>
          ))}
        </section>
        <section className="box" aria-labelledby="act-h">
          <div className="box-head">
            <h2 id="act-h">Recent activity</h2>
            <a className="small" href="#/activity">All</a>
          </div>
          {data.activity.length === 0 ? <Empty>Nothing yet.</Empty> : data.activity.map((a) => (
            <div className="row" key={a.id}>
              <div className="row-main">
                <div><span className="mono">{a.action}</span> {a.target && <span className="muted">{a.target}</span>}</div>
                <div className="meta"><span>{a.actor}</span><span title={when(a.at)}>{ago(a.at)}</span>
                  {a.result !== "ok" && <span style={{ color: "var(--bad)" }}>{a.result}</span>}</div>
              </div>
            </div>
          ))}
        </section>
      </div>
    </>
  );
}

function Stat({ label, value, note, href }: { label: string; value: number; note?: string; href?: string }) {
  const body = (
    <>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {note && <div className="stat-note">{note}</div>}
    </>
  );
  return href ? <a className="stat" href={href} style={{ color: "inherit", textDecoration: "none" }}>{body}</a>
    : <div className="stat">{body}</div>;
}
