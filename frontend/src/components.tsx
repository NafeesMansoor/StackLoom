import { useState, type ReactNode } from "react";
import { type ApiError, type Task } from "./api";
import { isTask, waitTask } from "./actions";
import { ErrorNote } from "./ui";

export type Note = { tone: "ok" | "error" | "info"; text: string } | null;

export function NoteView({ note }: { note: Note }) {
  if (!note) return null;
  if (note.tone === "error") return <ErrorNote message={note.text} />;
  return <div className={`notice notice-${note.tone}`} role="status">{note.text}</div>;
}

// Runs an action; if it returns a task, waits for it. Reports the outcome in plain words.
export function useAction(after?: () => void) {
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState<Note>(null);
  const run = async (label: string, fn: () => Promise<unknown>, success?: string) => {
    setBusy(label); setNote(null);
    try {
      let result = await fn();
      if (result === null) { setBusy(""); return; }
      if (isTask(result)) {
        setNote({ tone: "info", text: `${label}: running in the background…` });
        result = await waitTask(result as Task, (t) => setNote({ tone: "info", text: `${label}: ${t.message || t.status}…` }));
        const t = result as Task;
        setNote(t.status === "done" ? { tone: "ok", text: t.message || `${label}: done.` } : { tone: "error", text: t.message || `${label} failed.` });
      } else {
        const r = result as { message?: string; output?: string };
        setNote({ tone: "ok", text: success ?? r?.message ?? `${label}: done.` });
      }
      after?.();
    } catch (e) {
      setNote({ tone: "error", text: (e as ApiError).message });
    } finally {
      setBusy("");
    }
  };
  return { busy, note, setNote, run };
}

export function Tabs({ tabs, value, onChange }: { tabs: [string, string][]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map(([k, label]) => (
        <button key={k} role="tab" className="tab" aria-selected={value === k} onClick={() => onChange(k)}>{label}</button>
      ))}
    </div>
  );
}

export function DataTable({ columns, rows, empty }: { columns: string[]; rows: ReactNode[][]; empty?: string }) {
  if (!rows.length) return <div className="empty">{empty ?? "Nothing to show."}</div>;
  return (
    <div className="table-scroll">
      <table>
        <thead><tr>{columns.map((c) => <th scope="col" key={c}>{c}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

export function Box({ title, actions, children }: { title: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="box">
      <div className="box-head"><h2>{title}</h2>{actions && <div className="actions">{actions}</div>}</div>
      {children}
    </section>
  );
}

const STATE: Record<string, [string, string]> = {
  running: ["Running", "ok"], partial: ["Partly running", "warn"], stopped: ["Stopped", "bad"],
  external: ["Running outside STACKLOOM", "info"], "docker-unavailable": ["Docker not running", "warn"],
  "not managed": ["No start command", ""], error: ["Error", "bad"], exited: ["Exited", "bad"], created: ["Created", ""],
  paused: ["Paused", "warn"], restarting: ["Restarting", "warn"], dead: ["Dead", "bad"],
  healthy: ["Healthy", "ok"], down: ["Down", "bad"], unhealthy: ["Unhealthy", "bad"], starting: ["Starting", "warn"],
};
export function StatePill({ state }: { state: string }) {
  const [label, tone] = STATE[state] ?? [state, ""];
  return <span className={`pill ${tone}`}>{label}</span>;
}
