import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { CreditTrend, HBar } from "./Chart";
import { Pvci_agentinventoriesService } from "../generated/services/Pvci_agentinventoriesService";
import { Pvci_creditcapacitysnapshotsService } from "../generated/services/Pvci_creditcapacitysnapshotsService";
import { Pvci_creditsyncrunsService } from "../generated/services/Pvci_creditsyncrunsService";
import { Pvci_creditusagesService } from "../generated/services/Pvci_creditusagesService";
import { Pvci_credituserusagesService } from "../generated/services/Pvci_credituserusagesService";
import { Pvci_creditprivacysettingsService } from "../generated/services/Pvci_creditprivacysettingsService";
import { Pvci_transcriptsessionsService } from "../generated/services/Pvci_transcriptsessionsService";
import type { Pvci_agentinventories } from "../generated/models/Pvci_agentinventoriesModel";
import type { Pvci_creditcapacitysnapshots } from "../generated/models/Pvci_creditcapacitysnapshotsModel";
import type { Pvci_creditsyncruns } from "../generated/models/Pvci_creditsyncrunsModel";
import type { Pvci_creditusages } from "../generated/models/Pvci_creditusagesModel";
import type { Pvci_credituserusages } from "../generated/models/Pvci_credituserusagesModel";
import type { Pvci_creditprivacysettings } from "../generated/models/Pvci_creditprivacysettingsModel";
import type { SessionRow } from "../lib/model";

const USAGE_FIELDS = [
  "pvci_creditusageid", "pvci_usagedate", "pvci_environmentid", "pvci_resourceid",
  "pvci_agentname", "pvci_billedcredits", "pvci_nonbilledcredits", "pvci_featurename",
  "pvci_harness", "pvci_resolutionstatus", "pvci_sourceunit", "pvci_sourceapi", "pvci_users",
];

const CAPACITY_FIELDS = [
  "pvci_creditcapacitysnapshotid", "pvci_asofdate", "pvci_environmentid", "pvci_environmentname",
  "pvci_allocated", "pvci_consumed", "pvci_available", "pvci_status", "pvci_drawfromtenantpool",
  "pvci_alertenabled", "pvci_alertthreshold",
];

const AGENT_FIELDS = [
  "pvci_agentinventoryid", "pvci_resourceid", "pvci_displayname", "pvci_environmentid",
  "pvci_environmentname", "pvci_harness", "pvci_resourcetype", "pvci_classificationconfidence",
];

const SYNC_FIELDS = [
  "pvci_creditsyncrunid", "pvci_name", "pvci_source", "pvci_startedon", "pvci_completedon",
  "pvci_status", "pvci_sourcecount", "pvci_createdcount", "pvci_updatedcount", "pvci_rejectedcount",
];

const USER_USAGE_FIELDS = [
  "pvci_credituserusageid", "pvci_name", "pvci_userid", "pvci_userdisplayname",
  "pvci_usagedate", "pvci_billedcredits", "pvci_nonbilledcredits", "pvci_resources",
  "pvci_nameresolutionstatus",
];

const PRIVACY_FIELDS = [
  "pvci_creditprivacysettingid", "pvci_revealusernames", "pvci_approvalstatement",
  "pvci_approvedbyname", "pvci_approvedon", "pvci_revokedon",
];

const CORRELATION_SESSION_FIELDS = [
  "pvci_transcriptsessionid", "pvci_useraadobjectid", "pvci_userdisplayname",
  "pvci_botid", "pvci_botname", "pvci_environmentid", "pvci_startdatetimeutc",
  "pvci_messagecount", "pvci_userturncount", "pvci_toolcallcount", "pvci_toolerrorcount",
  "pvci_sessionoutcome", "pvci_istestmode",
];

type CreditMode = "total" | "billed" | "nonbilled";
type PeriodGrain = "day" | "week";

export function Credits({ sidebarTarget }: { sidebarTarget: HTMLElement | null }) {
  const [usage, setUsage] = useState<Pvci_creditusages[]>([]);
  const [capacity, setCapacity] = useState<Pvci_creditcapacitysnapshots[]>([]);
  const [agents, setAgents] = useState<Pvci_agentinventories[]>([]);
  const [syncRuns, setSyncRuns] = useState<Pvci_creditsyncruns[]>([]);
  const [userUsage, setUserUsage] = useState<Pvci_credituserusages[]>([]);
  const [privacy, setPrivacy] = useState<Pvci_creditprivacysettings | null>(null);
  const [correlationSessions, setCorrelationSessions] = useState<SessionRow[]>([]);
  const [privacyBusy, setPrivacyBusy] = useState(false);
  const [environment, setEnvironment] = useState("*");
  const [resource, setResource] = useState("*");
  const [selectedUser, setSelectedUser] = useState("*");
  const [navigatorSearch, setNavigatorSearch] = useState("");
  const [mode, setMode] = useState<CreditMode>("total");
  const [periodGrain, setPeriodGrain] = useState<PeriodGrain>("week");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [usageResult, capacityResult, agentResult, syncResult, userResult, privacyResult, sessionResult] = await Promise.all([
          Pvci_creditusagesService.getAll({ select: USAGE_FIELDS, orderBy: ["pvci_usagedate desc"], top: 500 }),
          Pvci_creditcapacitysnapshotsService.getAll({ select: CAPACITY_FIELDS, orderBy: ["pvci_asofdate desc"], top: 200 }),
          Pvci_agentinventoriesService.getAll({ select: AGENT_FIELDS, orderBy: ["pvci_displayname asc"], top: 500 }),
          Pvci_creditsyncrunsService.getAll({ select: SYNC_FIELDS, orderBy: ["pvci_startedon desc"], top: 50 }),
          Pvci_credituserusagesService.getAll({ select: USER_USAGE_FIELDS, orderBy: ["pvci_usagedate desc"], top: 500 }),
          Pvci_creditprivacysettingsService.getAll({ select: PRIVACY_FIELDS, filter: "pvci_settingkey eq 'credit-user-disclosure'", top: 1 }),
          Pvci_transcriptsessionsService.getAll({ select: CORRELATION_SESSION_FIELDS, orderBy: ["pvci_startdatetimeutc desc"], top: 500 }),
        ]);
        if (cancelled) return;
        setUsage((usageResult.data ?? []) as unknown as Pvci_creditusages[]);
        setCapacity((capacityResult.data ?? []) as unknown as Pvci_creditcapacitysnapshots[]);
        setAgents((agentResult.data ?? []) as unknown as Pvci_agentinventories[]);
        setSyncRuns((syncResult.data ?? []) as unknown as Pvci_creditsyncruns[]);
        setUserUsage((userResult.data ?? []) as unknown as Pvci_credituserusages[]);
        setPrivacy(((privacyResult.data ?? [])[0] ?? null) as unknown as Pvci_creditprivacysettings | null);
        setCorrelationSessions((sessionResult.data ?? []) as unknown as SessionRow[]);
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const environmentOptions = useMemo(() => {
    const options = new Map<string, string>();
    agents.forEach((agent) => {
      const id = agent.pvci_environmentid;
      if (id) options.set(id, agent.pvci_environmentname ?? id);
    });
    capacity.forEach((row) => {
      const id = row.pvci_environmentid;
      if (id) options.set(id, row.pvci_environmentname ?? id);
    });
    return [...options.entries()].sort((left, right) => left[1].localeCompare(right[1]));
  }, [agents, capacity]);
  const revealUserNames = privacy?.pvci_revealusernames === true;

  const environmentUsage = useMemo(
    () => usage.filter((row) => environment === "*" || row.pvci_environmentid === environment),
    [usage, environment]
  );
  const resourceSummaries = useMemo(() => {
    const summaries = new Map<string, { label: string; billed: number; nonbilled: number; facts: number }>();
    environmentUsage.forEach((row) => {
      const key = resourceKey(row);
      const current = summaries.get(key) ?? {
        label: row.pvci_agentname ?? row.pvci_resourceid ?? "Unknown resource",
        billed: 0,
        nonbilled: 0,
        facts: 0,
      };
      current.billed += row.pvci_billedcredits ?? 0;
      current.nonbilled += row.pvci_nonbilledcredits ?? 0;
      current.facts += 1;
      summaries.set(key, current);
    });
    return [...summaries.entries()].sort((left, right) =>
      (right[1].billed + right[1].nonbilled) - (left[1].billed + left[1].nonbilled)
    );
  }, [environmentUsage]);
  const scopedUsage = useMemo(
    () => environmentUsage.filter((row) => resource === "*" || resourceKey(row) === resource),
    [environmentUsage, resource]
  );
  const scopedCapacity = useMemo(
    () => capacity.filter((row) => environment === "*" || row.pvci_environmentid === environment),
    [capacity, environment]
  );
  const userSummaries = useMemo(() => {
    const summaries = new Map<string, { label: string; billed: number; nonbilled: number; facts: number; status: string }>();
    userUsage.forEach((row) => {
      const key = row.pvci_userid ?? "unknown";
      const current = summaries.get(key) ?? {
        label: privacy?.pvci_revealusernames ? row.pvci_userdisplayname ?? key : key,
        billed: 0,
        nonbilled: 0,
        facts: 0,
        status: row.pvci_nameresolutionstatus ?? "unknown",
      };
      current.billed += row.pvci_billedcredits ?? 0;
      current.nonbilled += row.pvci_nonbilledcredits ?? 0;
      current.facts += 1;
      summaries.set(key, current);
    });
    return [...summaries.entries()].sort((left, right) =>
      (right[1].billed + right[1].nonbilled) - (left[1].billed + left[1].nonbilled)
    );
  }, [userUsage, privacy?.pvci_revealusernames]);
  const visibleResourceSummaries = useMemo(() => {
    const query = navigatorSearch.trim().toLowerCase();
    return query
      ? resourceSummaries.filter(([key, summary]) => `${summary.label} ${key}`.toLowerCase().includes(query))
      : resourceSummaries;
  }, [resourceSummaries, navigatorSearch]);
  const visibleUserSummaries = useMemo(() => {
    const query = navigatorSearch.trim().toLowerCase();
    return query
      ? userSummaries.filter(([key, summary]) => `${summary.label} ${key}`.toLowerCase().includes(query))
      : userSummaries;
  }, [userSummaries, navigatorSearch]);
  const scopedUserUsage = useMemo(
    () => userUsage.filter((row) => selectedUser === "*" || (row.pvci_userid ?? "unknown") === selectedUser),
    [userUsage, selectedUser]
  );
  const selectedResourceLabel = resource === "*"
    ? null
    : resourceSummaries.find(([key]) => key === resource)?.[1].label ?? resource;
  const selectedUserLabel = selectedUser === "*"
    ? null
    : userSummaries.find(([key]) => key === selectedUser)?.[1].label ?? selectedUser;
  const environmentSessions = useMemo(
    () => correlationSessions.filter((session) => environment === "*" || session.pvci_environmentid === environment),
    [correlationSessions, environment]
  );
  const agentSessions = useMemo(
    () => resource === "*"
      ? environmentSessions
      : environmentSessions.filter((session) => sessionMatchesResource(session, resource, selectedResourceLabel)),
    [environmentSessions, resource, selectedResourceLabel]
  );
  const userSessions = useMemo(
    () => selectedUser === "*"
      ? environmentSessions
      : environmentSessions.filter((session) => sameId(session.pvci_useraadobjectid, selectedUser)),
    [environmentSessions, selectedUser]
  );
  const combinationSessions = useMemo(
    () => agentSessions.filter((session) => selectedUser === "*" || sameId(session.pvci_useraadobjectid, selectedUser)),
    [agentSessions, selectedUser]
  );
  const usersForAgent = useMemo(
    () => groupSessions(agentSessions, (session) => {
      const id = session.pvci_useraadobjectid ?? "Unknown user";
      return revealUserNames ? session.pvci_userdisplayname ?? id : id;
    }),
    [agentSessions, revealUserNames]
  );
  const agentsForUser = useMemo(
    () => groupSessions(userSessions, (session) => session.pvci_botname ?? session.pvci_botid ?? "Unknown agent"),
    [userSessions]
  );
  const userCreditsForAgent = useMemo(() => {
    const relatedIds = new Set(agentSessions.map((session) => session.pvci_useraadobjectid?.toLowerCase()).filter(Boolean));
    return userSummaries
      .filter(([key]) => relatedIds.has(key.toLowerCase()))
      .map(([, summary]) => ({ label: summary.label, value: summary.billed + summary.nonbilled }))
      .sort((left, right) => right.value - left.value);
  }, [agentSessions, userSummaries]);
  const agentCreditsForUser = useMemo(() => {
    const related = new Set<string>();
    userSessions.forEach((session) => {
      if (session.pvci_botid) related.add(session.pvci_botid.toLowerCase());
      if (session.pvci_botname) related.add(session.pvci_botname.toLowerCase());
    });
    return resourceSummaries
      .filter(([key, summary]) => related.has(key.toLowerCase()) || related.has(summary.label.toLowerCase()))
      .map(([, summary]) => ({ label: summary.label, value: summary.billed + summary.nonbilled }))
      .sort((left, right) => right.value - left.value);
  }, [userSessions, resourceSummaries]);
  const userCreditTrend = useMemo(
    () => aggregateSplitCreditPeriods(scopedUserUsage, periodGrain),
    [scopedUserUsage, periodGrain]
  );
  const combinationByPeriod = useMemo(
    () => groupSessionsByPeriod(combinationSessions, periodGrain),
    [combinationSessions, periodGrain]
  );
  const relationshipKpis = useMemo(() => ({
    sessions: combinationSessions.length,
    messages: combinationSessions.reduce((total, row) => total + (row.pvci_messagecount ?? 0), 0),
    userTurns: combinationSessions.reduce((total, row) => total + (row.pvci_userturncount ?? 0), 0),
    tools: combinationSessions.reduce((total, row) => total + (row.pvci_toolcallcount ?? 0), 0),
    toolErrors: combinationSessions.reduce((total, row) => total + (row.pvci_toolerrorcount ?? 0), 0),
    resolved: combinationSessions.filter((row) => row.pvci_sessionoutcome === "Resolved").length,
    reportedUsers: maxSourceCount(scopedUsage.map((row) => row.pvci_users)),
    reportedResources: maxSourceCount(scopedUserUsage.map((row) => row.pvci_resources)),
  }), [combinationSessions, scopedUsage, scopedUserUsage]);

  const globalTotals = useMemo(() => {
    const billed = sum(environmentUsage, "pvci_billedcredits");
    const nonbilled = sum(environmentUsage, "pvci_nonbilledcredits");
    return {
      billed,
      nonbilled,
      total: billed + nonbilled,
      unresolved: environmentUsage.filter((row) => row.pvci_resolutionstatus !== "exact").length,
      unknownHarness: environmentUsage.filter((row) => !row.pvci_harness || row.pvci_harness === "unknown").length,
    };
  }, [environmentUsage]);
  const scopedTotals = useMemo(() => {
    const billed = sum(scopedUsage, "pvci_billedcredits");
    const nonbilled = sum(scopedUsage, "pvci_nonbilledcredits");
    return {
      billed,
      nonbilled,
      total: billed + nonbilled,
      unresolved: scopedUsage.filter((row) => row.pvci_resolutionstatus !== "exact").length,
      unknownHarness: scopedUsage.filter((row) => !row.pvci_harness || row.pvci_harness === "unknown").length,
    };
  }, [scopedUsage]);

  const globalByResource = useMemo(
    () => aggregate(environmentUsage, (row) => row.pvci_agentname ?? row.pvci_resourceid ?? "Unknown resource", (row) => creditValue(row, mode)).slice(0, 12),
    [environmentUsage, mode]
  );
  const globalByFeature = useMemo(
    () => aggregate(environmentUsage, (row) => row.pvci_featurename ?? "Unknown feature", (row) => creditValue(row, mode)),
    [environmentUsage, mode]
  );
  const globalByPeriod = useMemo(
    () => aggregatePeriods(environmentUsage, periodGrain, (row) => creditValue(row, mode)),
    [environmentUsage, mode, periodGrain]
  );
  const agentCreditTrend = useMemo(
    () => aggregateSplitCreditPeriods(scopedUsage, periodGrain),
    [scopedUsage, periodGrain]
  );

  const latestSync = syncRuns[0];
  const latestUsageDate = environmentUsage.reduce<string | undefined>(
    (latest, row) => !latest || (row.pvci_usagedate ?? "") > latest ? row.pvci_usagedate : latest,
    undefined
  );
  const globalScopeLabel = environment === "*"
    ? "All environments"
    : environmentOptions.find(([id]) => id === environment)?.[1] ?? environment;
  const hasScopedSelection = resource !== "*" || selectedUser !== "*";

  const setUserNameDisclosure = async (reveal: boolean) => {
    if (!privacy || privacyBusy) return;
    const approved = window.confirm(
      reveal
        ? "Reveal end-user names for all authorized users of both reporting apps? This shared approval is audited and resolves stored source IDs against Dataverse users."
        : "Revoke user-name disclosure? Resolved names, UPNs, and linked Dataverse user IDs will be removed from all stored credit user facts."
    );
    if (!approved) return;
    setPrivacyBusy(true);
    setError(null);
    try {
      await Pvci_creditprivacysettingsService.update(privacy.pvci_creditprivacysettingid, {
        pvci_revealusernames: reveal,
      });
      const [userResult, privacyResult] = await Promise.all([
        Pvci_credituserusagesService.getAll({ select: USER_USAGE_FIELDS, orderBy: ["pvci_usagedate desc"], top: 500 }),
        Pvci_creditprivacysettingsService.get(privacy.pvci_creditprivacysettingid, { select: PRIVACY_FIELDS }),
      ]);
      setUserUsage((userResult.data ?? []) as unknown as Pvci_credituserusages[]);
      setPrivacy((privacyResult.data ?? null) as unknown as Pvci_creditprivacysettings | null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPrivacyBusy(false);
    }
  };

  if (loading) return <div className="muted pad">Loading credit reporting…</div>;
  if (error) return <div className="error">{error}</div>;

  const sidebar = sidebarTarget ? createPortal(
    <>
      <input
        className="search"
        placeholder="Search agents and users…"
        value={navigatorSearch}
        onChange={(event) => setNavigatorSearch(event.target.value)}
      />
      <select className="search" value={environment} onChange={(event) => { setEnvironment(event.target.value); setResource("*"); }}>
        <option value="*">All environments</option>
        {environmentOptions.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </select>

      <div className="credit-nav-heading">
        <span>Agents and resources</span>
        <span>{resourceSummaries.length}</span>
      </div>
      <div className="credit-nav-list agent-nav-list">
        <button className={`session-item credit-nav-item${resource === "*" ? " active" : ""}`} onClick={() => setResource("*")}>
          <div className="si-top"><span className="si-user">All agents and resources</span></div>
          <div className="si-sub muted small">{environmentUsage.length} usage facts</div>
        </button>
        {visibleResourceSummaries.map(([key, summary]) => (
          <button key={key} className={`session-item credit-nav-item${resource === key ? " active" : ""}`} onClick={() => setResource(key)}>
            <div className="si-top">
              <span className="si-user" title={summary.label}>{summary.label}</span>
              <span className="chip">{fmtCredits(summary.billed + summary.nonbilled)}</span>
            </div>
            <div className="si-sub muted small">{fmtFacts(summary.facts)} · {fmtCredits(summary.billed)} billed</div>
          </button>
        ))}
      </div>

      <div className="credit-nav-heading">
        <span>Users</span>
        <span>{userSummaries.length}</span>
      </div>
      <div className="credit-nav-list user-nav-list">
        <button className={`session-item credit-nav-item${selectedUser === "*" ? " active" : ""}`} onClick={() => setSelectedUser("*")}>
          <div className="si-top"><span className="si-user">All users</span></div>
          <div className="si-sub muted small">{userUsage.length} source-period facts</div>
        </button>
        {visibleUserSummaries.map(([key, summary]) => (
          <button key={key} className={`session-item credit-nav-item${selectedUser === key ? " active" : ""}`} onClick={() => setSelectedUser(key)}>
            <div className="si-top">
              <span className={`si-user${revealUserNames ? "" : " mono"}`} title={summary.label}>{summary.label}</span>
              <span className="chip">{fmtCredits(summary.billed + summary.nonbilled)}</span>
            </div>
            <div className="si-sub muted small">{fmtFacts(summary.facts)} · {summary.status}</div>
          </button>
        ))}
      </div>
    </>,
    sidebarTarget
  ) : null;

  return (
    <div className="credits">
      {sidebar}
      <div className="credit-title">
        <div>
          <h2>Copilot credit reporting</h2>
          <p>Actual PPAC billed and non-billed aggregates, persisted in Dataverse.</p>
        </div>
        <div className="freshness">
          <span>Usage through <strong>{fmtDate(latestUsageDate)}</strong></span>
          <span>Last sync <strong>{fmtDateTime(latestSync?.pvci_completedon)}</strong></span>
        </div>
      </div>

      <section className="report-band global-report">
        <div className="report-heading">
          <div>
            <span className="report-eyebrow">Global overview</span>
            <h3 className="heading-with-help">
              {globalScopeLabel}
              <HelpTip text="Tenant or environment-wide PPAC resource consumption. Agent and user selections do not change these totals." />
            </h3>
            <p>All PPAC resource facts in scope; agent and user selections do not change this band.</p>
          </div>
          <div className="credit-filters">
            <div className="segmented" aria-label="Credit value mode">
              {(["total", "billed", "nonbilled"] as const).map((option) => (
                <button key={option} className={mode === option ? "on" : ""} onClick={() => setMode(option)}>
                  {option === "nonbilled" ? "Non-billed" : title(option)}
                </button>
              ))}
            </div>
            <div className="segmented" aria-label="Source period grouping">
              {(["day", "week"] as const).map((option) => (
                <button key={option} className={periodGrain === option ? "on" : ""} onClick={() => setPeriodGrain(option)}>
                  {title(option)}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="kpis credit-kpis global-kpis">
          <CreditKpi label="Billed" value={fmtCredits(globalTotals.billed)} tone="bad" />
          <CreditKpi label="Non-billed" value={fmtCredits(globalTotals.nonbilled)} tone="good" />
          <CreditKpi label="Total activity" value={fmtCredits(globalTotals.total)} />
          <CreditKpi label="Usage facts" value={String(environmentUsage.length)} />
          <CreditKpi label="Unresolved resources" value={String(globalTotals.unresolved)} tone={globalTotals.unresolved ? "warn" : undefined} />
          <CreditKpi label="Unknown harness" value={String(globalTotals.unknownHarness)} tone={globalTotals.unknownHarness ? "warn" : undefined} />
        </div>

        <div className="global-chart-grid">
          <div className="global-period-chart">
            <SectionHeading text={`Activity by source ${periodGrain}`} help="Total selected credit mode grouped by the as-of dates returned by PPAC. These are source-period aggregates, not individual billing events." />
            <HBar rows={globalByPeriod} unit="credits" />
          </div>
          <div>
            <SectionHeading text={`Top resources · ${mode === "total" ? "all activity" : mode === "billed" ? "billed" : "non-billed"}`} help="Highest-consuming PPAC resources in the current global environment scope." />
            <HBar rows={globalByResource} unit="credits" />
          </div>
          <div>
            <SectionHeading text="Feature mix" help="Credit contribution by PPAC feature dimension. Aggregate rows remain labeled as aggregate when no finer feature was supplied." />
            <HBar rows={globalByFeature} unit="credits" />
          </div>
        </div>

        <div className="source-note">
          Source-period aggregates, not billing events. Day/week grouping uses returned as-of dates; unresolved harness and session attribution remain visible rather than inferred.
        </div>
      </section>

      <section className={`report-band scoped-report${hasScopedSelection ? " has-selection" : ""}`}>
        <div className="report-heading scoped-heading">
          <div>
            <span className="report-eyebrow">Scoped analysis</span>
            <h3 className="heading-with-help">
              {hasScopedSelection ? `${selectedUserLabel ?? "All users"} · ${selectedResourceLabel ?? "All agents and resources"}` : "Choose an agent or user"}
              <HelpTip text="Focused report for the selected user, billing resource, or both. Credit projections stay separate from transcript correlations." />
            </h3>
            <p>Selection-specific credit trends and transcript-correlated operating signals.</p>
          </div>
          {hasScopedSelection && <span className="conf multiple">Correlated, not allocated</span>}
        </div>

        {!hasScopedSelection ? (
          <div className="scope-empty">Select an agent/resource or user in the left navigator to open a focused report.</div>
        ) : (
          <>
          <div className="selection-analysis">
          <div className="selection-title selection-title-compact">
            <div>
              <SectionHeading text="Evidence boundary" help="Explains which selected metrics are authoritative PPAC facts and which are transcript correlations. Correlated activity is never presented as allocated credits." />
            </div>
          </div>
          <div className="selection-note">
            PPAC exposes user and resource credits as separate aggregate projections. The two credit trends below remain authoritative separately; transcript relationships show observed usage but do not assign user credits to an agent.
          </div>
          {resource !== "*" && agentSessions.length === 0 && (
            <div className="selection-gap">
              This PPAC billing resource does not exactly match a transcript bot ID or name. PPAC reports a user count, but not the user identities for this resource, so no user-agent session relationship is inferred.
            </div>
          )}

          <div className="kpis selection-kpis">
            {resource !== "*" && <CreditKpi label="Agent credits" value={fmtCredits(scopedTotals.total)} />}
            {selectedUser !== "*" && <CreditKpi label="User credits" value={fmtCredits(sumUserCredits(scopedUserUsage))} />}
            <CreditKpi label="Matched sessions" value={String(relationshipKpis.sessions)} />
            <CreditKpi label="Messages" value={String(relationshipKpis.messages)} />
            <CreditKpi label="User turns" value={String(relationshipKpis.userTurns)} />
            <CreditKpi label="Tool calls" value={String(relationshipKpis.tools)} tone={relationshipKpis.toolErrors ? "warn" : undefined} />
            <CreditKpi label="Resolved" value={`${relationshipKpis.resolved} / ${relationshipKpis.sessions}`} />
            {resource !== "*" && <CreditKpi label="PPAC reported users" value={fmtOptionalCount(relationshipKpis.reportedUsers)} />}
            {selectedUser !== "*" && <CreditKpi label="PPAC reported resources" value={fmtOptionalCount(relationshipKpis.reportedResources)} />}
          </div>

          <div className="selection-grid">
            {resource !== "*" && (
              <div>
                <SectionHeading text="Agent credit trend" help="Authoritative PPAC resource credits by source period, split into billed and non-billed lanes on one shared scale." />
                <CreditTrend rows={agentCreditTrend} />
              </div>
            )}
            {selectedUser !== "*" && (
              <div>
                <SectionHeading text="User credit trend" help="Authoritative PPAC user credits by source period, split into billed and non-billed lanes. These values are not assigned to the selected agent." />
                <CreditTrend rows={userCreditTrend} />
              </div>
            )}
            {resource !== "*" && (
              <div>
                <SectionHeading text="Users observed with this resource · sessions" help="Distinct user labels and session counts from exact transcript user/bot relationships, available only when the billing resource matches a transcript bot." />
                <HBar rows={usersForAgent} unit="sessions" />
              </div>
            )}
            {selectedUser !== "*" && (
              <div>
                <SectionHeading text="Agents observed for this user · sessions" help="Agents seen in this user's stored transcripts and the number of matching sessions. This is operational correlation, not billing allocation." />
                <HBar rows={agentsForUser} unit="sessions" />
              </div>
            )}
            {resource !== "*" && (
              <div>
                <SectionHeading text="Related users · total credits across all agents" help="Each observed user's full PPAC credit total across all agents. It is context for the relationship, not this resource's attributed charge." />
                <HBar rows={userCreditsForAgent} unit="credits" />
              </div>
            )}
            {selectedUser !== "*" && (
              <div>
                <SectionHeading text="Related agents · total credits across all users" help="Each observed agent resource's full PPAC credit total across all users. It is not the selected user's allocated charge." />
                <HBar rows={agentCreditsForUser} unit="credits" />
              </div>
            )}
            {resource !== "*" && selectedUser !== "*" && (
              <div className="combination-trend">
                <SectionHeading text="User + agent session trend" help="Stored transcript sessions over time where the selected user and transcript bot both match. Current PPAC reads do not expose pair-level credits." />
                <HBar rows={combinationByPeriod} unit="sessions" />
              </div>
            )}
          </div>
          </div>

          {selectedUser !== "*" && (
            <div className="scoped-user-detail">
              <div className="user-credit-head">
                <div>
                  <h4 className="heading-with-help">{selectedUserLabel}<HelpTip text="Raw PPAC user source-period rows for the selected user, kept separate from resource totals to avoid double-counting." /></h4>
                  <span className={`conf ${revealUserNames ? "high" : "multiple"}`}>
                    {revealUserNames ? "Names approved" : "GUID only"}
                  </span>
                </div>
              </div>
              <div className="credit-table-wrap">
                <table className="runtable credit-table user-credit-table">
                  <thead><tr><th>User</th><th>As of</th><th>Billed</th><th>Non-billed</th><th>Identity status</th><th>Resources</th></tr></thead>
                  <tbody>
                    {scopedUserUsage.map((row) => (
                      <tr key={row.pvci_credituserusageid}>
                        <td className={revealUserNames ? "" : "mono"}>
                          {revealUserNames ? row.pvci_userdisplayname ?? row.pvci_userid ?? "Unknown" : row.pvci_userid ?? "Unknown"}
                        </td>
                        <td>{fmtDate(row.pvci_usagedate)}</td>
                        <td className="mono">{fmtCredits(row.pvci_billedcredits ?? 0)}</td>
                        <td className="mono">{fmtCredits(row.pvci_nonbilledcredits ?? 0)}</td>
                        <td>{row.pvci_nameresolutionstatus ?? "unknown"}</td>
                        <td className="user-resources" title={row.pvci_resources}>{summarizeResources(row.pvci_resources)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          </>
        )}
      </section>

      <section className="report-band operations-report">
        <div className="report-heading">
          <div>
            <span className="report-eyebrow">Operations</span>
            <h3 className="heading-with-help">Capacity, privacy, and collector health<HelpTip text="Administrative status for available capacity, shared user-name disclosure, and scheduled collector freshness." /></h3>
            <p>Administrative context for the reporting data.</p>
          </div>
        </div>

        <SectionHeading text="Environment capacity" help="Latest PPAC capacity snapshots by environment, including allocation, consumption, availability, pool policy, and status." className="report-subheading" />
        <div className="credit-table-wrap">
        <table className="runtable credit-table">
          <thead><tr><th>Environment</th><th>As of</th><th>Allocated</th><th>Consumed</th><th>Available</th><th>Policy</th><th>Status</th></tr></thead>
          <tbody>
            {scopedCapacity.map((row) => (
              <tr key={row.pvci_creditcapacitysnapshotid}>
                <td>{row.pvci_environmentname ?? row.pvci_environmentid ?? "Unknown"}</td>
                <td>{fmtDate(row.pvci_asofdate)}</td>
                <td className="mono">{fmtCredits(row.pvci_allocated ?? 0)}</td>
                <td className="mono">{fmtCredits(row.pvci_consumed ?? 0)}</td>
                <td className="mono">{fmtCredits(row.pvci_available ?? 0)}</td>
                <td>{row.pvci_drawfromtenantpool ? "Tenant pool" : "Allocated"}</td>
                <td><span className={`conf ${row.pvci_status === "WithinCapacity" ? "high" : "multiple"}`}>{row.pvci_status ?? "Unknown"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>

        <div className="privacy-operations">
      <div className="user-credit-head">
        <div>
          <h4 className="heading-with-help">User name privacy<HelpTip text="Shared audited approval controlling whether user GUIDs are resolved to Dataverse display names in both reporting apps." /></h4>
          <span className={`conf ${revealUserNames ? "high" : "multiple"}`}>
            {revealUserNames ? "Names approved" : "GUID only"}
          </span>
        </div>
        {privacy && (
          <button
            type="button"
            className={revealUserNames ? "privacy-action revoke" : "privacy-action"}
            disabled={privacyBusy}
            onClick={() => void setUserNameDisclosure(!revealUserNames)}
          >
            {privacyBusy ? "Applying…" : revealUserNames ? "Revoke name access" : "Reveal user names"}
          </button>
        )}
      </div>
      <div className="privacy-statement">
        {privacy?.pvci_approvalstatement ?? "User names remain hidden until the shared Dataverse approval is enabled."}
        {revealUserNames && privacy?.pvci_approvedbyname && (
          <span> Approved by {privacy.pvci_approvedbyname} on {fmtDateTime(privacy.pvci_approvedon)}.</span>
        )}
      </div>
        </div>

      <SectionHeading text="Sync health" help="Most recent scheduled credit collector result, including imported source rows and rejected records." className="report-subheading" />
      <div className="sync-strip">
        <span>{latestSync?.pvci_name ?? "No sync run"}</span>
        <span className={`conf ${latestSync?.pvci_status === "success" ? "high" : "multiple"}`}>{latestSync?.pvci_status ?? "unknown"}</span>
        <span>{latestSync?.pvci_sourcecount ?? 0} source rows</span>
        <span>{latestSync?.pvci_rejectedcount ?? 0} rejected</span>
      </div>
      </section>
    </div>
  );
}

function CreditKpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <div className="kpi"><div className="kpi-label">{label}</div><div className={`kpi-value ${tone ?? ""}`}>{value}</div></div>;
}

function sum(rows: Pvci_creditusages[], field: "pvci_billedcredits" | "pvci_nonbilledcredits") {
  return rows.reduce((total, row) => total + (row[field] ?? 0), 0);
}

function creditValue(row: Pvci_creditusages, mode: CreditMode) {
  if (mode === "billed") return row.pvci_billedcredits ?? 0;
  if (mode === "nonbilled") return row.pvci_nonbilledcredits ?? 0;
  return (row.pvci_billedcredits ?? 0) + (row.pvci_nonbilledcredits ?? 0);
}

function aggregate(rows: Pvci_creditusages[], label: (row: Pvci_creditusages) => string, value: (row: Pvci_creditusages) => number) {
  const values = new Map<string, number>();
  rows.forEach((row) => values.set(label(row), (values.get(label(row)) ?? 0) + value(row)));
  return [...values.entries()].sort((left, right) => right[1] - left[1]).map(([name, amount]) => ({ label: name, value: amount }));
}

function aggregatePeriods(rows: Pvci_creditusages[], grain: PeriodGrain, value: (row: Pvci_creditusages) => number) {
  const values = new Map<string, number>();
  rows.forEach((row) => {
    const key = periodKey(row.pvci_usagedate, grain);
    values.set(key, (values.get(key) ?? 0) + value(row));
  });
  return [...values.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([label, amount]) => ({ label, value: amount }));
}

function aggregateSplitCreditPeriods(
  rows: Array<{ pvci_usagedate?: string; pvci_billedcredits?: number; pvci_nonbilledcredits?: number }>,
  grain: PeriodGrain
) {
  const values = new Map<string, { billed: number; nonbilled: number }>();
  rows.forEach((row) => {
    const key = periodKey(row.pvci_usagedate, grain);
    const current = values.get(key) ?? { billed: 0, nonbilled: 0 };
    current.billed += row.pvci_billedcredits ?? 0;
    current.nonbilled += row.pvci_nonbilledcredits ?? 0;
    values.set(key, current);
  });
  return [...values.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([label, value]) => ({ label, ...value }));
}

function sumUserCredits(rows: Pvci_credituserusages[]) {
  return rows.reduce((total, row) => total + (row.pvci_billedcredits ?? 0) + (row.pvci_nonbilledcredits ?? 0), 0);
}

function sameId(left?: string, right?: string) {
  return Boolean(left && right && left.toLowerCase() === right.toLowerCase());
}

function sessionMatchesResource(session: SessionRow, resourceId: string, resourceLabel: string | null) {
  if (sameId(session.pvci_botid, resourceId)) return true;
  return Boolean(resourceLabel && session.pvci_botname?.toLowerCase() === resourceLabel.toLowerCase());
}

function groupSessions(rows: SessionRow[], label: (row: SessionRow) => string) {
  const values = new Map<string, number>();
  rows.forEach((row) => values.set(label(row), (values.get(label(row)) ?? 0) + 1));
  return [...values.entries()].sort((left, right) => right[1] - left[1]).map(([name, value]) => ({ label: name, value }));
}

function groupSessionsByPeriod(rows: SessionRow[], grain: PeriodGrain) {
  const values = new Map<string, number>();
  rows.forEach((row) => {
    const key = periodKey(row.pvci_startdatetimeutc, grain);
    values.set(key, (values.get(key) ?? 0) + 1);
  });
  return [...values.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([label, value]) => ({ label, value }));
}

function resourceKey(row: Pvci_creditusages) {
  return row.pvci_resourceid ?? row.pvci_agentname ?? "unknown";
}

function periodKey(value: string | undefined, grain: PeriodGrain) {
  if (!value) return "Unknown period";
  const day = new Date(value);
  if (Number.isNaN(day.valueOf())) return value.slice(0, 10);
  if (grain === "day") return day.toISOString().slice(0, 10);
  const weekday = day.getUTCDay() || 7;
  day.setUTCDate(day.getUTCDate() - weekday + 1);
  return `Week of ${day.toISOString().slice(0, 10)}`;
}

function fmtCredits(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function fmtFacts(value: number) {
  return `${value} ${value === 1 ? "fact" : "facts"}`;
}

function fmtDate(value?: string) {
  return value ? value.slice(0, 10) : "—";
}

function fmtDateTime(value?: string) {
  return value ? value.replace("T", " ").slice(0, 16) : "—";
}

function title(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function summarizeResources(value?: string) {
  if (!value) return "—";
  try {
    const parsed = JSON.parse(value);
    if (Array.isArray(parsed)) return `${parsed.length} resource${parsed.length === 1 ? "" : "s"}`;
  } catch {
    // Preserve an opaque source value without exposing more detail in the grid.
  }
  return "Available";
}

function maxSourceCount(values: Array<string | undefined>) {
  const counts = values.map(parseSourceCount).filter((value): value is number => value !== null);
  return counts.length ? Math.max(...counts) : null;
}

function parseSourceCount(value?: string) {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value);
    return typeof parsed === "number" && Number.isFinite(parsed) ? parsed : Array.isArray(parsed) ? parsed.length : null;
  } catch {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
}

function fmtOptionalCount(value: number | null) {
  return value === null ? "—" : value.toLocaleString();
}

function SectionHeading({ text, help, className = "" }: { text: string; help: string; className?: string }) {
  return <h4 className={`heading-with-help ${className}`.trim()}>{text}<HelpTip text={help} /></h4>;
}

function HelpTip({ text }: { text: string }) {
  return (
    <span className="report-help" tabIndex={0} aria-label={text}>
      <span aria-hidden="true">?</span>
      <span className="report-help-card" role="tooltip">{text}</span>
    </span>
  );
}