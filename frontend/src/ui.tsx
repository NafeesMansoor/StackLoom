import type { ReactNode } from "react";

export function Pill({ label, tone }: { label: string; tone?: string }) {
  return <span className={`pill ${tone ?? ""}`}>{label}</span>;
}

export function Loading({ what = "Loading…" }: { what?: string }) {
  return <div className="loading" role="status">{what}</div>;
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="notice notice-error" role="alert">
      <strong>Error:</strong> {message}{" "}
      {onRetry && <button className="btn btn-sm" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function PageHead({ title, lede, children }: { title: string; lede?: ReactNode; children?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {lede && <p>{lede}</p>}
      </div>
      {children && <div className="actions">{children}</div>}
    </div>
  );
}
