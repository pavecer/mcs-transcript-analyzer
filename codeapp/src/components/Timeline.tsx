import { useMemo, useState } from "react";
import { JsonTree } from "./JsonTree";
import { fmtClock, fmtMs, latencyBand, planSteps, safeParse, turnKind, type TurnRow } from "../lib/model";

interface Props {
  turns: TurnRow[];
  loading: boolean;
}

export function Timeline({ turns, loading }: Props) {
  const [showReasoning, setShowReasoning] = useState(true);
  const [showOther, setShowOther] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const visible = useMemo(
    () =>
      turns.filter((t) => {
        const kind = turnKind(t);
        if (kind === "message") return true;
        if (kind === "reasoning") return showReasoning;
        return showOther;
      }),
    [turns, showReasoning, showOther]
  );

  const counts = useMemo(() => {
    let message = 0;
    let reasoning = 0;
    let other = 0;
    turns.forEach((t) => {
      const k = turnKind(t);
      if (k === "message") message++;
      else if (k === "reasoning") reasoning++;
      else other++;
    });
    return { message, reasoning, other };
  }, [turns]);

  const toggle = (id: string) => {
    const next = new Set(expanded);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setExpanded(next);
  };

  if (loading) return <div className="muted pad">Loading activities…</div>;
  if (!turns.length) return <div className="muted pad">No activities stored for this session.</div>;

  return (
    <div className="timeline">
      <div className="timeline-bar">
        <button className={showReasoning ? "on" : ""} onClick={() => setShowReasoning(!showReasoning)}>
          Reasoning ({counts.reasoning})
        </button>
        <button className={showOther ? "on" : ""} onClick={() => setShowOther(!showOther)}>
          Other activities ({counts.other})
        </button>
        <span className="muted small">{counts.message} messages</span>
      </div>

      <div className="timeline-body">
        {visible.map((t) => {
          const kind = turnKind(t);
          const isUser = t.pvci_role === 1;
          const value = safeParse(t.pvci_valuejson);
          const isOpen = expanded.has(t.pvci_transcriptturnid);
          const steps = kind === "reasoning" ? planSteps(value) : [];

          if (kind === "message") {
            return (
              <div key={t.pvci_transcriptturnid} className={`bubble-row ${isUser ? "right" : "left"}`}>
                <div className={`bubble ${isUser ? "user" : "agent"}`}>
                  <div className="bubble-meta">
                    {isUser ? "User" : "Agent"} · {fmtClock(t.pvci_timestamputc)}
                    {t.pvci_latencyms !== undefined && t.pvci_latencyms !== null && (
                      <span className={`lat ${latencyBand(t.pvci_latencyms)}`}>{fmtMs(t.pvci_latencyms)}</span>
                    )}
                  </div>
                  <div className="bubble-text">{t.pvci_turntext}</div>
                  {value !== undefined && (
                    <button className="link" onClick={() => toggle(t.pvci_transcriptturnid)}>
                      {isOpen ? "hide payload" : "show payload"}
                    </button>
                  )}
                  {isOpen && value !== undefined && (
                    <div className="inline-json">
                      <JsonTree value={value} initialCollapseDepth={3} />
                    </div>
                  )}
                </div>
              </div>
            );
          }

          return (
            <div key={t.pvci_transcriptturnid} className={`event ${kind}`}>
              <div className="event-head" onClick={() => toggle(t.pvci_transcriptturnid)}>
                <span className="event-time">{fmtClock(t.pvci_timestamputc)}</span>
                <span className={`chip ${kind}`}>{t.pvci_eventname ?? t.pvci_activitytype}</span>
                {steps.length > 0 && <span className="steps">→ {steps.join(", ")}</span>}
                {value !== undefined && <span className="caret">{isOpen ? "▼" : "▶"}</span>}
              </div>
              {isOpen && value !== undefined && (
                <div className="inline-json">
                  <JsonTree value={value} initialCollapseDepth={4} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
