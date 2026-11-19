import { type Activity as Row } from "../api";
import { when } from "../format";
import { useApi } from "../hooks";
import { Empty, ErrorNote, Loading, PageHead } from "../ui";

export function Activity() {
  const { data, error, loading, reload } = useApi<Row[]>("/api/activity");
  if (loading) return <Loading />;
  if (error || !data) return <ErrorNote message={error} onRetry={reload} />;
  return (
    <>
      <PageHead title="Recent activity" lede="Every administrative action, who did it and how it ended. Secrets are masked." />
      <div className="box table-scroll">
        {data.length === 0 ? <Empty>Nothing yet.</Empty> : (
          <table>
            <thead><tr><th scope="col">When</th><th scope="col">Who</th><th scope="col">Action</th><th scope="col">Target</th><th scope="col">Result</th></tr></thead>
            <tbody>{data.map((a) => (
              <tr key={a.id}>
                <td className="small" style={{ whiteSpace: "nowrap" }}>{when(a.at)}</td>
                <td>{a.actor}</td>
                <td className="mono">{a.action}</td>
                <td className="small">{a.target}{a.detail && <div className="muted">{a.detail}</div>}</td>
                <td style={{ color: a.result === "ok" ? "var(--ok)" : "var(--bad)" }}>{a.result}</td>
              </tr>))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
