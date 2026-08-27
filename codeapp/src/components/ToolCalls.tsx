import { JsonTree } from "./JsonTree";
import { fmtMs, latencyBand, safeParse, type ToolCall } from "../lib/model";
import { formatPlannedToolLabel, getPlannedToolSteps, type PlanEvent, type ReasoningStep } from "../lib/reasoning";
import { useState } from "react";

export function ToolCalls({ json, loading, exactTelemetryAvailable = true, planEventsJson }: { json?: string; loading?: boolean; exactTelemetryAvailable?: boolean; planEventsJson?: string }) {
  const calls = (safeParse(json) as unknown as ToolCall[] | undefined) ?? [];
  const planEvents = (safeParse(planEventsJson) as unknown as PlanEvent[] | undefined) ?? [];
  const plannedToolSteps = getPlannedToolSteps(planEvents);
  const [open, setOpen] = useState<Set<number>>(new Set());

  if (loading) return <div className="muted pad">Loading tool calls…</div>;
  if (!calls.length) {
    if (plannedToolSteps.length) {
      return <PlannedToolEvidence steps={plannedToolSteps} exactTelemetryAvailable={exactTelemetryAvailable} />;
    }
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
        const incomplete = c.completion_observed === false;
        const band = c.failed ? "bad" : incomplete ? "warn" : latencyBand(c.duration_ms);
        const isOpen = open.has(i);
        const hasOutput = c.output !== undefined && c.output !== null && JSON.stringify(c.output) !== "{}";
        return (
          <div key={`${c.action_id}-${i}`} className={`toolcall ${band}`}>
            <div className="toolcall-head" onClick={() => toggle(i)}>
              <span className={`dur ${band}`}>{fmtMs(c.duration_ms)}</span>
              <span className="ttype">{c.action_type}</span>
              <span className="ttopic">{c.topic}</span>
              {c.failed && <span className="flag warn">failed</span>}
              {incomplete && <span className="conf multiple">completion not observed</span>}
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

function PlannedToolEvidence({ steps, exactTelemetryAvailable }: { steps: ReasoningStep[]; exactTelemetryAvailable: boolean }) {
  const invocationState = exactTelemetryAvailable ? "0 exact invocations" : "Exact invocation telemetry unavailable";

  return (
    <div className="tools planned-tools">
      <section className="planned-tool-assessment">
        <div>
          <strong>{invocationState} · {steps.length} planned MCP/tool step{steps.length === 1 ? "" : "s"}</strong>
          <span className="flag warn">execution not evidenced</span>
        </div>
        <p>The planner selected {steps.length === 1 ? "this step" : "these steps"}, but no exact DialogTracing invocation record was retained. Whether the external tool ran, succeeded, or returned output is unknown.</p>
      </section>

      <div className="muted small pad-sm">Planned MCP/tool steps · not invocation traces</div>
      {steps.map((step, index) => (
        <article className="toolcall warn planned-tool" key={`${step.id}-${index}`}>
          <div className="toolcall-head planned-tool-head">
            <span className="reasoning-kind tool">MCP / tool</span>
            <strong>{formatPlannedToolLabel(step.task)}</strong>
            <span className="conf multiple">execution not evidenced</span>
          </div>
          <div className="reasoning-step-grid">
            <div><span>Selected at</span><strong>{step.startedAt ?? "—"}</strong></div>
            <div><span>Planner step state</span><strong>{step.state ?? "not retained"}</strong></div>
            <div><span>Planner step elapsed</span><strong>{fmtMs(step.executionMs)}</strong></div>
            <div><span>Inputs prepared</span><strong>{step.argumentNames.length}</strong></div>
          </div>
          {step.rationale && <div className="reasoning-rationale"><span>Recorded routing rationale</span>{step.rationale}</div>}
          {step.argumentNames.length > 0 && (
            <div className="reasoning-tags">
              <span>Prepared input names</span>
              {step.argumentNames.map((name) => <code key={name}>{name}</code>)}
            </div>
          )}
          <div className="planned-tool-note">Planner state and elapsed time describe orchestration only; they do not prove tool execution or latency.</div>
        </article>
      ))}
    </div>
  );
}
