import { useEffect, useMemo, useState } from "react";
import { Pvci_transcriptsessionsService } from "../generated/services/Pvci_transcriptsessionsService";
import type { Pvci_agentinventories } from "../generated/models/Pvci_agentinventoriesModel";
import type { Pvci_environmentinventories } from "../generated/models/Pvci_environmentinventoriesModel";
import type { Pvci_transcriptsessions } from "../generated/models/Pvci_transcriptsessionsModel";
import {
  buildAgentInventoryPresentations,
  type AgentAuthorship,
  type AgentDeployment,
  type AgentInventoryEvidence,
  type AgentInventoryPresentation,
  type AgentSessionEvidence,
} from "../lib/agentInventoryPresentation";

const SESSION_FIELDS = [
  "pvci_transcriptsessionid", "pvci_tenantid", "pvci_environmentid", "pvci_botid", "pvci_botname",
  "pvci_startdatetimeutc", "pvci_channel", "pvci_sessionoutcome", "pvci_initialusermessage", "pvci_usererrorcount",
];

type CollectionFilter = "all" | "available" | "unavailable";
type SessionQueryRow = Pvci_transcriptsessions & {
  pvci_environmentid?: string;
  pvci_usererrorcount?: number;
};

export function AgentInventory({ agents, environments, hostEnvironmentId, loading, error, focusEnvironmentId, onOpenSession }: {
  agents: Pvci_agentinventories[];
  environments: Pvci_environmentinventories[];
  hostEnvironmentId?: string;
  loading: boolean;
  error?: string | null;
  focusEnvironmentId?: string;
  onOpenSession: (sessionId: string) => void;
}) {
  const [sessions, setSessions] = useState<SessionQueryRow[]>([]);
  const [sessionEvidenceState, setSessionEvidenceState] = useState<"loading" | "available" | "unavailable">("loading");
  const [sessionLoading, setSessionLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [environmentFilter, setEnvironmentFilter] = useState(() => focusEnvironmentId?.toLowerCase() ?? "*");
  const [authorshipFilter, setAuthorshipFilter] = useState<"all" | AgentAuthorship>("all");
  const [deploymentFilter, setDeploymentFilter] = useState<"all" | AgentDeployment>("all");
  const [collectionFilter, setCollectionFilter] = useState<CollectionFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void Pvci_transcriptsessionsService.getAll({
      select: SESSION_FIELDS,
      orderBy: ["pvci_startdatetimeutc desc"],
      top: 2000,
    }).then((result) => {
      if (cancelled) return;
      setSessions((result.data ?? []) as unknown as SessionQueryRow[]);
      setSessionEvidenceState("available");
      setSessionError(null);
    }).catch((reason) => {
      if (cancelled) return;
      setSessions([]);
      setSessionEvidenceState("unavailable");
      setSessionError(reason instanceof Error ? reason.message : String(reason));
    }).finally(() => {
      if (!cancelled) setSessionLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  const presentations = useMemo(() => buildAgentInventoryPresentations(
    agents.map(toAgentEvidence),
    environments.map((row) => ({
      id: row.pvci_environmentinventoryid,
      tenantId: row.pvci_tenantid,
      environmentId: row.pvci_environmentid,
      displayName: row.pvci_displayname,
      collectorEnabled: row.pvci_transcriptcollectorenabled,
      accessStatus: row.pvci_transcriptaccessstatus,
      onboardingStatus: row.pvci_transcriptonboardingstatus,
    })),
    sessions.map(toSessionEvidence),
    hostEnvironmentId,
    sessionEvidenceState,
  ), [agents, environments, hostEnvironmentId, sessionEvidenceState, sessions]);

  const environmentOptions = useMemo(() => {
    const options = new Map<string, string>();
    presentations.forEach((row) => {
      if (row.agent.environmentId) options.set(row.agent.environmentId.toLowerCase(), row.environmentLabel);
    });
    return [...options.entries()].sort((left, right) => left[1].localeCompare(right[1]));
  }, [presentations]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return presentations.filter((row) => {
      if (environmentFilter !== "*" && row.agent.environmentId?.toLowerCase() !== environmentFilter) return false;
      if (authorshipFilter !== "all" && row.authorship !== authorshipFilter) return false;
      if (deploymentFilter !== "all" && row.deployment !== deploymentFilter) return false;
      if (collectionFilter === "available" && !row.collection.available) return false;
      if (collectionFilter === "unavailable" && row.collection.available) return false;
      if (!query) return true;
      return [row.agent.displayName, row.agent.schemaName, row.agent.resourceId, row.environmentLabel, row.agent.authoringOrigin]
        .some((value) => (value ?? "").toLowerCase().includes(query));
    });
  }, [authorshipFilter, collectionFilter, deploymentFilter, environmentFilter, presentations, search]);

  const selected = presentations.find((row) => row.agent.id === selectedId) ?? null;
  const counts = useMemo(() => ({
    total: presentations.length,
    userCreated: presentations.filter((row) => row.authorship === "user-created").length,
    microsoftProvided: presentations.filter((row) => row.authorship === "microsoft-provided").length,
    managed: presentations.filter((row) => row.deployment === "managed").length,
    collectionAvailable: presentations.filter((row) => row.collection.available).length,
    withSessions: presentations.filter((row) => ["exact", "candidate", "ambiguous"].includes(row.sessionMatch)).length,
    unknownAuthorship: presentations.filter((row) => row.authorship === "unknown").length,
  }), [presentations]);

  const clearFilters = () => {
    setSearch("");
    setEnvironmentFilter("*");
    setAuthorshipFilter("all");
    setDeploymentFilter("all");
    setCollectionFilter("all");
  };

  return <section className="agent-inventory" aria-labelledby="agent-inventory-heading">
    <div className="agent-inventory-heading">
      <div>
        <span className="report-eyebrow">Tenant agent inventory</span>
        <h3 id="agent-inventory-heading">Discovered agents by environment</h3>
        <p>Authorship uses Microsoft-reserved markers and direct creator evidence. Managed deployment is separate and does not change who created the agent.</p>
      </div>
      <button type="button" className="inventory-refresh" onClick={clearFilters}>Clear filters</button>
    </div>

    {error && <div className="error">Agent inventory could not be read: {error}</div>}
    {sessionError && <div className="error">Session evidence could not be read: {sessionError}</div>}

    <div className="agent-kpis" aria-label="Agent inventory summary">
      <AgentKpi label="Discovered" value={counts.total} />
      <AgentKpi label="User-created" value={counts.userCreated} tone="good" />
      <AgentKpi label="Microsoft-provided" value={counts.microsoftProvided} />
      <AgentKpi label="Managed deployment" value={counts.managed} />
      <AgentKpi label="Collection available" value={counts.collectionAvailable} tone="good" />
      <AgentKpi label="With candidate sessions" value={counts.withSessions} tone={counts.withSessions ? "warn" : undefined} />
      <AgentKpi label="Authorship unknown" value={counts.unknownAuthorship} tone={counts.unknownAuthorship ? "warn" : undefined} />
    </div>

    {selected && <AgentReview row={selected} sessionLoading={sessionLoading} onClose={() => setSelectedId(null)} onOpenSession={onOpenSession} />}

    <div className="agent-toolbar">
      <input className="search" type="search" placeholder="Search agent, schema, environment, or source…" value={search} onChange={(event) => setSearch(event.target.value)} />
      <select className="search" value={environmentFilter} onChange={(event) => setEnvironmentFilter(event.target.value)} aria-label="Filter agents by environment">
        <option value="*">All environments</option>
        {environmentOptions.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </select>
      <select className="search" value={authorshipFilter} onChange={(event) => setAuthorshipFilter(event.target.value as "all" | AgentAuthorship)} aria-label="Filter agents by authorship">
        <option value="all">All authorship</option>
        <option value="user-created">User-created</option>
        <option value="microsoft-provided">Microsoft-provided</option>
        <option value="unknown">Authorship unknown</option>
      </select>
      <select className="search" value={deploymentFilter} onChange={(event) => setDeploymentFilter(event.target.value as "all" | AgentDeployment)} aria-label="Filter agents by deployment">
        <option value="all">All deployments</option>
        <option value="managed">Managed deployment</option>
        <option value="unmanaged">Unmanaged deployment</option>
        <option value="unknown">Deployment unknown</option>
      </select>
      <select className="search" value={collectionFilter} onChange={(event) => setCollectionFilter(event.target.value as CollectionFilter)} aria-label="Filter agents by collection availability">
        <option value="all">All collection states</option>
        <option value="available">Collection available</option>
        <option value="unavailable">Collection unavailable</option>
      </select>
      <span className="muted small">{filtered.length} of {presentations.length}</span>
    </div>

    <div className="inventory-table-wrap agent-table-wrap">
      <table className="runtable agent-table">
        <thead><tr><th>Agent</th><th>Environment</th><th>Authorship</th><th>Deployment</th><th>Published</th><th>Collection</th><th>Session evidence</th><th>Last inventoried</th><th /></tr></thead>
        <tbody>
          {loading && !agents.length && <tr><td colSpan={9} className="muted">Loading discovered agents…</td></tr>}
          {!loading && !filtered.length && <tr><td colSpan={9} className="muted">No agents match these filters.</td></tr>}
          {filtered.map((row) => <tr key={row.agent.id} className={selected?.agent.id === row.agent.id ? "selected" : undefined}>
            <td><strong>{row.agent.displayName ?? "Unnamed agent"}</strong><span className="inventory-row-id">{row.agent.schemaName ?? row.agent.resourceId ?? "Source ID unavailable"}</span></td>
            <td><strong>{row.environmentLabel}</strong><span className="inventory-row-id">{row.agent.environmentId ?? "Environment ID unavailable"}</span></td>
            <td><span className={`agent-evidence ${row.authorship}`}>{row.authorship === "user-created" ? "User-created" : row.authorship === "microsoft-provided" ? "Microsoft-provided" : "Unknown"}</span><small>{row.authorshipLabel}</small></td>
            <td><span className={`agent-evidence ${row.deployment}`}>{row.deploymentLabel}</span></td>
            <td>{row.agent.published == null ? "Unknown" : row.agent.published ? "Published" : "Not observed"}</td>
            <td title={row.collection.reason}><span className={`agent-evidence ${row.collection.available ? "available" : "unavailable"}`}>{row.collection.label}</span></td>
            <td><span className={`agent-session-evidence ${row.sessionMatch}`}>{row.sessionLabel}</span></td>
            <td>{formatDateTime(row.agent.lastSyncedOn)}</td>
            <td><button type="button" className="onboarding-link" onClick={() => setSelectedId(row.agent.id)}>Review</button></td>
          </tr>)}
        </tbody>
      </table>
    </div>
    <p className="agent-evidence-note">Session counts use exact environment/tenant/Bot ID only when IDs match. Agent-name matches are labeled candidate or ambiguous and never presented as exact attribution. The session sample is limited to the 2,000 most recent retained sessions.</p>
  </section>;
}

function AgentReview({ row, sessionLoading, onClose, onOpenSession }: {
  row: AgentInventoryPresentation;
  sessionLoading: boolean;
  onClose: () => void;
  onOpenSession: (sessionId: string) => void;
}) {
  const sessions = row.exactSessions.length ? row.exactSessions : row.candidateSessions;
  return <section className="agent-review" aria-label={`Agent review for ${row.agent.displayName ?? "unnamed agent"}`}>
    <header>
      <div><span className="report-eyebrow">Selected agent</span><h4>{row.agent.displayName ?? "Unnamed agent"}</h4><span>{row.environmentLabel}</span></div>
      <button type="button" className="onboarding-close" onClick={onClose} aria-label="Close agent review">×</button>
    </header>
    <dl className="agent-review-facts">
      <ReviewFact label="Authorship" value={row.authorshipLabel} />
      <ReviewFact label="Deployment" value={row.deploymentLabel} />
      <ReviewFact label="Collection" value={row.collection.label} />
      <ReviewFact label="Session match" value={row.sessionLabel} />
      <ReviewFact label="Authoring source" value={row.agent.authoringOrigin ?? "Unknown"} />
      <ReviewFact label="Last inventoried" value={formatDateTime(row.agent.lastSyncedOn)} />
    </dl>
    {!row.collection.available && <div className="agent-session-warning"><strong>Session details unavailable</strong><span>{row.collection.reason}</span></div>}
    {row.collection.available && row.sessionMatch === "ambiguous" && <div className="agent-session-warning"><strong>Candidate attribution is ambiguous</strong><span>More than one discovered agent has this name in the environment. Review the sessions, but do not treat the count as exact agent attribution.</span></div>}
    {row.collection.available && <div className="agent-session-list">
      <h5>{row.exactSessions.length ? "Exactly attributed collected sessions" : "Candidate collected sessions by agent name"}</h5>
      {sessionLoading && <p className="muted">Loading session evidence…</p>}
      {!sessionLoading && !sessions.length && <p className="muted">No name-matched sessions were found in the recent retained sample. This is not proof that the agent has never run.</p>}
      {sessions.slice(0, 10).map((session) => <article key={session.id}>
        <div><strong>{formatDateTime(session.startedOn)}</strong><span>{session.channel ?? "Channel unknown"} · {session.outcome ?? "Outcome unknown"}</span></div>
        <div className="agent-session-actions">
          <span className={session.userErrorCount ? "agent-session-error" : "muted"}>{session.userErrorCount == null ? "Errors unavailable" : `${session.userErrorCount} user ${session.userErrorCount === 1 ? "error" : "errors"}`}</span>
          <button type="button" className="onboarding-link" onClick={() => onOpenSession(session.id)}>Open session</button>
        </div>
        {session.initialMessage && <p>{session.initialMessage.slice(0, 180)}</p>}
      </article>)}
    </div>}
  </section>;
}

function toAgentEvidence(row: Pvci_agentinventories): AgentInventoryEvidence {
  return {
    id: row.pvci_agentinventoryid,
    tenantId: row.pvci_tenantid,
    environmentId: row.pvci_environmentid,
    botId: row.pvci_botid,
    resourceId: row.pvci_resourceid,
    displayName: row.pvci_displayname,
    schemaName: row.pvci_schemaname,
    authoringOrigin: row.pvci_authoringorigin,
    published: row.pvci_published,
    lastSyncedOn: row.pvci_lastsyncedon,
    evidenceJson: row.pvci_evidencejson,
  };
}

function toSessionEvidence(row: SessionQueryRow): AgentSessionEvidence {
  return {
    id: row.pvci_transcriptsessionid,
    tenantId: row.pvci_tenantid,
    environmentId: row.pvci_environmentid,
    botId: row.pvci_botid,
    botName: row.pvci_botname,
    startedOn: row.pvci_startdatetimeutc,
    channel: row.pvci_channel,
    outcome: row.pvci_sessionoutcome,
    initialMessage: row.pvci_initialusermessage,
    userErrorCount: row.pvci_usererrorcount,
  };
}

function AgentKpi({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return <div className="kpi"><span className="kpi-label">{label}</span><span className={`kpi-value ${tone ?? ""}`}>{value}</span></div>;
}

function ReviewFact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function formatDateTime(value?: string) {
  if (!value) return "Unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
