// STACKLOOM mark (source: scripts/brand.py). Three staggered layers woven by two threads;
// each thread breaks where it passes under a layer.
const BARS = "M10 10H26M6 16H26M6 22H22";
const THREADS = "M12.5 6V13.4M12.5 18.6V26M19.5 6V7.4M19.5 12.6V19.4M19.5 24.6V26";

export function Mark({ size = 22, tile = true }: { size?: number; tile?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      {tile && <rect width="32" height="32" rx="7" fill="var(--highlight-fill)" />}
      <g fill="none" strokeLinecap="round">
        <path d={BARS} stroke={tile ? "#f5f2ec" : "currentColor"} strokeWidth="3.4" />
        <path d={THREADS} stroke={tile ? "#9db8e8" : "var(--highlight)"} strokeWidth="2.8" />
      </g>
    </svg>
  );
}
