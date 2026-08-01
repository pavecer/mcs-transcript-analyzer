import { useState } from "react";
import { JsonTree } from "./JsonTree";
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
}

interface ActionEntry {
  name?: string;
  status?: string;
  start?: string;
  end?: string;
  code?: string;
  error?: unknown;
  inputs?: unknown;
  outputs?: unknown;
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

export function FlowRuns({ json, loading }: { json?: string; loading?: boolean }) {
  const items = (safeParse(json) as unknown as FlowCorrelation[] | undefined) ?? [];
  const [open, setOpen] = useState<Set<number>>(new Set());

  if (loading) return <div className="muted pad">Loading flow correlation…</div>;
  if (!items.length) return <div className="muted pad">No flow actions were invoked in this session.</div>;

  const toggle = (i: number) => {
    const next = new Set(open);
    if (next.has(i)) next.delete(i);
    else next.add(i);
    setOpen(next);
  };

  return (
    <div className="tools">
      <div className="muted small pad-sm">
        Flow runs are matched by time overlap — Power Automate does not stamp the conversation id on a run.
        <br />
        <span className="conf flow_action">action</span> = exact invoke trace (test mode only) ·{" "}
        <span className="conf plan_step">plan step</span> = orchestrator step window (production channels)
      </div>

      {items.map((fc, i) => {
        const runs = fc.runs ?? [];
        const isOpen = open.has(i);
        return (
          <div key={`${fc.action_id}-${i}`} className={`toolcall ${fc.exception ? "bad" : latencyBand(fc.span_ms)}`}>
            <div className="toolcall-head" onClick={() => toggle(i)}>
              <span className={`dur ${latencyBand(fc.span_ms)}`}>{fmtMs(fc.span_ms)}</span>
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
                      <th /><th>started</th><th>status</th><th>duration</th><th>offset</th><th>flow</th><th /></tr>
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
                          <td className="mono muted">{r.offset_ms !== undefined ? `+${Math.round(r.offset_ms)}ms` : "—"}</td>
                          <td className="mono muted" title={r.workflow_id}>{(r.workflow_id ?? "").slice(0, 8)}</td>
                          <td>{r.run_name && <RunDetailToggle runName={r.run_name} />}</td>
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
    </div>
  );
}

function RunDetailToggle({ runName }: { runName: string }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "missing" | "error">("idle");

  const load = async () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (detail || state === "loading") return;
    setState("loading");
    try {
      const res = await Pvci_flowrundetailsService.getAll({
        select: [
          "pvci_runname", "pvci_flowdisplayname", "pvci_status", "pvci_durationms",
          "pvci_actioncount", "pvci_failedactioncount", "pvci_skippedactioncount",
          "pvci_triggerjson", "pvci_actionsjson", "pvci_errorsummary", "pvci_payloadtruncated",
        ],
        filter: `pvci_runname eq '${runName}'`,
        top: 1,
      });
      const row = ((res.data ?? []) as unknown as RunDetail[])[0];
      if (!row) setState("missing");
      else {
        setDetail(row);
        setState("idle");
      }
    } catch {
      setState("error");
    }
  };

  return (
    <>
      <button className="link" onClick={() => void load()}>{open ? "hide detail" : "detail"}</button>
      {open && (
        <div className="rundetail">
          {state === "loading" && <div className="muted small">Loading run detail…</div>}
          {state === "error" && <div className="muted small">Could not load run detail.</div>}
          {state === "missing" && (
            <div className="muted small">
              Not fetched yet — run <code>fetch_flow_run_details.py</code> to pull inputs and outputs.
            </div>
          )}
          {detail && <RunDetailBody detail={detail} />}
        </div>
      )}
    </>
  );
}

function RunDetailBody({ detail }: { detail: RunDetail }) {
  const actions = (safeParse(detail.pvci_actionsjson) as unknown as ActionEntry[] | undefined) ?? [];
  const trigger = safeParse(detail.pvci_triggerjson);
  const [showSkipped, setShowSkipped] = useState(false);
  const [sel, setSel] = useState<number | null>(null);

  const visible = actions
    .map((a, i) => ({ a, i }))
    .filter(({ a }) => showSkipped || a.status !== "Skipped");

  return (
    <div>
      <div className="muted small pad-sm">
        {detail.pvci_flowdisplayname} · {detail.pvci_status} · {fmtMs(detail.pvci_durationms)} ·{" "}
        {detail.pvci_actioncount} actions ({detail.pvci_skippedactioncount} skipped
        {detail.pvci_failedactioncount ? `, ${detail.pvci_failedactioncount} failed` : ""})
        {detail.pvci_payloadtruncated && <span className="flag warn"> payload truncated</span>}
      </div>

      {detail.pvci_errorsummary && <div className="toolcall-error">{detail.pvci_errorsummary}</div>}

      <div className="timeline-bar">
        <button className={showSkipped ? "on" : ""} onClick={() => setShowSkipped(!showSkipped)}>
          Show skipped ({actions.filter((a) => a.status === "Skipped").length})
        </button>
        {trigger != null && (
          <button className={sel === -1 ? "on" : ""} onClick={() => setSel(sel === -1 ? null : -1)}>
            Trigger
          </button>
        )}
      </div>

      {sel === -1 && trigger != null && (
        <div className="inline-json"><JsonTree value={trigger as never} initialCollapseDepth={3} /></div>
      )}

      <div className="actionlist">
        {visible.map(({ a, i }) => {
          const ok = a.status === "Succeeded";
          const skipped = a.status === "Skipped";
          return (
            <div key={`${a.name}-${i}`} className={`actionrow ${skipped ? "skip" : ok ? "ok" : "fail"}`}>
              <div className="actionrow-head" onClick={() => setSel(sel === i ? null : i)}>
                <span className={`dot ${skipped ? "skip" : ok ? "ok" : "fail"}`} />
                <span className="aname">{a.name}</span>
                <span className="muted small">{a.status}</span>
                <span className="caret">{sel === i ? "▼" : "▶"}</span>
              </div>
              {sel === i && (
                <div className="io">
                  <div>
                    <h4>Inputs</h4>
                    {a.inputs === undefined || a.inputs === null
                      ? <div className="muted small">none</div>
                      : <div className="inline-json"><JsonTree value={a.inputs as never} initialCollapseDepth={2} /></div>}
                  </div>
                  <div>
                    <h4>Outputs</h4>
                    {a.outputs === undefined || a.outputs === null
                      ? <div className="muted small">none</div>
                      : <div className="inline-json"><JsonTree value={a.outputs as never} initialCollapseDepth={2} /></div>}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
