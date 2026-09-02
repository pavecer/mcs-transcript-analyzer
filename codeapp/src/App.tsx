import { useEffect, useMemo, useState } from "react";
import { getContext } from "@microsoft/power-apps/app";
import { Pvci_transcriptsessionsService } from "./generated/services/Pvci_transcriptsessionsService";
import { Pvci_transcriptturnsService } from "./generated/services/Pvci_transcriptturnsService";
import { Pvci_environmentinventoriesService } from "./generated/services/Pvci_environmentinventoriesService";
import { Pvci_creditsyncrunsService } from "./generated/services/Pvci_creditsyncrunsService";
import { SolutionsService } from "./generated/services/SolutionsService";
import { JsonTree } from "./components/JsonTree";
import { Timeline } from "./components/Timeline";
import { ToolCalls } from "./components/ToolCalls";
import { KnowledgeCalls } from "./components/KnowledgeCalls";
import { ReasoningFlow } from "./components/ReasoningFlow";
import { FlowRuns } from "./components/FlowRuns";
import { EssOps } from "./components/EssOps";
import { Trends } from "./components/Trends";
import { Credits } from "./components/Credits";
import { InventoryManagement } from "./components/InventoryManagement";
import { OperationsOverview } from "./components/OperationsOverview";
import { classifyCreditCapability, withTimeout, type CreditCapability } from "./lib/creditCapability";
import { formatObservedPair } from "./lib/telemetryAvailability";
import { buildSessionAlerts } from "./lib/sessionAlerts";
import { isFlowTelemetryAvailable } from "./lib/flowTelemetryAvailability";
import { isCrossEnvironmentCollectionEnabled, scopeRowsToHost } from "./lib/transcriptScope";
import {
  fmtDuration,
  fmtMs,
  fmtTime,
  isEssSession,
  latencyBand,
  safeParse,
  sourceEnvironmentKey,
  sourceEnvironmentLabel,
  type SessionRow,
  type TurnRow,
} from "./lib/model";
import "./App.css";

const SESSION_FIELDS = [
  "pvci_transcriptsessionid", "pvci_transcriptid", "pvci_name",
  "pvci_userdisplayname", "pvci_userupn", "pvci_useraadobjectid",
  "pvci_channel", "pvci_botid", "pvci_botname",
  "pvci_tenantid", "pvci_environmentid", "pvci_environmentname",
  "pvci_topicname", "pvci_topicid",
  "pvci_datasource",
  "pvci_startdatetimeutc", "pvci_enddatetimeutc", "pvci_durationseconds",
  "pvci_messagecount", "pvci_activitycount", "pvci_eventcount",
  "pvci_userturncount", "pvci_agentturncount",
  "pvci_istestmode", "pvci_multiuseranomaly", "pvci_payloadtruncated",
  "pvci_correlationstatus", "pvci_initialusermessage",
  "pvci_firstresponsems", "pvci_avgresponsems", "pvci_maxresponsems",
  "pvci_toolcallcount", "pvci_toolerrorcount", "pvci_tooltotalms", "pvci_maxtoolms",
  "pvci_knowledgecallcount", "pvci_knowledgesourcecount", "pvci_knowledgefailurecount",
  "pvci_sessionoutcome", "pvci_outcomereason",
  "pvci_usererrorcount", "pvci_primaryerrorcode", "pvci_primaryerrortopic", "pvci_errorcategory",
  "pvci_isresolvedimplied", "pvci_turncount",
  "pvci_flowruncount", "pvci_flowrunfailurecount", "pvci_flowrunmaxms",
];

// Fetched only for the selected row - these payloads reach ~140 KB each.
const SESSION_DETAIL_FIELDS = [
  "pvci_transcriptsessionid",
  "pvci_activitiesjson", "pvci_conversationjson", "pvci_planeventsjson",
  "pvci_metadatajson", "pvci_toolcallsjson", "pvci_knowledgecallsjson", "pvci_flowrunsjson", "pvci_primaryerrormessage",
];

const TURN_FIELDS = [
  "pvci_transcriptturnid", "pvci_transcriptid", "pvci_turnindex",
  "pvci_activitytype", "pvci_speaker", "pvci_role", "pvci_eventname",
  "pvci_channelid", "pvci_timestamputc", "pvci_turntext", "pvci_valuejson", "pvci_latencyms",
];

type Tab = "essops" | "replay" | "tools" | "knowledge" | "flows" | "conversation" | "reasoning" | "raw";
type Theme = "light" | "dark";
type View = "sessions" | "trends" | "operations" | "inventory" | "credits";
type CreditCapabilityState = "idle" | "checking" | "error" | CreditCapability;

const THEME_STORAGE_KEY = "pvci-theme";

function initialTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // Storage can be unavailable in a restricted host; OS preference still works.
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

const TAB_LABEL: Record<Tab, string> = {
  essops: "Overview",
  replay: "Replay",
  tools: "Tool Calls",
  knowledge: "Knowledge",
  flows: "Flow Runs",
  conversation: "Conversation JSON",
  reasoning: "Agent Reasoning",
  raw: "Full Transcript JSON",
};

export default function App() {
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [selected, setSelected] = useState<SessionRow | null>(null);
  const [detail, setDetail] = useState<SessionRow | null>(null);
  const [turns, setTurns] = useState<TurnRow[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingTurns, setLoadingTurns] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [hideTest, setHideTest] = useState(false);
  const [essOnly, setEssOnly] = useState(false);
  const [environmentFilter, setEnvironmentFilter] = useState("*");
  const [tab, setTab] = useState<Tab>("essops");
  const [jsonFilter, setJsonFilter] = useState("");
  const [view, setView] = useState<View>("sessions");
  const [creditsSidebarTarget, setCreditsSidebarTarget] = useState<HTMLDivElement | null>(null);
  const [creditCapability, setCreditCapability] = useState<CreditCapabilityState>("idle");
  const [creditCheckVersion, setCreditCheckVersion] = useState(0);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [hostEnvironmentId, setHostEnvironmentId] = useState<string>();
  const [enabledCollectorEnvironmentIds, setEnabledCollectorEnvironmentIds] = useState<string[]>([]);

  const crossEnvironmentEnabled = useMemo(
    () => isCrossEnvironmentCollectionEnabled(enabledCollectorEnvironmentIds, hostEnvironmentId),
    [enabledCollectorEnvironmentIds, hostEnvironmentId],
  );

  useEffect(() => {
    void getContext()
      .then((context) => setHostEnvironmentId(context.app.environmentId))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // The selected theme remains active for this session.
    }
  }, [theme]);

  useEffect(() => {
    if (view !== "credits") return;
    let cancelled = false;

    void (async () => {
      setCreditCapability("checking");
      try {
        const solutionResult = await withTimeout(
          SolutionsService.getAll({
            select: ["solutionid"],
            filter: "uniquename eq 'pvConversationInsightsCredits'",
            top: 1,
          }),
          15_000,
        );
        const addonInstalled = (solutionResult.data ?? []).length > 0;
        let hasSyncRun = false;
        if (addonInstalled) {
          const syncResult = await withTimeout(
            Pvci_creditsyncrunsService.getAll({
              select: ["pvci_creditsyncrunid"],
              filter: "pvci_status eq 'success'",
              top: 1,
            }),
            15_000,
          );
          hasSyncRun = (syncResult.data ?? []).length > 0;
        }
        if (!cancelled) setCreditCapability(classifyCreditCapability(addonInstalled, hasSyncRun));
      } catch {
        if (!cancelled) setCreditCapability("error");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [view, creditCheckVersion]);

  useEffect(() => {
    void (async () => {
      try {
        const res = await Pvci_transcriptsessionsService.getAll({
          select: SESSION_FIELDS,
          orderBy: ["pvci_startdatetimeutc desc"],
          top: 200,
        });
        const rawRows = (res.data ?? []) as unknown as SessionRow[];
        const environmentNames = new Map<string, string>();
        try {
          const inventoryRes = await Pvci_environmentinventoriesService.getAll({
            select: ["pvci_environmentid", "pvci_displayname", "pvci_transcriptcollectorenabled"],
            top: 500,
          });
          const inventoryRows = (inventoryRes.data ?? []) as unknown as Array<{
            pvci_environmentid?: string;
            pvci_displayname?: string;
            pvci_transcriptcollectorenabled?: boolean;
          }>;
          inventoryRows.forEach((environment) => {
            if (environment.pvci_environmentid && environment.pvci_displayname) {
              environmentNames.set(environment.pvci_environmentid.toLowerCase(), environment.pvci_displayname);
            }
          });
          setEnabledCollectorEnvironmentIds(inventoryRows
            .filter((environment) => environment.pvci_transcriptcollectorenabled && environment.pvci_environmentid)
            .map((environment) => environment.pvci_environmentid!));
        } catch {
          // Session lineage still provides a friendly-name fallback when inventory is unavailable.
        }
        const rows = rawRows.map((session) => ({
          ...session,
          pvci_environmentname: environmentNames.get((session.pvci_environmentid ?? "").toLowerCase())
            ?? session.pvci_environmentname,
        }));
        setSessions(rows);
        if (rows.length) setSelected(rows[0]);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoadingSessions(false);
      }
    })();
  }, []);

  const visibleSessions = useMemo(
    () => scopeRowsToHost(sessions, hostEnvironmentId, crossEnvironmentEnabled),
    [sessions, hostEnvironmentId, crossEnvironmentEnabled],
  );

  const activeEnvironmentFilter = crossEnvironmentEnabled ? environmentFilter : "*";

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return visibleSessions.filter((session) => {
      if (hideTest && session.pvci_istestmode) return false;
      if (essOnly && !isEssSession(session)) return false;
      if (activeEnvironmentFilter !== "*" && sourceEnvironmentKey(session) !== activeEnvironmentFilter) return false;
      if (!q) return true;
      return [
        session.pvci_userdisplayname, session.pvci_userupn, session.pvci_channel, session.pvci_initialusermessage,
        session.pvci_botname, session.pvci_topicname, session.pvci_primaryerrorcode, session.pvci_primaryerrortopic,
        session.pvci_errorcategory, session.pvci_knowledgecallcount ? "knowledge" : undefined,
      ].some((value) => (value ?? "").toLowerCase().includes(q));
    });
  }, [visibleSessions, search, hideTest, essOnly, activeEnvironmentFilter]);

  const activeSession = selected && filtered.some((session) => session.pvci_transcriptsessionid === selected.pvci_transcriptsessionid)
    ? selected
    : filtered[0] ?? null;

  useEffect(() => {
    const transcriptId = activeSession?.pvci_transcriptid;
    const sessionId = activeSession?.pvci_transcriptsessionid;
    let cancelled = false;

    void (async () => {
      if (!transcriptId || !sessionId) {
        if (!cancelled) {
          setTurns([]);
          setDetail(null);
        }
        return;
      }
      setLoadingTurns(true);
      setDetail(null);
      try {
        const [turnRes, detailRes] = await Promise.all([
          Pvci_transcriptturnsService.getAll({
            select: TURN_FIELDS,
            filter: `pvci_transcriptid eq '${transcriptId}'`,
            orderBy: ["pvci_turnindex asc"],
            top: 500,
          }),
          Pvci_transcriptsessionsService.get(sessionId, { select: SESSION_DETAIL_FIELDS }),
        ]);
        if (!cancelled) {
          setTurns((turnRes.data ?? []) as unknown as TurnRow[]);
          setDetail((detailRes.data ?? null) as unknown as SessionRow | null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoadingTurns(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeSession]);

  const environmentOptions = useMemo(() => {
    const options = new Map<string, string>();
    visibleSessions.forEach((s) => {
      options.set(sourceEnvironmentKey(s), sourceEnvironmentLabel(s));
    });
    return [...options.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [visibleSessions]);

  const handleCollectorStateChange = (environmentId: string, enabled: boolean) => {
    if (!enabled) setEnvironmentFilter("*");
    setEnabledCollectorEnvironmentIds((current) => enabled
      ? [...new Set([...current, environmentId])]
      : current.filter((id) => id.toLowerCase() !== environmentId.toLowerCase()));
  };

  const openSessionFromInventory = async (sessionId: string) => {
    setError(null);
    try {
      const existing = sessions.find((session) => session.pvci_transcriptsessionid === sessionId);
      const session = existing ?? (await Pvci_transcriptsessionsService.get(sessionId, { select: SESSION_FIELDS })).data as unknown as SessionRow;
      setSessions((current) => [session, ...current.filter((row) => row.pvci_transcriptsessionid !== sessionId)]);
      setSelected(session);
      setSearch("");
      setHideTest(false);
      setEssOnly(false);
      setEnvironmentFilter("*");
      setTab("essops");
      setView("sessions");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return (
    <div className={`app ${view}-view`}>
      <header className="app-header">
        <div className="app-brand">
          <strong>Conversation Insights</strong>
          <span>{view === "sessions"
            ? `${sessions.length} sessions`
            : view === "trends"
              ? "Quality and latency"
              : view === "operations"
                ? "Flow health and runs"
              : view === "inventory"
                ? "Environment readiness"
                : "Usage and governance"}</span>
        </div>
        <nav className="viewswitch app-navigation" aria-label="Primary navigation">
          <button type="button" className={view === "sessions" ? "on" : ""} aria-current={view === "sessions" ? "page" : undefined} onClick={() => setView("sessions")}>Sessions</button>
          <button type="button" className={view === "trends" ? "on" : ""} aria-current={view === "trends" ? "page" : undefined} onClick={() => setView("trends")}>Trends</button>
          <button type="button" className={view === "operations" ? "on" : ""} aria-current={view === "operations" ? "page" : undefined} onClick={() => setView("operations")}>Operations</button>
          <button type="button" className={view === "inventory" ? "on" : ""} aria-current={view === "inventory" ? "page" : undefined} onClick={() => setView("inventory")}>Inventory</button>
          <button type="button" className={view === "credits" ? "on" : ""} aria-current={view === "credits" ? "page" : undefined} onClick={() => setView("credits")}>Credits</button>
        </nav>
        <button
          className="theme-toggle"
          type="button"
          title={`Use ${theme === "dark" ? "light" : "dark"} mode`}
          aria-label={`Use ${theme === "dark" ? "light" : "dark"} mode`}
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          <span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span>
        </button>
      </header>

      <div className="app-workspace">
      {(view === "sessions" || view === "credits") && <aside className="sidebar">
        {view === "sessions" && (
          <>
            <div className="sidebar-heading">
              <strong>Sessions</strong>
              <span>{filtered.length} shown</span>
            </div>
            <input
              className="search"
              placeholder="Search user, channel, first message…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <label className="checkline">
              <input type="checkbox" checked={hideTest} onChange={(e) => setHideTest(e.target.checked)} />
              Hide test-mode sessions
            </label>
            <label className="checkline">
              <input type="checkbox" checked={essOnly} onChange={(e) => setEssOnly(e.target.checked)} />
              ESS agents only
            </label>
            {crossEnvironmentEnabled && <select className="search" value={environmentFilter} onChange={(e) => setEnvironmentFilter(e.target.value)}>
              <option value="*">All environments</option>
              {environmentOptions.map(([id, label]) => (
                <option key={id} value={id}>{label}</option>
              ))}
            </select>}

            <div className="session-list">
              {loadingSessions && <div className="muted pad">Loading…</div>}
              {!loadingSessions && !filtered.length && <div className="muted pad">No sessions match.</div>}
              {filtered.map((s) => {
                const flowTelemetryAvailable = isFlowTelemetryAvailable(s, hostEnvironmentId);
                const alerts = buildSessionAlerts({
                  userErrorCount: s.pvci_usererrorcount,
                  errorCategory: s.pvci_errorcategory,
                  primaryErrorCode: s.pvci_primaryerrorcode,
                  toolErrorCount: s.pvci_toolerrorcount,
                  candidateFlowFailureCount: flowTelemetryAvailable ? s.pvci_flowrunfailurecount : null,
                  payloadTruncated: s.pvci_payloadtruncated,
                });
                return (
                  <button
                    key={s.pvci_transcriptsessionid}
                    className={`session-item${alerts.some((alert) => alert.kind === "error") ? " has-error" : ""}${activeSession?.pvci_transcriptsessionid === s.pvci_transcriptsessionid ? " active" : ""}`}
                    onClick={() => { setSelected(s); setTab("essops"); }}
                  >
                    <div className="si-top">
                      <span className="si-user">{s.pvci_userdisplayname ?? "Unknown user"}</span>
                      <span className="chip">{s.pvci_channel ?? "—"}</span>
                    </div>
                    {alerts.length > 0 && <div className="si-alerts" aria-label="Session alerts">
                      {alerts.map((alert) => <span key={alert.text} className={`si-alert ${alert.kind}`}>{alert.text}</span>)}
                    </div>}
                    <div className="si-sub muted small">
                      {fmtTime(s.pvci_startdatetimeutc)} · {s.pvci_messagecount == null ? "messages unavailable" : `${s.pvci_messagecount} msg`} · {fmtDuration(s.pvci_durationseconds)}
                    </div>
                    <div className="si-metrics">
                      <span className={`lat ${latencyBand(s.pvci_maxresponsems)}`}>
                        slowest reply {fmtMs(s.pvci_maxresponsems)}
                      </span>
                      {s.pvci_toolcallcount != null && s.pvci_toolcallcount > 0 && (
                        <span className="lat none">{s.pvci_toolcallcount} tools</span>
                      )}
                    </div>
                    {s.pvci_initialusermessage && <div className="si-snippet">{s.pvci_initialusermessage.slice(0, 90)}</div>}
                    <div className="si-flags">
                      {s.pvci_istestmode && <span className="flag test">test</span>}
                      {s.pvci_multiuseranomaly && <span className="flag warn">multi-user</span>}
                      {s.pvci_correlationstatus && s.pvci_correlationstatus !== "exact" && (
                        <span className="flag warn">{s.pvci_correlationstatus}</span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </>
        )}
        {view === "credits" && <div ref={setCreditsSidebarTarget} className="credits-sidebar-host" />}
      </aside>}

      <main className={`main${view === "trends" ? " trends-main" : ""}`}>
        {error && <div className="error">{error}</div>}

        {view === "trends" && (
          <>
            <Trends key={crossEnvironmentEnabled ? "cross" : "local"} sessions={visibleSessions} loading={loadingSessions} allowEnvironmentSelection={crossEnvironmentEnabled} />
          </>
        )}

        {view === "operations" && <OperationsOverview hostEnvironmentId={hostEnvironmentId} onNavigate={(destination) => setView(destination)} />}

        {view === "credits" && creditCapability === "checking" && (
          <div className="capability-state muted">Checking Copilot Credit availability…</div>
        )}

        {view === "credits" && creditCapability === "unavailable" && (
          <div className="capability-state">
            <span className="eyebrow">Optional add-on</span>
            <h2>Copilot Credit reporting is not installed</h2>
            <p>Transcript analysis remains fully available. Install the Credit runtime add-on to enable usage, capacity, and governance reporting.</p>
            <a className="capability-action" href="https://github.com/pavecer/mcs-transcript-analyzer/releases/latest" target="_blank" rel="noreferrer">Get the Credit add-on</a>
          </div>
        )}

        {view === "credits" && creditCapability === "setup-required" && (
          <div className="capability-state">
            <span className="eyebrow">Setup required</span>
            <h2>Copilot Credit reporting is installed</h2>
            <p>Map the two licensing connections and run the packaged credit collection flow to initialize this workspace.</p>
            <button type="button" className="capability-action" onClick={() => setCreditCheckVersion((version) => version + 1)}>Check again</button>
          </div>
        )}

        {view === "credits" && creditCapability === "error" && (
          <div className="capability-state">
            <span className="eyebrow">Availability check failed</span>
            <h2>Copilot Credit status could not be verified</h2>
            <p>Confirm that your security role can read installed solutions, then retry.</p>
            <button type="button" className="capability-action" onClick={() => setCreditCheckVersion((version) => version + 1)}>Retry</button>
          </div>
        )}

        {view === "credits" && creditCapability === "ready" && <Credits key={crossEnvironmentEnabled ? "cross" : "local"} sidebarTarget={creditsSidebarTarget} allowEnvironmentSelection={crossEnvironmentEnabled} hostEnvironmentId={hostEnvironmentId} />}

        {view === "inventory" && <InventoryManagement hostEnvironmentId={hostEnvironmentId} onCollectorStateChange={handleCollectorStateChange} onOpenSession={(sessionId) => void openSessionFromInventory(sessionId)} />}

        {view === "sessions" && !activeSession && !loadingSessions && <div className="muted pad">No sessions match the current filters.</div>}

        {view === "sessions" && activeSession && (
          <>
            <header className="detail-head">
              <div className="session-identity">
                <div className="session-person">
                  <h2>{activeSession.pvci_userdisplayname ?? "Unknown user"}</h2>
                  <div className="muted small">{activeSession.pvci_userupn ?? activeSession.pvci_useraadobjectid ?? "—"}</div>
                </div>
                <div className="session-context" aria-label="Session context">
                  <span>{activeSession.pvci_channel ?? "Unknown channel"}</span>
                  <span>{sourceEnvironmentLabel(activeSession)}</span>
                  <span>{activeSession.pvci_istestmode ? "Test chat" : "Production"}</span>
                </div>
              </div>

              <div className="signal-groups">
                <section className="signal-group" aria-labelledby="conversation-signals-heading">
                  <h3 id="conversation-signals-heading">Conversation</h3>
                  <dl className="signal-grid conversation-signals">
                    <Fact k="Duration" v={fmtDuration(activeSession.pvci_durationseconds)} />
                    <Fact
                      k="Turns"
                      v={formatObservedPair(
                        activeSession.pvci_userturncount,
                        { singular: "user turn", plural: "user turns" },
                        activeSession.pvci_agentturncount,
                        { singular: "agent turn", plural: "agent turns" },
                      )}
                    />
                    <Fact k="Outcome" v={activeSession.pvci_sessionoutcome} />
                    <Fact
                      k="User errors"
                      v={activeSession.pvci_usererrorcount == null
                        ? "Unavailable in this transcript"
                        : activeSession.pvci_usererrorcount > 0
                          ? `${activeSession.pvci_usererrorcount} · ${activeSession.pvci_errorcategory ?? activeSession.pvci_primaryerrorcode ?? "user error"}`
                          : "0"}
                    />
                    <Fact k="First reply" v={fmtMs(activeSession.pvci_firstresponsems)} />
                    <Fact k="Slowest reply" v={fmtMs(activeSession.pvci_maxresponsems)} />
                  </dl>
                </section>

                <section className="signal-group" aria-labelledby="observability-signals-heading">
                  <h3 id="observability-signals-heading">Observed telemetry</h3>
                  <dl className="signal-grid observability-signals">
                    <Fact
                      k="Exact tool traces"
                      v={activeSession.pvci_istestmode
                        ? formatObservedPair(
                            activeSession.pvci_toolcallcount,
                            { singular: "tool call", plural: "tool calls" },
                            activeSession.pvci_toolerrorcount,
                            { singular: "failed call", plural: "failed calls" },
                          )
                        : "Unavailable in this transcript"}
                    />
                    <Fact
                      k="Knowledge"
                      v={formatObservedPair(
                        activeSession.pvci_knowledgecallcount,
                        { singular: "retrieval", plural: "retrievals" },
                        activeSession.pvci_knowledgesourcecount,
                        { singular: "source ID", plural: "source IDs" },
                      )}
                    />
                    <Fact
                      k="Candidate flow matches"
                      v={isFlowTelemetryAvailable(activeSession, hostEnvironmentId)
                        ? formatObservedPair(
                            activeSession.pvci_flowruncount,
                            { singular: "candidate match", plural: "candidate matches" },
                            activeSession.pvci_flowrunfailurecount,
                            { singular: "failed run", plural: "failed runs" },
                          )
                        : "Unavailable for this source transcript"}
                    />
                    <Fact k="Slowest exact tool" v={fmtMs(activeSession.pvci_maxtoolms)} />
                  </dl>
                </section>
              </div>

              <details className="technical-details">
                <summary>Session metadata</summary>
                <dl className="technical-grid">
                  <Fact k="Agent" v={activeSession.pvci_botname} />
                  <Fact k="Tenant" v={activeSession.pvci_tenantid} />
                  <Fact k="Identity match" v={activeSession.pvci_correlationstatus ?? "unknown"} />
                  <Fact k="Capture" v={activeSession.pvci_payloadtruncated ? "Truncated" : "Complete stored payload"} />
                  <Fact k="Session topic" v={activeSession.pvci_topicname ?? activeSession.pvci_topicid} />
                  <Fact k="Started (UTC)" v={fmtTime(activeSession.pvci_startdatetimeutc)} />
                  <Fact k="Outcome detail" v={activeSession.pvci_outcomereason} />
                  <Fact k="Implied resolved" v={activeSession.pvci_isresolvedimplied} />
                </dl>
              </details>
            </header>

            <nav className="tabs">
              {(Object.keys(TAB_LABEL) as Tab[]).map((t) => (
                <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
                  {TAB_LABEL[t]}
                </button>
              ))}
            </nav>

            <section className="pane">
              {tab === "essops" ? (
                <EssOps
                  session={detail ? { ...activeSession, ...detail } : activeSession}
                  turns={turns}
                  loading={loadingTurns}
                  flowTelemetryAvailable={isFlowTelemetryAvailable(activeSession, hostEnvironmentId)}
                />
              ) : tab === "replay" ? (
                <Timeline turns={turns} loading={loadingTurns} />
              ) : tab === "tools" ? (
                <ToolCalls
                  json={detail?.pvci_toolcallsjson}
                  loading={loadingTurns}
                  exactTelemetryAvailable={Boolean(activeSession.pvci_istestmode)}
                  planEventsJson={detail?.pvci_planeventsjson}
                />
              ) : tab === "knowledge" ? (
                <KnowledgeCalls json={detail?.pvci_knowledgecallsjson} loading={loadingTurns} />
              ) : tab === "flows" ? (
                <FlowRuns
                  json={detail?.pvci_flowrunsjson}
                  loading={loadingTurns}
                  telemetryAvailable={isFlowTelemetryAvailable(activeSession, hostEnvironmentId)}
                />
              ) : tab === "reasoning" ? (
                <ReasoningFlow json={detail?.pvci_planeventsjson} knowledgeJson={detail?.pvci_knowledgecallsjson} loading={loadingTurns} />
              ) : (
                <>
                  <input
                    className="search json-filter"
                    placeholder="Filter JSON keys and values…"
                    value={jsonFilter}
                    onChange={(e) => setJsonFilter(e.target.value)}
                  />
                  <JsonPane
                    text={
                      tab === "conversation" ? detail?.pvci_conversationjson : detail?.pvci_activitiesjson
                    }
                    filter={jsonFilter}
                    depth={tab === "raw" ? 2 : 3}
                    extra={tab === "raw" ? detail?.pvci_metadatajson : undefined}
                    loading={loadingTurns}
                  />
                </>
              )}
            </section>
          </>
        )}
      </main>
      </div>
    </div>
  );
}

function Fact({ k, v }: { k: string; v?: string | number | null }) {
  return (
    <div className="fact">
      <dt>{k}</dt>
      <dd>{v === undefined || v === null || v === "" ? "—" : String(v)}</dd>
    </div>
  );
}

function JsonPane({ text, filter, depth, extra, loading }:
  { text?: string; filter: string; depth: number; extra?: string; loading?: boolean }) {
  const parsed = safeParse(text);
  const parsedExtra = safeParse(extra);

  if (loading) return <div className="muted pad">Loading payload…</div>;
  if (parsed === undefined) return <div className="muted pad">No JSON stored for this session.</div>;

  return (
    <>
      <div className="muted small pad-sm">{(text ?? "").length.toLocaleString()} chars</div>
      <JsonTree value={parsed} initialCollapseDepth={depth} filter={filter} />
      {parsedExtra !== undefined && (
        <>
          <h3 className="sub">Transcript metadata</h3>
          <JsonTree value={parsedExtra} initialCollapseDepth={3} filter={filter} />
        </>
      )}
    </>
  );
}
