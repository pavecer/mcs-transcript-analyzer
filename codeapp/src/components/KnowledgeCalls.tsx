import { fmtMs, safeParse, type KnowledgeCall } from "../lib/model";

export function KnowledgeCalls({ json, loading }: { json?: string; loading?: boolean }) {
  const calls = (safeParse(json) as unknown as KnowledgeCall[] | undefined) ?? [];

  if (loading) return <div className="muted pad">Loading knowledge retrievals…</div>;
  if (!calls.length) return <div className="muted pad">No knowledge retrieval trace was recorded for this session.</div>;

  return (
    <div className="knowledge-calls">
      <div className="muted small pad-sm">
        {calls.length} retrieval{calls.length === 1 ? "" : "s"} · {calls.reduce((total, call) => total + call.cited_sources.length, 0)} source identifiers referenced
      </div>
      {calls.map((call, index) => (
        <section key={`${call.step_id ?? "knowledge"}-${index}`} className={`knowledge-call ${call.failed ? "failed" : "completed"}`}>
          <div className="knowledge-call-head">
            <span className={`conf ${call.failed ? "risk-critical" : "high"}`}>{call.completion_state ?? (call.failed ? "Failed" : "Completed")}</span>
            <strong>{knowledgeTaskLabel(call.task)}</strong>
            <span className="mono muted" title="Elapsed time from the search plan-step trigger to its KnowledgeTraceData outcome.">Knowledge step elapsed: {fmtMs(call.duration_ms)}</span>
          </div>
          <div className="knowledge-call-meta">
            <span>Search executed: {call.searched ? "Yes" : "No"}</span>
            <span>Source identifiers referenced: {call.cited_sources.length}</span>
          </div>
          {call.cited_sources.length > 0 && (
            <div className="knowledge-source-list">
              {call.cited_sources.map((source) => <span key={source} className="knowledge-source">{knowledgeSourceLabel(source)}</span>)}
            </div>
          )}
          {call.failed_source_types.length > 0 && (
            <div className="toolcall-error">Failed source types: {call.failed_source_types.join(", ")}</div>
          )}
        </section>
      ))}
    </div>
  );
}

function knowledgeTaskLabel(task?: string): string {
  if (!task) return "Knowledge search";
  return task.replace(/^P:/, "").replace(/([a-z])([A-Z])/g, "$1 $2");
}

function knowledgeSourceLabel(source: string): string {
  const label = source.split(".").pop() ?? source;
  return label.replace(/_[A-Za-z0-9]+$/, "").replace(/([a-z])([A-Z])/g, "$1 $2");
}
