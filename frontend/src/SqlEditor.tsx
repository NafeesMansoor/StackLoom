// A textarea with SQL highlighting drawn underneath it (no editor library).
import { useRef } from "react";

const KEYWORDS = new Set(("select from where and or not insert into values update set delete create table drop alter add column " +
  "index primary key foreign references join left right inner outer full on as order by group having limit offset distinct " +
  "union all case when then else end null is in like between exists with returning begin commit rollback view show describe " +
  "explain pragma asc desc count sum avg min max default unique check constraint cascade truncate grant revoke").split(" "));

function highlight(sql: string) {
  const parts: JSX.Element[] = [];
  const re = /(--[^\n]*|\/\*[\s\S]*?\*\/)|('(?:[^']|'')*'?)|("(?:[^"]|"")*"?|`[^`]*`?)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)|(\s+|.)/g;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(sql))) {
    const [text] = m;
    const cls = m[1] ? "c" : m[2] ? "s" : m[3] ? "i" : m[4] ? "n" : m[5] && KEYWORDS.has(text.toLowerCase()) ? "k" : "";
    parts.push(cls ? <span key={i++} className={`sql-${cls}`}>{text}</span> : <span key={i++}>{text}</span>);
  }
  return parts;
}

export function SqlEditor({ value, onChange, onRun, id }: { value: string; onChange: (v: string) => void; onRun: () => void; id: string }) {
  const under = useRef<HTMLPreElement>(null);
  return (
    <div className="sql-editor">
      <pre ref={under} aria-hidden="true">{highlight(value)}{"\n"}</pre>
      <textarea id={id} spellCheck={false} value={value} onChange={(e) => onChange(e.target.value)}
        onScroll={(e) => { if (under.current) { under.current.scrollTop = e.currentTarget.scrollTop; under.current.scrollLeft = e.currentTarget.scrollLeft; } }}
        onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); onRun(); } }} />
    </div>
  );
}
