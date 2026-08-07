import { useMemo, useState } from "react";
import { ComboChart, HBar, type Bucket } from "./Chart";
import { fmtMs, isEssSession, latencyBand, parseSourceStamp, type SessionRow } from "../lib/model";

type Grain = "hour" | "day";
interface AgentOption { id: string; name: string }

export function Trends({ sessions, loading }: { sessions: SessionRow[]; loading: boolean }) {
  const [agent, setAgent] = useState<string>("*");
  const [hideTest, setHideTest] = useState(true);
  const [essOnly, setEssOnly] = useState(true);
  const [tenant, setTenant] = useState("*");
  const [environment, setEnvironment] = useState("*");
  const [grain, setGrain] = useState<Grain | "auto">("auto");

  const tenantOptions = useMemo(
    () => [...new Set(sessions.map((s) => s.pvci_tenantid).filter((v): v is string => Boolean(v)))].sort((a, b) => a.localeCompare(b)),
    [sessions]
  );

  const environmentOptions = useMemo(() => {
    const options = new Map<string, string>();
    sessions.forEach((s) => {
      const stamp = parseSourceStamp(s.pvci_datasource);
      const key = stamp?.environmentId ?? stamp?.org ?? "unknown";
      const label = stamp?.environmentName ?? stamp?.environmentId ?? stamp?.org ?? "unknown";
      options.set(key, label);
    });
    return [...options.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [sessions]);

  const agents = useMemo(
    () => {
      const options = new Map<string, AgentOption>();
      sessions.forEach((session) => {
        const id = session.pvci_botid ?? session.pvci_botname;
        if (!id) return;
        options.set(id, { id, name: session.pvci_botname ?? "Unnamed agent" });
      });
      return [...options.values()].sort((left, right) => left.name.localeCompare(right.name));
    },
    [sessions]
  );

  const scoped = useMemo(
    () =>
      sessions.filter((s) => {
        if (hideTest && s.pvci_istestmode) return false;
        if (essOnly && !isEssSession(s)) return false;
        if (agent !== "*" && (s.pvci_botid ?? s.pvci_botname) !== agent) return false;
        if (tenant !== "*" && (s.pvci_tenantid ?? "") !== tenant) return false;

        if (environment !== "*") {
          const stamp = parseSourceStamp(s.pvci_datasource);
          const envKey = stamp?.environmentId ?? stamp?.org ?? "unknown";
          if (envKey !== environment) return false;
        }
        return Boolean(s.pvci_startdatetimeutc);
      }),
    [sessions, agent, hideTest, essOnly, tenant, environment]
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
    return {
      sessions: scoped.length,
      answered,
      unanswered: scoped.length - answered,
      p50: pct(lat, 0.5),
      p95: pct(lat, 0.95),
      worst: lat.length ? lat[lat.length - 1] : null,
      toolCalls,
      toolErrors,
      resolvedPct: scoped.length ? Math.round((resolved / scoped.length) * 100) : 0,
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

  if (loading) return <div className="muted pad">Loading…</div>;

  return (
    <div className="trends">
      <div className="trend-bar">
        <select value={agent} onChange={(e) => setAgent(e.target.value)} className="search">
          <option value="*">All agents ({agents.length})</option>
          {agents.map((option) => (
            <option key={option.id} value={option.id}>{option.name}</option>
          ))}
        </select>
        <button className={hideTest ? "on" : ""} onClick={() => setHideTest(!hideTest)}>Hide test mode</button>
        <button className={essOnly ? "on" : ""} onClick={() => setEssOnly(!essOnly)}>ESS only</button>
        <select value={tenant} onChange={(e) => setTenant(e.target.value)} className="search">
          <option value="*">All tenants</option>
          {tenantOptions.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <select value={environment} onChange={(e) => setEnvironment(e.target.value)} className="search">
          <option value="*">All environments</option>
          {environmentOptions.map(([id, label]) => (
            <option key={id} value={id}>{label}</option>
          ))}
        </select>
        {(["auto", "hour", "day"] as const).map((g) => (
          <button key={g} className={grain === g ? "on" : ""} onClick={() => setGrain(g)}>{g}</button>
        ))}
        <span className="muted small">grain: {effectiveGrain}</span>
      </div>

      <div className="kpis">
        <Kpi label="Sessions" value={String(kpi.sessions)} />
        <Kpi label="Answered" value={`${kpi.answered} / ${kpi.sessions}`}
             hint={kpi.unanswered ? `${kpi.unanswered} never got a reply` : undefined} />
        <Kpi label="p50 slowest reply" value={fmtMs(kpi.p50)} band={latencyBand(kpi.p50)} />
        <Kpi label="p95 slowest reply" value={fmtMs(kpi.p95)} band={latencyBand(kpi.p95)} />
        <Kpi label="Worst reply" value={fmtMs(kpi.worst)} band={latencyBand(kpi.worst)} />
        <Kpi label="Tool calls" value={String(kpi.toolCalls)}
             hint={kpi.toolErrors ? `${kpi.toolErrors} failed` : undefined}
             band={kpi.toolErrors ? "bad" : "none"} />
        <Kpi label="Resolved" value={`${kpi.resolvedPct}%`} />
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
