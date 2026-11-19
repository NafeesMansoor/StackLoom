import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { ago } from "./format";

interface Item { id: number; at: string; level: string; title: string; body: string; link: string; read: number }

// Unread count polled once a minute (the only idle polling in the dashboard).
export function Bell() {
  const [data, setData] = useState<{ unread: number; items: Item[] }>({ unread: 0, items: [] });
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const load = () => api.get<typeof data>("/api/notifications").then(setData).catch(() => undefined);
  useEffect(() => { load(); const t = setInterval(load, 60_000); return () => clearInterval(t); }, []);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button className="icon-btn" aria-expanded={open} aria-label={`Notifications, ${data.unread} unread`} onClick={() => { setOpen(!open); if (!open) load(); }}>
        Notices{data.unread > 0 && <span className="nav-count" style={{ marginLeft: 6, background: "var(--bad-fill)", color: "#fff" }}>{data.unread}</span>}
      </button>
      {open && (
        <div className="box bell-pop" role="dialog" aria-label="Notifications">
          <div className="box-head"><h2>Notifications</h2>
            {data.unread > 0 && <button className="btn btn-sm" onClick={() => api.post("/api/notifications/read").then(load)}>Mark all read</button>}</div>
          {data.items.length === 0 ? <div className="empty">Nothing yet. Finished and failed jobs, and apps that stop by themselves, show up here.</div>
            : data.items.slice(0, 20).map((n) => (
              <a key={n.id} className="row" href={n.link || "#/tasks"} onClick={() => setOpen(false)} style={{ color: "inherit", textDecoration: "none", display: "block" }}>
                <div className="row-title" style={{ fontWeight: n.read ? 400 : 600 }}>
                  <span className={`pill ${n.level === "error" ? "bad" : "info"}`} style={{ marginRight: 6 }}>{n.level === "error" ? "Failed" : "Done"}</span>{n.title}</div>
                <div className="meta"><span>{ago(n.at)}</span>{n.body && <span>{n.body.slice(0, 140)}</span>}</div>
              </a>))}
        </div>)}
    </div>
  );
}
