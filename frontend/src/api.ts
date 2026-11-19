// Same-origin API client. The session lives in an HttpOnly cookie; mutating
// requests carry the session's CSRF token.
let csrf = "";

export function setCsrf(token: string) {
  csrf = token;
}

export function csrfToken(): string {
  return csrf;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrf;
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "STACKLOOM is not answering. Is it still running? Start it again with `stackloom`.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : `Request failed (${response.status}).`;
    throw new ApiError(response.status, detail);
  }
  return data as T;
}

async function text(path: string): Promise<string> {
  const response = await fetch(path, { credentials: "same-origin" }).catch(() => null);
  if (!response) throw new ApiError(0, "STACKLOOM is not answering.");
  const body = await response.text();
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try { detail = JSON.parse(body).detail ?? detail; } catch { /* plain text */ }
    throw new ApiError(response.status, detail);
  }
  return body;
}

export const api = {
  text,
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body: unknown = {}) => request<T>("POST", path, body),
  del: <T>(path: string, body?: unknown) => request<T>("DELETE", path, body),
};

export interface Me { username: string; must_change_password: boolean; csrf: string }
export interface Health { version: string; copyright: string; copyright_url: string }
export interface Task {
  id: number; kind: string; target: string; status: string; message: string; log: string;
  actor: string; created_at: string; started_at: string | null; finished_at: string | null;
}
export interface Activity { id: number; at: string; actor: string; action: string; target: string; result: string; detail: string }
export interface ProjectRow {
  id: string; name: string; group: string; kind: string; stack: string[]; path: string; source: string;
  map_status: string; map_refreshed: string | null; last_opened: string | null;
}
export interface MapRecord {
  project_id: string; status: string; last_refresh?: string | null; last_opened?: string | null;
  map_dir?: string; error?: string; task_id?: number; name?: string; path?: string; group?: string;
  stats: { nodes?: number; edges?: number; files?: number; languages?: string[]; size_bytes?: number;
    codecortex_version?: string; derived_stale?: boolean; error?: string };
}
export interface Overview {
  version: string; workspaces: string[]; projects: number; groups: number; by_kind: Record<string, number>;
  maps: { ready: number; refreshing: number; missing: number }; candidates: number; tasks_running: number;
  recently_opened: { path: string; last_opened: string; project: string | null; name: string }[];
  activity: Activity[];
}
