import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";

export interface Loaded<T> { data: T | null; error: string; loading: boolean; reload: () => void }

export function useText(path: string | null): Loaded<string> {
  const [data, setData] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setLoading(true);
    api.text(path).then((d) => { if (!cancelled) { setData(d); setError(""); setLoading(false); } })
      .catch((e: ApiError) => { if (!cancelled) { setError(e.message); setLoading(false); } });
    return () => { cancelled = true; };
  }, [path, tick]);
  return { data, error, loading, reload };
}

// Fetch once; poll only while `pollWhile(data)` is true (no idle polling).
export function useApi<T>(path: string | null, pollWhile?: (data: T) => boolean, intervalMs = 2000): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const pollRef = useRef(pollWhile);
  pollRef.current = pollWhile;
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    let timer: number | undefined;
    const load = () => {
      api.get<T>(path)
        .then((d) => {
          if (cancelled) return;
          setData(d); setError(""); setLoading(false);
          if (pollRef.current && pollRef.current(d)) timer = window.setTimeout(load, intervalMs);
        })
        .catch((e: ApiError) => {
          if (cancelled) return;
          if (e.status === 401) window.dispatchEvent(new Event("stackloom:signed-out"));
          setError(e.message); setLoading(false);
        });
    };
    load();
    return () => { cancelled = true; if (timer) window.clearTimeout(timer); };
  }, [path, tick, intervalMs]);

  return { data, error, loading, reload };
}
