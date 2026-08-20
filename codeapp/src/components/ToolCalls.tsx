import { JsonTree } from "./JsonTree";
import { fmtMs, latencyBand, safeParse, type ToolCall } from "../lib/model";
import { useState } from "react";

export function ToolCalls({ json, loading, exactTelemetryAvailable = true }: { json?: string; loading?: boolean; exactTelemetryAvailable?: boolean }) {
  const calls = (safeParse(json) as unknown as ToolCall[] | undefined) ?? [];
  const [open, setOpen] = useState<Set<number>>(new Set());

  if (loading) return <div className="muted pad">Loading tool calls…</div>;
  if (!calls.length) {
    return exactTelemetryAvailable
      ? <div className="muted pad">No exact tool or connector invocation was observed in this test transcript.</div>
      : <div className="muted pad">Exact tool telemetry is unavailable in this production transcript. This does not prove that no tool was used.</div>;
  }

  const toggle = (i: number) => {
    const next = new Set(open);
    if (next.has(i)) next.delete(i);
    else next.add(i);
    setOpen(next);
  };

  const total = calls.reduce((a, c) => a + (c.duration_ms ?? 0), 0);
  const failed = calls.filter((c) => c.failed).length;

  return (
    <div className="tools">
      <div className="muted small pad-sm">
        {calls.length} calls · {fmtMs(total)} total{failed > 0 && <span className="fail-note"> · {failed} failed</span>}
      </div>

      {calls.map((c, i) => {
        const band = c.failed ? "bad" : latencyBand(c.duration_ms);
        const isOpen = open.has(i);
        const hasOutput = c.output !== undefined && c.output !== null && JSON.stringify(c.output) !== "{}";
        return (
          <div key={`${c.action_id}-${i}`} className={`toolcall ${band}`}>
            <div className="toolcall-head" onClick={() => toggle(i)}>
              <span className={`dur ${band}`}>{fmtMs(c.duration_ms)}</span>
              <span className="ttype">{c.action_type}</span>
              <span className="ttopic">{c.topic}</span>
              {c.failed && <span className="flag warn">failed</span>}
              <span className="caret">{isOpen ? "▼" : "▶"}</span>
            </div>
            {c.exception && <div className="toolcall-error">{c.exception}</div>}
            {isOpen && (
              <div className="inline-json">
                {hasOutput ? (
                  <JsonTree value={c.output as never} initialCollapseDepth={2} />
                ) : (
                  <div className="muted small">No output recorded.</div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
