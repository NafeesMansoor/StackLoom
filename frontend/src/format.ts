export function ago(iso?: string | null): string {
  if (!iso) return "never";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const s = (Date.now() - t) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function when(iso?: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function bytes(n?: number): string {
  if (!n) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}

const MAP_LABEL: Record<string, [string, string]> = {
  ready: ["Map ready", "ok"],
  refreshing: ["Refreshing", "warn"],
  none: ["No map", ""],
  error: ["Map error", "bad"],
};

export function mapPill(status: string): [string, string] {
  return MAP_LABEL[status] ?? [status, ""];
}

const TASK_LABEL: Record<string, [string, string]> = {
  queued: ["Queued", "warn"], running: ["Running", "info"], done: ["Done", "ok"], failed: ["Failed", "bad"], cancelled: ["Cancelled", ""],
};
export function taskPill(status: string): [string, string] {
  return TASK_LABEL[status] ?? [status, ""];
}

const TASK_NAME: Record<string, string> = {
  "codecortex.refresh": "Refresh project map",
  "discovery.scan": "Discover projects",
};
export function taskName(kind: string): string {
  return TASK_NAME[kind] ?? kind;
}
