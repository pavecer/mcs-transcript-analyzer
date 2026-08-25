import { useMemo, useState } from "react";
import { ComboChart, HBar, type Bucket } from "./Chart";
import { fmtMs, isEssSession, latencyBand, sourceEnvironmentKey, sourceEnvironmentLabel, type SessionRow } from "../lib/model";

type Grain = "hour" | "day";
interface AgentOption { id: string; name: string }

export function Trends({ sessions, loading }: { sessions: SessionRow[]; loading: boolean }) {
  const [agent, setAgent] = useState<string>("*");
  const [hideTest, setHideTest] = useState(true);
  const [essOnly, setEssOnly] = useState(true);
  const [environment, setEnvironment] = useState("*");
  const [grain, setGrain] = useState<Grain | "auto">("auto");

  const environmentOptions = useMemo(() => {
    const options = new Map<string, string>();
    sessions.forEach((session) => {
      if (essOnly && !isEssSession(session)) return;
      options.set(sourceEnvironmentKey(session), sourceEnvironmentLabel(session));
    });
    return [...options.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [sessions, essOnly]);

  const agents = useMemo(
    () => {
      const options = new Map<string, AgentOption>();
      sessions.forEach((session) => {
        if (essOnly && !isEssSession(session)) return;
        if (environment !== "*" && sourceEnvironmentKey(session) !== environment) return;
        if (hideTest && session.pvci_istestmode) return;
        const id = session.pvci_botid ?? session.pvci_botname;
        if (!id) return;
        options.set(id, { id, name: session.pvci_botname ?? "Unnamed agent" });
      });
      return [...options.values()].sort((left, right) => left.name.localeCompare(right.name));
    },
    [sessions, environment, essOnly, hideTest]
  );

  const activeAgent = agent === "*" || agents.some((option) => option.id === agent) ? agent : "*";

  const scoped = useMemo(
    () =>
      sessions.filter((s) => {
        if (hideTest && s.pvci_istestmode) return false;
        if (essOnly && !isEssSession(s)) return false;
        if (activeAgent !== "*" && (s.pvci_botid ?? s.pvci_botname) !== activeAgent) return false;

        if (environment !== "*") {
          if (sourceEnvironmentKey(s) !== environment) return false;
        }
        return Boolean(s.pvci_startdatetimeutc);
      }),
    [sessions, activeAgent, hideTest, essOnly, environment]
  );

  const effectiveGrain: Grain = useMemo(() => {
    if (grain !== "auto") return grain;
    const times = scoped.map((s) => Date.parse(s.pvci_startdatetimeutc!)).filter((n) => !Number.isNaN(n));
    if (times.length < 2) return "hour";
    const spanDays = (Math.max(...times) - Math.min(...times)) / 86_400_000;
    return spanDays > 3 ? "day" : "hour";
  }, [scoped, grain]);

  const buckets: Bucket[] = useMemo(() => {
    const map = new Map<string, SessionRow[]>();
    for (const s of scoped) {
      const iso = s.pvci_startdatetimeutc!;
      const key = effectiveGrain === "day" ? iso.slice(0, 10) : `${iso.slice(0, 13)}:00`;
      const list = map.get(key) ?? [];
      list.push(s);
      map.set(key, list);
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, rows]) => {
        // Abandoned sessions have no reply; excluding them keeps latency honest.
        const lat = rows
          .map((r) => r.pvci_maxresponsems)
          .filter((v): v is number => typeof v === "number")
          .sort((a, b) => a - b);
        return {
          label: effectiveGrain === "day" ? key.slice(5) : key.slice(11),
          count: rows.length,
          p50: pct(lat, 0.5),
          p95: pct(lat, 0.95),
          failures: rows.filter((r) => (r.pvci_toolerrorcount ?? 0) > 0).length,
        };
      });
  }, [scoped, effectiveGrain]);

  const kpi = useMemo(() => {
    const lat = scoped
      .map((s) => s.pvci_maxresponsems)
      .filter((v): v is number => typeof v === "number")
      .sort((a, b) => a - b);
    const answered = lat.length;
    const toolCalls = scoped.reduce((a, s) => a + (s.pvci_toolcallcount ?? 0), 0);
    const toolErrors = scoped.reduce((a, s) => a + (s.pvci_toolerrorcount ?? 0), 0);
    const resolved = scoped.filter((s) => s.pvci_sessionoutcome === "Resolved").length;
    const knownOutcomes = scoped.filter((s) => Boolean(s.pvci_sessionoutcome) && s.pvci_sessionoutcome !== "None").length;
    return {
      sessions: scoped.length,
      answered,
      unanswered: scoped.length - answered,
      p50: pct(lat, 0.5),
      p95: pct(lat, 0.95),
      worst: lat.length ? lat[lat.length - 1] : null,
      toolCalls,
      toolErrors,
      knownOutcomes,
      unknownOutcomes: scoped.length - knownOutcomes,
      resolvedPct: knownOutcomes ? Math.round((resolved / knownOutcomes) * 100) : 0,
    };
  }, [scoped]);

  const byChannel = useMemo(() => group(scoped, (s) => s.pvci_channel ?? "unknown"), [scoped]);
  const byOutcome = useMemo(() => group(scoped, (s) => s.pvci_sessionoutcome ?? "None"), [scoped]);

  const slowest = useMemo(
    () =>
      [...scoped]
        .filter((s) => typeof s.pvci_maxresponsems === "number")
        .sort((a, b) => (b.pvci_maxresponsems ?? 0) - (a.pvci_maxresponsems ?? 0))
        .slice(0, 6),
    [scoped]
  );

  const sampleRange = useMemo(() => {
    const stamps = scoped
      .map((session) => session.pvci_startdatetimeutc)
      .filter((value): value is string => Boolean(value))
      .sort();
    return stamps.length ? `${stamps[0].slice(0, 10)} to ${stamps[stamps.length - 1].slice(0, 10)} UTC` : "no dated sessions";
  }, [scoped]);

  if (loading) return <div className="muted pad">Loading…</div>;

  return (
    <div className="trends">
      <div className="trend-intro">
        <div>
          <h2>Conversation trends</h2>
          <p>Compare recent conversation outcomes and response latency across an environment or agent.</p>
        </div>
      </div>

      <div className="trend-filterbar" aria-label="Trend filters">
        <label className="trend-filter">
          <span>Environment</span>
          <select
            value={environment}
            onChange={(event) => { setEnvironment(event.target.value); setAgent("*"); }}
          >
            <option value="*">All environments ({environmentOptions.length})</option>
            {environmentOptions.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        <label className="trend-filter">
          <span>Agent</span>
          <select value={activeAgent} onChange={(event) => setAgent(event.target.value)}>
            <option value="*">All matching agents ({agents.length})</option>
            {agents.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}
          </select>
        </label>
        <div className="trend-filter trend-scope">
          <span>Scope</span>
          <div className="segmented">
            <button
              className={essOnly ? "on" : ""}
              onClick={() => { setEssOnly(!essOnly); setEnvironment("*"); setAgent("*"); }}
              title="Name-based Employee Self-Service agent preset"
            >ESS agents</button>
            <button className={hideTest ? "on" : ""} onClick={() => { setHideTest(!hideTest); setAgent("*"); }}>
              Exclude test chats
            </button>
          </div>
        </div>
        <div className="trend-filter trend-grain">
          <span>Time grain</span>
          <div className="segmented">
            {(["auto", "hour", "day"] as const).map((option) => (
              <button key={option} className={grain === option ? "on" : ""} onClick={() => setGrain(option)}>{option}</button>
            ))}
          </div>
          <small>Showing {effectiveGrain}</small>
        </div>
      </div>

      <div className="muted small pad-sm">
        Recent diagnostic sample loaded by the app: {scoped.length} sessions · {sampleRange}. This is not a complete operational population.
      </div>

      <div className="kpis">
        <Kpi label="Sessions" value={String(kpi.sessions)} />
        <Kpi label="Reply latency available" value={`${kpi.answered} / ${kpi.sessions}`}
             hint={kpi.unanswered ? `${kpi.unanswered} without a stored latency value` : undefined} />
        <Kpi label="p50 slowest reply" value={fmtMs(kpi.p50)} band={latencyBand(kpi.p50)} />
        <Kpi label="p95 slowest reply" value={fmtMs(kpi.p95)} band={latencyBand(kpi.p95)} />
        <Kpi label="Worst reply" value={fmtMs(kpi.worst)} band={latencyBand(kpi.worst)} />
           <Kpi label="Exact tool traces" value={String(kpi.toolCalls)}
             hint={kpi.toolErrors ? `${kpi.toolErrors} failed · captured traces only` : "Captured test traces only"}
             band={kpi.toolErrors ? "bad" : "none"} />
           <Kpi label="Resolved · known outcomes" value={`${kpi.resolvedPct}%`}
             hint={kpi.unknownOutcomes ? `${kpi.unknownOutcomes} unknown outcome(s) excluded` : undefined} />
      </div>

      <h3 className="sub">Sessions and latency over time</h3>
      <div className="muted small pad-sm">
        Bars = session count · line = p95 of the slowest reply per session · red bars contain tool failures
      </div>
      <ComboChart buckets={buckets} />

      <div className="split">
        <div>
          <h3 className="sub">By channel</h3>
          <HBar rows={byChannel} />
        </div>
        <div>
          <h3 className="sub">By outcome</h3>
          <HBar rows={byOutcome} />
        </div>
      </div>

      <h3 className="sub">Slowest sessions</h3>
      <HBar
        rows={slowest.map((s) => ({
          label: `${s.pvci_userdisplayname ?? "?"} · ${s.pvci_channel ?? "?"} · ${(s.pvci_startdatetimeutc ?? "").slice(5, 16)}`,
          value: s.pvci_maxresponsems ?? 0,
          bad: (s.pvci_maxresponsems ?? 0) >= 10000,
        }))}
        unit="ms"
      />
    </div>
  );
}

function Kpi({ label, value, hint, band }: { label: string; value: string; hint?: string; band?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value ${band ?? ""}`}>{value}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  );
}

function pct(sorted: number[], p: number): number | null {
  if (!sorted.length) return null;
  const i = Math.min(sorted.length - 1, Math.floor(p * (sorted.length - 1)));
  return sorted[i];
}

function group(rows: SessionRow[], key: (s: SessionRow) => string) {
  const map = new Map<string, number>();
  rows.forEach((r) => map.set(key(r), (map.get(key(r)) ?? 0) + 1));
  return Array.from(map.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([label, value]) => ({ label, value }));
}
