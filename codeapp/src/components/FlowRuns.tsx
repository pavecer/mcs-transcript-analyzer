import { useRef, useState } from "react";
import { JsonTree } from "./JsonTree";
import { ProcessMap, type FlowActionEntry } from "./ProcessMap";
import { Pvci_flowrundetailsService } from "../generated/services/Pvci_flowrundetailsService";
import { fmtMs, latencyBand, safeParse } from "../lib/model";

interface RunDetail {
  pvci_runname?: string;
  pvci_flowdisplayname?: string;
  pvci_status?: string;
  pvci_durationms?: number;
  pvci_actioncount?: number;
  pvci_failedactioncount?: number;
  pvci_skippedactioncount?: number;
  pvci_triggerjson?: string;
  pvci_actionsjson?: string;
  pvci_errorsummary?: string;
  pvci_payloadtruncated?: boolean;
  pvci_fetchedon?: string;
}

interface FlowRun {
  flow_run_id?: string;
  run_name?: string;
  workflow_id?: string;
  status?: string;
  started_utc?: string;
  ended_utc?: string;
  duration_ms?: number | null;
  error_code?: string | null;
  offset_ms?: number;
  rank?: number;
  best?: boolean;
}

interface FlowCorrelation {
  action_id?: string;
  topic?: string;
  source?: "flow_action" | "plan_step";
  thought?: string | null;
  started_utc?: string;
  span_ms?: number | null;
  exception?: string;
  confidence?: "none" | "high" | "multiple";
  runs?: FlowRun[];
}

function fmtStartDelta(ms?: number): string {
  if (ms === undefined) return "—";
  const sign = ms > 0 ? "+" : ms < 0 ? "−" : "";
  return `${sign}${fmtMs(Math.abs(Math.round(ms)))}`;
}

function escapeODataString(value: string): string {
  return value.replace(/'/g, "''");
}

export function FlowRuns({ json, loading }: { json?: string; loading?: boolean }) {
  const items = (safeParse(json) as unknown as FlowCorrelation[] | undefined) ?? [];
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailState, setDetailState] = useState<"idle" | "loading" | "missing" | "error">("idle");
  const workspaceRef = useRef<HTMLElement>(null);
  const detailRequestRef = useRef(0);

  if (loading) return <div className="muted pad">Loading flow correlation…</div>;
  if (!items.length) return <div className="muted pad">No flow actions were invoked in this session.</div>;

  const toggle = (i: number) => {
    const next = new Set(open);
    if (next.has(i)) next.delete(i);
    else next.add(i);
    setOpen(next);
  };

  const analyze = async (runName: string) => {
    const requestId = ++detailRequestRef.current;
    if (selectedRun === runName) {
      setSelectedRun(null);
      setDetail(null);
      setDetailState("idle");
      return;
    }
    setSelectedRun(runName);
    setDetail(null);
    setDetailState("loading");
    try {
      const res = await Pvci_flowrundetailsService.getAll({
        select: [
          "pvci_runname", "pvci_flowdisplayname", "pvci_status", "pvci_durationms",
          "pvci_actioncount", "pvci_failedactioncount", "pvci_skippedactioncount",
          "pvci_triggerjson", "pvci_actionsjson", "pvci_errorsummary", "pvci_payloadtruncated",
          "pvci_fetchedon",
        ],
        filter: `pvci_runname eq '${escapeODataString(runName)}'`,
        top: 1,
      });
      if (detailRequestRef.current !== requestId) return;
      const row = ((res.data ?? []) as unknown as RunDetail[])[0];
      if (!row || !row.pvci_fetchedon || !row.pvci_actionsjson) {
        setDetailState("missing");
      }
      else {
        setDetail(row);
        setDetailState("idle");
        requestAnimationFrame(() => {
          if (detailRequestRef.current === requestId) {
            workspaceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        });
      }
    } catch {
      if (detailRequestRef.current !== requestId) return;
      setDetailState("error");
    }
  };

  return (
    <div className="tools">
      <div className="muted small pad-sm">
        Flow runs are matched by time overlap — Power Automate does not stamp the conversation id on a run.
        <br />
        <span className="conf flow_action">action</span> = exact invoke trace (test mode only) ·{" "}
        <span className="conf plan_step">plan step</span> = orchestrator step window, not flow runtime (production channels)
      </div>

      <div className="timing-help" tabIndex={0} aria-label="Timing explanation">
        <span className="timing-help-trigger">Explain this timing</span>
        <div className="timing-help-card" role="note">
          <p><strong>step window</strong> is the orchestrator step span (start to finish of that plan step).</p>
          <p><strong>run time</strong> is the backend Power Automate run duration for one matched run.</p>
          <p><strong>start delta</strong> is run start minus step start (timing correlation, not queue telemetry).</p>
          <p>Values can overlap in time, so do not add them together as a total.</p>
        </div>
      </div>

      {items.map((fc, i) => {
        const runs = fc.runs ?? [];
        const isOpen = open.has(i);
        return (
          <div key={`${fc.action_id}-${i}`} className={`toolcall ${fc.exception ? "bad" : latencyBand(fc.span_ms)}`}>
            <div className="toolcall-head" onClick={() => toggle(i)}>
              <span
                className={`dur correlation-duration ${latencyBand(fc.span_ms)}`}
                title={fc.source === "plan_step"
                  ? "Elapsed time from DynamicPlanStepTriggered to DynamicPlanStepFinished. This overlaps backend flow execution and is not a sum of run durations."
                  : "Elapsed time between exact flow invocation trace events."}
              >
                <strong>{fmtMs(fc.span_ms)}</strong>
                <small>{fc.source === "plan_step" ? "step window" : "invoke span"}</small>
              </span>
              <span className="ttype">{fc.topic || fc.action_id}</span>
              <span className={`conf ${fc.source ?? "flow_action"}`}>
                {fc.source === "plan_step" ? "plan step" : "action"}
              </span>
              <span className={`conf ${fc.confidence}`}>{fc.confidence === "none" ? "no run matched" : fc.confidence}</span>
              <span className="ttopic">{(fc.started_utc ?? "").slice(11, 19)}</span>
              <span className="caret">{isOpen ? "▼" : "▶"}</span>
            </div>

            {fc.thought && <div className="thought">{fc.thought}</div>}

            {fc.exception && <div className="toolcall-error">{fc.exception}</div>}

            {isOpen && (
              runs.length ? (
                <table className="runtable">
                  <thead>
                    <tr>
                      <th /><th>started</th><th>status</th><th>run time</th>
                      <th title="Run start minus plan-step/invocation start. Correlation timing only; not measured queue or backend wait time.">start delta</th>
                      <th>flow</th><th /></tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => {
                      const ok = (r.status ?? "").toLowerCase() === "succeeded";
                      return (
                        <tr key={r.flow_run_id} className={r.best ? "best" : ""}>
                          <td>{r.best ? <span className="badge">best</span> : ""}</td>
                          <td className="mono">{(r.started_utc ?? "").replace("T", " ").replace("Z", "")}</td>
                          <td className={ok ? "ok" : "fail"}>{r.status}</td>
                          <td className="mono">{fmtMs(r.duration_ms)}</td>
                          <td
                            className="mono muted"
                            title="Run start minus plan-step/invocation start. This is correlation timing, not measured backend waiting time."
                          >
                            {fmtStartDelta(r.offset_ms)}
                          </td>
                          <td className="mono muted" title={r.workflow_id}>{(r.workflow_id ?? "").slice(0, 8)}</td>
                          <td>
                            {r.run_name && (
                              <button
                                className={`analyze-run${selectedRun === r.run_name ? " on" : ""}`}
                                onClick={() => void analyze(r.run_name!)}
                              >
                                {selectedRun === r.run_name ? "Close map" : "Analyze"}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <div className="muted small pad-sm">
                  No flow run found in the window. It may have aged out of Dataverse retention.
                </div>
              )
            )}
          </div>
        );
      })}

      {selectedRun && (
        <section className="flow-analysis-workspace" ref={workspaceRef}>
          {detailState === "loading" && <div className="muted pad">Loading execution map…</div>}
          {detailState === "error" && <div className="error">Could not load this flow run.</div>}
          {detailState === "missing" && (
            <div className="muted pad">
              Run detail is pending enrichment. The execution map will appear after action history is collected.
            </div>
          )}
          {detail && <RunDetailBody detail={detail} />}
        </section>
      )}
    </div>
  );
}

function RunDetailBody({ detail }: { detail: RunDetail }) {
  const actions = (safeParse(detail.pvci_actionsjson) as unknown as FlowActionEntry[] | undefined) ?? [];
  const trigger = safeParse(detail.pvci_triggerjson);
  const [showContext, setShowContext] = useState(false);

  return (
    <div>
      <div className="flow-run-overview">
        <div>
          <span className={`inspector-status ${(detail.pvci_status ?? "").toLowerCase() === "succeeded" ? "success" : "failed"}`}>
            {detail.pvci_status ?? "Unknown"}
          </span>
          <h3>{detail.pvci_flowdisplayname ?? "Flow execution"}</h3>
        </div>
        <dl>
          <div><dt>Duration</dt><dd>{fmtMs(detail.pvci_durationms)}</dd></div>
          <div><dt>Executed</dt><dd>{(detail.pvci_actioncount ?? 0) - (detail.pvci_skippedactioncount ?? 0)}</dd></div>
          <div><dt>Skipped</dt><dd>{detail.pvci_skippedactioncount ?? 0}</dd></div>
          <div><dt>Failed</dt><dd>{detail.pvci_failedactioncount ?? 0}</dd></div>
        </dl>
        {detail.pvci_payloadtruncated && <span className="flag warn">payload truncated</span>}
      </div>

      <div className="timeline-bar">
        {trigger != null && (
          <button className={showContext ? "on" : ""} onClick={() => setShowContext(!showContext)}>
            Run context
          </button>
        )}
      </div>

      {showContext && trigger != null && (
        <div className="inline-json"><JsonTree value={trigger as never} initialCollapseDepth={3} /></div>
      )}

      <ProcessMap actions={actions} />

      {detail.pvci_errorsummary && (
        <details className="technical-errors">
          <summary>Technical error summary</summary>
          <pre>{detail.pvci_errorsummary}</pre>
        </details>
      )}
    </div>
  );
}
