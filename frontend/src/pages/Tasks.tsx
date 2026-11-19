import { useState } from "react";
import { type Task } from "../api";
import { ago, taskName, taskPill, when } from "../format";
import { useApi } from "../hooks";
import { Empty, ErrorNote, Loading, PageHead, Pill } from "../ui";

export function Tasks() {
  const { data, error, loading, reload } = useApi<Task[]>("/api/tasks",
    (d) => d.some((t) => t.status === "queued" || t.status === "running"), 2000);
  const [open, setOpen] = useState<number | null>(null);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  return (
    <>
      <PageHead title="Tasks" lede="Long jobs run in the background. This page updates while any of them is running." />
      <div className="box">
        {data.length === 0 ? <Empty>No tasks yet.</Empty> : data.map((t) => {
          const [label, tone] = taskPill(t.status);
          return (
            <div className="row" key={t.id} style={{ display: "block" }}>
              <div style={{ display: "flex", gap: 12, justifyContent: "space-between", flexWrap: "wrap" }}>
                <div className="row-main">
                  <div className="row-title">{taskName(t.kind)} {t.target && <span className="muted">{t.target}</span>}</div>
                  <div className="meta"><span>#{t.id}</span><span>{t.actor}</span><span title={when(t.created_at)}>{ago(t.created_at)}</span>
                    {t.message && <span>{t.message}</span>}</div>
                </div>
                <div className="actions">
                  <Pill label={label} tone={tone} />
                  {t.log && <button className="btn btn-sm" aria-expanded={open === t.id} onClick={() => setOpen(open === t.id ? null : t.id)}>Log</button>}
                </div>
              </div>
              {open === t.id && <pre className="log">{t.log}</pre>}
            </div>
          );
        })}
      </div>
    </>
  );
}
