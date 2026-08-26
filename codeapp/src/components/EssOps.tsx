import { fmtClock, fmtMs, safeParse, sourceEnvironmentLabel, type SessionRow, type TurnRow } from "../lib/model";
import { formatObservedMetric } from "../lib/telemetryAvailability";

interface TopicStep {
  id: string;
  topic: string;
  startedUtc?: string;
  durationMs?: number | null;
  thought?: string;
}

interface Gap {
  fromUtc: string;
  toUtc: string;
  ms: number;
}

interface ErrorEvent {
  id: string;
  at?: string;
  code?: string;
  message?: string;
  topic?: string;
  category: string;
}

export function EssOps({ session, turns, loading }: { session: SessionRow; turns: TurnRow[]; loading: boolean }) {
  if (loading) return <div className="muted pad">Loading ESS operations view…</div>;

  const topicSteps = deriveTopicSteps(turns, session.pvci_planeventsjson);
  const maxGap = largestGap(turns);
  const staleGaps = topStaleGaps(turns, 60_000, 4);
  const unansweredUserTurns = countUnansweredUserTurns(turns);
  const errorEvents = deriveErrorEvents(turns);

  const firstReplyMs = session.pvci_firstresponsems ?? firstReplyLatency(turns) ?? null;
  const sessionTopic = session.pvci_topicname ?? topicSteps[0]?.topic ?? "—";
  const firstTopicAt = topicSteps[0]?.startedUtc;

  const hints = buildHints(session, firstReplyMs, maxGap, unansweredUserTurns);

  return (
    <div className="ess-ops">
      <div className="muted small pad-sm">
        Conversation overview: what the user experienced, how the agent routed the request, and which observable systems participated.
      </div>

      <div className="ess-kpis">
        <Kpi label="Environment" value={sourceEnvironmentLabel(session)} hint={session.pvci_tenantid ? `tenant ${session.pvci_tenantid}` : undefined} />
        <Kpi label="Primary topic" value={sessionTopic} hint={firstTopicAt ? `first picked ${fmtClock(firstTopicAt)}` : undefined} />
        <Kpi label="First reply" value={fmtMs(firstReplyMs)} />
        <Kpi label="Largest retained-event gap" value={fmtMs(maxGap?.ms ?? null)} hint={maxGap ? `${fmtClock(maxGap.fromUtc)} → ${fmtClock(maxGap.toUtc)}` : undefined} />
        <Kpi label="Unanswered user turns" value={String(unansweredUserTurns)} hint={unansweredUserTurns > 0 ? "candidate stale handoff" : undefined} />
        <Kpi label="Topic steps" value={String(topicSteps.length)} />
        <Kpi
          label="Knowledge calls"
          value={formatObservedMetric(
            session.pvci_knowledgecallcount,
            { singular: "retrieval", plural: "retrievals" },
          )}
          hint={formatObservedMetric(
            session.pvci_knowledgesourcecount,
            { singular: "cited source", plural: "cited sources" },
          )}
        />
        <Kpi
          label="User errors"
          value={session.pvci_usererrorcount == null
            ? "Unavailable"
            : String(session.pvci_usererrorcount)}
          hint={session.pvci_errorcategory ?? undefined}
        />
      </div>

      <h3 className="sub">Failure timeline</h3>
      {!errorEvents.length ? (
        <div className="muted small pad-sm">No user-facing runtime failure trace was retained.</div>
      ) : (
        <table className="runtable ess-error-table">
          <thead>
            <tr>
              <th>at</th>
              <th>category</th>
              <th>topic</th>
              <th>error</th>
            </tr>
          </thead>
          <tbody>
            {errorEvents.map((error) => (
              <tr key={error.id}>
                <td className="mono">{fmtClock(error.at)}</td>
                <td><span className="conf risk-critical">{error.category}</span></td>
                <td className="mono">{error.topic ?? "—"}</td>
                <td>
                  <strong className="ess-error-code">{error.code ?? "UserError"}</strong>
                  <span className="ess-error-message">{error.message ?? "No error message was recorded."}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 className="sub">Routing timeline</h3>
      {!topicSteps.length ? (
        <div className="muted small pad-sm">
          No DynamicPlan step activity found. Check transcript retention and reasoning capture.
        </div>
      ) : (
        <table className="runtable ess-topic-table">
          <thead>
            <tr>
              <th>at</th>
              <th>topic</th>
              <th>step time</th>
              <th>thought</th>
            </tr>
          </thead>
          <tbody>
            {topicSteps.map((step) => (
              <tr key={step.id}>
                <td className="mono">{step.startedUtc ? fmtClock(step.startedUtc) : "—"}</td>
                <td className="mono">{step.topic}</td>
                <td className="mono">{fmtMs(step.durationMs)}</td>
                <td className="muted">{step.thought ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 className="sub">Retained-event gaps</h3>
      {!staleGaps.length ? (
        <div className="muted small pad-sm">No gap over 60 seconds exists between retained transcript events.</div>
      ) : (
        <table className="runtable ess-stale-table">
          <thead>
            <tr>
              <th>from</th>
              <th>to</th>
              <th>silence</th>
            </tr>
          </thead>
          <tbody>
            {staleGaps.map((gap, idx) => (
              <tr key={`${gap.fromUtc}-${gap.toUtc}-${idx}`}>
                <td className="mono">{fmtClock(gap.fromUtc)}</td>
                <td className="mono">{fmtClock(gap.toUtc)}</td>
                <td className="mono">{fmtMs(gap.ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 className="sub">Where to look when it breaks</h3>
      <div className="ess-hints">
        {hints.map((hint) => (
          <div key={hint.title} className={`ess-hint ${hint.band}`}>
            <strong>{hint.title}</strong>
            <span>{hint.detail}</span>
            <small>{hint.where}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  );
}

function firstReplyLatency(turns: TurnRow[]): number | null {
  const ordered = [...turns]
    .filter((t) => t.pvci_timestamputc)
    .sort((a, b) => Date.parse(a.pvci_timestamputc!) - Date.parse(b.pvci_timestamputc!));

  const firstUser = ordered.find((t) => t.pvci_activitytype === "message" && t.pvci_role === 1);
  if (!firstUser?.pvci_timestamputc) return null;
  const userTs = Date.parse(firstUser.pvci_timestamputc);
  if (Number.isNaN(userTs)) return null;

  const firstAgent = ordered.find((t) =>
    t.pvci_activitytype === "message" &&
    t.pvci_role !== 1 &&
    t.pvci_timestamputc &&
    Date.parse(t.pvci_timestamputc) >= userTs
  );
  if (!firstAgent?.pvci_timestamputc) return null;

  const agentTs = Date.parse(firstAgent.pvci_timestamputc);
  return Number.isNaN(agentTs) ? null : agentTs - userTs;
}

function deriveErrorEvents(turns: TurnRow[]): ErrorEvent[] {
  const ordered = [...turns].sort((left, right) => (left.pvci_turnindex ?? 0) - (right.pvci_turnindex ?? 0));
  const errors: ErrorEvent[] = [];
  let currentTopic: string | undefined;

  for (const turn of ordered) {
    const payload = safeParse(turn.pvci_valuejson) as Record<string, unknown> | undefined;
    if (turn.pvci_eventname === "DynamicPlanStepTriggered") {
      const topicId = typeof payload?.taskDialogId === "string" ? payload.taskDialogId : undefined;
      currentTopic = topicId ? topicId.split(".").pop() ?? topicId : currentTopic;
      continue;
    }
    if (turn.pvci_eventname !== "ErrorTraceData" || payload?.isUserError !== true) continue;

    const code = typeof payload.errorCode === "string" ? payload.errorCode : undefined;
    const message = typeof payload.errorMessage === "string" ? payload.errorMessage : undefined;
    errors.push({
      id: turn.pvci_transcriptturnid,
      at: turn.pvci_timestamputc,
      code,
      message,
      topic: currentTopic,
      category: classifyError(code, message),
    });
  }
  return errors;
}

function classifyError(code?: string, message?: string): string {
  const text = `${code ?? ""} ${message ?? ""}`.toLowerCase();
  if (["authentication", "unauthorized", "forbidden", "consent"].some((token) => text.includes(token))) return "Authentication";
  if (["connector", "connection", "reference id"].some((token) => text.includes(token))) return "Connector";
  if (["expression", "contentvalidation"].some((token) => text.includes(token))) return "Topic expression";
  return "Topic runtime";
}

function deriveTopicSteps(turns: TurnRow[], planEventsJson?: string): TopicStep[] {
  const steps = new Map<string, TopicStep & { startMs?: number; endMs?: number }>();

  for (const turn of turns) {
    const name = turn.pvci_eventname ?? "";
    if (!name.startsWith("DynamicPlanStep")) continue;
    const payload = safeParse(turn.pvci_valuejson) as Record<string, unknown> | undefined;
    const stepId = typeof payload?.stepId === "string" ? payload.stepId : turn.pvci_transcriptturnid;
    const rec = steps.get(stepId) ?? {
      id: stepId,
      topic: "?",
      thought: undefined,
      startMs: undefined,
      endMs: undefined,
      startedUtc: undefined,
      durationMs: undefined,
    };

    if (name === "DynamicPlanStepTriggered") {
      const topicRaw = typeof payload?.taskDialogId === "string" ? payload.taskDialogId : undefined;
      rec.topic = topicRaw ? topicRaw.split(".").pop() ?? topicRaw : rec.topic;
      rec.thought = typeof payload?.thought === "string" ? payload.thought : rec.thought;
      if (turn.pvci_timestamputc) {
        const ms = Date.parse(turn.pvci_timestamputc);
        if (!Number.isNaN(ms)) {
          rec.startMs = ms;
          rec.startedUtc = turn.pvci_timestamputc;
        }
      }
    }

    if (name === "DynamicPlanStepFinished" && turn.pvci_timestamputc) {
      const ms = Date.parse(turn.pvci_timestamputc);
      if (!Number.isNaN(ms)) rec.endMs = ms;
    }

    steps.set(stepId, rec);
  }

  if (!steps.size && planEventsJson) {
    const events = safeParse(planEventsJson) as Array<Record<string, unknown>> | undefined;
    if (Array.isArray(events)) {
      for (const ev of events) {
        const name = typeof ev?.name === "string" ? ev.name : "";
        if (!name.startsWith("DynamicPlanStep")) continue;
        const value = (ev?.value ?? {}) as Record<string, unknown>;
        const stepId = typeof value.stepId === "string" ? value.stepId : `${steps.size + 1}`;
        const rec = steps.get(stepId) ?? {
          id: stepId,
          topic: "?",
          thought: undefined,
          startMs: undefined,
          endMs: undefined,
          startedUtc: undefined,
          durationMs: undefined,
        };
        if (name === "DynamicPlanStepTriggered") {
          const topicRaw = typeof value.taskDialogId === "string" ? value.taskDialogId : undefined;
          rec.topic = topicRaw ? topicRaw.split(".").pop() ?? topicRaw : rec.topic;
          rec.thought = typeof value.thought === "string" ? value.thought : rec.thought;
          if (typeof ev.at === "string") {
            rec.startedUtc = ev.at;
            const ms = Date.parse(ev.at);
            if (!Number.isNaN(ms)) rec.startMs = ms;
          }
        }
        if (name === "DynamicPlanStepFinished" && typeof ev.at === "string") {
          const ms = Date.parse(ev.at);
          if (!Number.isNaN(ms)) rec.endMs = ms;
        }
        steps.set(stepId, rec);
      }
    }
  }

  return [...steps.values()]
    .map((step) => ({
      id: step.id,
      topic: step.topic,
      startedUtc: step.startedUtc,
      durationMs: typeof step.startMs === "number" && typeof step.endMs === "number" ? step.endMs - step.startMs : null,
      thought: step.thought,
    }))
    .sort((left, right) => (Date.parse(left.startedUtc ?? "") || 0) - (Date.parse(right.startedUtc ?? "") || 0));
}

function largestGap(turns: TurnRow[]): Gap | null {
  const stamps = orderedStamps(turns);
  if (stamps.length < 2) return null;
  let best: Gap | null = null;
  for (let i = 1; i < stamps.length; i++) {
    const prev = stamps[i - 1];
    const cur = stamps[i];
    const ms = cur.ms - prev.ms;
    if (!best || ms > best.ms) {
      best = { fromUtc: prev.iso, toUtc: cur.iso, ms };
    }
  }
  return best;
}

function topStaleGaps(turns: TurnRow[], thresholdMs: number, topN: number): Gap[] {
  const stamps = orderedStamps(turns);
  const gaps: Gap[] = [];
  for (let i = 1; i < stamps.length; i++) {
    const prev = stamps[i - 1];
    const cur = stamps[i];
    const ms = cur.ms - prev.ms;
    if (ms >= thresholdMs) gaps.push({ fromUtc: prev.iso, toUtc: cur.iso, ms });
  }
  return gaps.sort((a, b) => b.ms - a.ms).slice(0, topN);
}

function orderedStamps(turns: TurnRow[]): Array<{ iso: string; ms: number }> {
  return turns
    .map((turn) => turn.pvci_timestamputc)
    .filter((iso): iso is string => Boolean(iso))
    .map((iso) => ({ iso, ms: Date.parse(iso) }))
    .filter((entry) => !Number.isNaN(entry.ms))
    .sort((a, b) => a.ms - b.ms);
}

function countUnansweredUserTurns(turns: TurnRow[]): number {
  const msgs = turns
    .filter((turn) => turn.pvci_activitytype === "message" && turn.pvci_timestamputc)
    .sort((a, b) => Date.parse(a.pvci_timestamputc!) - Date.parse(b.pvci_timestamputc!));

  let unanswered = 0;
  for (let i = 0; i < msgs.length; i++) {
    const current = msgs[i];
    if (current.pvci_role !== 1) continue;
    let answered = false;
    for (let j = i + 1; j < msgs.length; j++) {
      if (msgs[j].pvci_role === 1) break;
      answered = true;
      break;
    }
    if (!answered) unanswered += 1;
  }
  return unanswered;
}

function buildHints(session: SessionRow, firstReplyMs: number | null, maxGap: Gap | null, unansweredUserTurns: number) {
  const hints: Array<{ title: string; detail: string; where: string; band: "good" | "warn" | "bad" }> = [];

  if ((session.pvci_usererrorcount ?? 0) > 0) {
    hints.push({
      title: session.pvci_errorcategory ?? "Topic runtime failure",
      detail: `${session.pvci_usererrorcount} user-facing error(s). ${session.pvci_primaryerrorcode ?? "No error code recorded"}.`,
      where: `Inspect Failure timeline at ${session.pvci_primaryerrortopic ?? "the active topic"}. ${session.pvci_primaryerrormessage ?? ""}`.trim(),
      band: "bad",
    });
  }

  if ((session.pvci_knowledgefailurecount ?? 0) > 0) {
    hints.push({
      title: "Knowledge retrieval failure",
      detail: `${session.pvci_knowledgefailurecount} knowledge retrieval(s) reported failed sources or incomplete execution.`,
      where: "Open Knowledge and inspect completion state plus failed source types.",
      band: "bad",
    });
  }

  if ((session.pvci_toolerrorcount ?? 0) > 0) {
    hints.push({
      title: "Tool or connector failure",
      detail: `${session.pvci_toolerrorcount} tool call(s) failed in this session.`,
      where: "Open Tool Calls and inspect exception details. Then inspect the nearest DynamicPlan step in Replay.",
      band: "bad",
    });
  }

  if ((session.pvci_flowrunfailurecount ?? 0) > 0) {
    hints.push({
      title: "Flow execution failure",
      detail: `${session.pvci_flowrunfailurecount} matched flow run(s) failed.`,
      where: "Open Flow Runs, analyze the failed run map, and inspect root-failure node plus technical summary.",
      band: "bad",
    });
  }

  if (firstReplyMs !== null && firstReplyMs >= 10_000) {
    hints.push({
      title: "Slow first response",
      detail: `First user message waited ${fmtMs(firstReplyMs)} for first agent reply.`,
      where: "Check Replay around the first message, then compare with Tool Calls and Flow Runs for cold-start/tool delays.",
      band: "warn",
    });
  }

  if ((maxGap?.ms ?? 0) >= 60_000 || unansweredUserTurns > 0) {
    hints.push({
      title: "Conversation may have gone stale",
      detail: `${unansweredUserTurns} unanswered user turn(s); max silence ${fmtMs(maxGap?.ms ?? null)}.`,
      where: "Check Topic pick timeline and stale segments above, then inspect DynamicPlan step transitions for missing completion.",
      band: "warn",
    });
  }

  if (!hints.length) {
    hints.push({
      title: "No critical signals detected",
      detail: "No failed tools/flows and no significant inactivity gaps in this session.",
      where: "Use Replay for semantic quality checks (wrong answer, wrong topic, or content quality issues).",
      band: "good",
    });
  }

  return hints;
}
