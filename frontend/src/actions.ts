import { api, ApiError, type Task } from "./api";

// The server answers 409 when an action needs confirmation; ask with its own words, then retry.
export async function withConfirm<T>(call: (confirm: boolean) => Promise<T>): Promise<T | null> {
  try {
    return await call(false);
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      if (!window.confirm(e.message)) return null;
      return await call(true);
    }
    throw e;
  }
}

export async function waitTask(task: Task, onUpdate?: (t: Task) => void): Promise<Task> {
  let t = task;
  while (t.status === "queued" || t.status === "running") {
    await new Promise((r) => setTimeout(r, 1200));
    t = await api.get<Task>(`/api/tasks/${t.id}`);
    onUpdate?.(t);
  }
  return t;
}

export function isTask(x: unknown): x is Task {
  return !!x && typeof x === "object" && "status" in (x as object) && "kind" in (x as object);
}

export function download(url: string) {
  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
