import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { CreditTrend, HBar } from "./Chart";
import { Pvci_agentinventoriesService } from "../generated/services/Pvci_agentinventoriesService";
import { Pvci_agentthresholdsnapshotsService } from "../generated/services/Pvci_agentthresholdsnapshotsService";
import { Pvci_creditcapacitysnapshotsService } from "../generated/services/Pvci_creditcapacitysnapshotsService";
import { Pvci_creditsyncrunsService } from "../generated/services/Pvci_creditsyncrunsService";
import { Pvci_creditusagesService } from "../generated/services/Pvci_creditusagesService";
import { Pvci_credituserusagesService } from "../generated/services/Pvci_credituserusagesService";
import { Pvci_creditprivacysettingsService } from "../generated/services/Pvci_creditprivacysettingsService";
import { Pvci_environmentinventoriesService } from "../generated/services/Pvci_environmentinventoriesService";
import { Pvci_governancesyncrunsService } from "../generated/services/Pvci_governancesyncrunsService";
import { Pvci_inventorysyncrunsService } from "../generated/services/Pvci_inventorysyncrunsService";
import { Pvci_transcriptsessionsService } from "../generated/services/Pvci_transcriptsessionsService";
import type { Pvci_agentinventories } from "../generated/models/Pvci_agentinventoriesModel";
import type { Pvci_agentthresholdsnapshots } from "../generated/models/Pvci_agentthresholdsnapshotsModel";
import type { Pvci_creditcapacitysnapshots } from "../generated/models/Pvci_creditcapacitysnapshotsModel";
import type { Pvci_creditsyncruns } from "../generated/models/Pvci_creditsyncrunsModel";
import type { Pvci_creditusages } from "../generated/models/Pvci_creditusagesModel";
import type { Pvci_credituserusages } from "../generated/models/Pvci_credituserusagesModel";
import type { Pvci_creditprivacysettings } from "../generated/models/Pvci_creditprivacysettingsModel";
import type { Pvci_environmentinventories } from "../generated/models/Pvci_environmentinventoriesModel";
import type { Pvci_governancesyncruns } from "../generated/models/Pvci_governancesyncrunsModel";
import type { Pvci_inventorysyncruns } from "../generated/models/Pvci_inventorysyncrunsModel";
import type { SessionRow } from "../lib/model";
import { loadAllPages } from "../lib/paging";

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
  "pvci_agentstatus", "pvci_hasdetailedaccess", "pvci_inventorysource",
];

const THRESHOLD_FIELDS = [
  "pvci_agentthresholdsnapshotid", "pvci_environmentid", "pvci_resourceid", "pvci_entitlementid",
  "pvci_limit", "pvci_resourceconsumption", "pvci_notificationthreshold", "pvci_notifyifovercapacity",
  "pvci_stopifovercapacity", "pvci_stopresource", "pvci_capturedon", "_pvci_agentid_value",
];

const GOVERNANCE_SYNC_FIELDS = [
  "pvci_governancesyncrunid", "pvci_name", "pvci_status", "pvci_startedon", "pvci_completedon",
  "pvci_thresholdcount", "pvci_createdcount", "pvci_updatedcount", "pvci_rejectedcount",
];

const ENVIRONMENT_FIELDS = [
  "pvci_environmentinventoryid", "pvci_environmentid", "pvci_displayname", "pvci_environmenturl",
  "pvci_environmenttype", "pvci_geo", "pvci_state", "pvci_ismanaged", "pvci_hasdataverse",
  "pvci_hasdetailedaccess", "pvci_lastsyncedon",
];

const INVENTORY_SYNC_FIELDS = [
  "pvci_inventorysyncrunid", "pvci_name", "pvci_source", "pvci_startedon", "pvci_completedon",
  "pvci_status", "pvci_environmentcount", "pvci_agentcount", "pvci_createdcount",
  "pvci_updatedcount", "pvci_rejectedcount",
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
type HarnessFilter = "*" | "github_copilot" | "not_github_copilot" | "unknown";
type ResourceSummary = {
  label: string;
  resourceId: string;
  environmentId?: string;
  harness: Exclude<HarnessFilter, "*">;
  threshold?: Pvci_agentthresholdsnapshots;
  billed: number;
  nonbilled: number;
  facts: number;
};

export function Credits({ sidebarTarget }: { sidebarTarget: HTMLElement | null }) {
  const [usage, setUsage] = useState<Pvci_creditusages[]>([]);
  const [capacity, setCapacity] = useState<Pvci_creditcapacitysnapshots[]>([]);
  const [agents, setAgents] = useState<Pvci_agentinventories[]>([]);
  const [thresholds, setThresholds] = useState<Pvci_agentthresholdsnapshots[]>([]);
  const [governanceSyncRuns, setGovernanceSyncRuns] = useState<Pvci_governancesyncruns[]>([]);
  const [environments, setEnvironments] = useState<Pvci_environmentinventories[]>([]);
  const [inventorySyncRuns, setInventorySyncRuns] = useState<Pvci_inventorysyncruns[]>([]);
  const [syncRuns, setSyncRuns] = useState<Pvci_creditsyncruns[]>([]);
  const [userUsage, setUserUsage] = useState<Pvci_credituserusages[]>([]);
  const [privacy, setPrivacy] = useState<Pvci_creditprivacysettings | null>(null);
  const [correlationSessions, setCorrelationSessions] = useState<SessionRow[]>([]);
  const [privacyBusy, setPrivacyBusy] = useState(false);
  const [environment, setEnvironment] = useState("*");
  const [harness, setHarness] = useState<HarnessFilter>("*");
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
        const [usageResult, capacityResult, agentResult, thresholdResult, governanceSyncResult, environmentResult, inventorySyncResult, syncResult, userResult, privacyResult, sessionResult] = await Promise.all([
          loadAllPages((skipToken, maxPageSize) => Pvci_creditusagesService.getAll({ select: USAGE_FIELDS, orderBy: ["pvci_usagedate desc"], maxPageSize, skipToken })),
          loadAllPages((skipToken, maxPageSize) => Pvci_creditcapacitysnapshotsService.getAll({ select: CAPACITY_FIELDS, orderBy: ["pvci_asofdate desc"], maxPageSize, skipToken })),
          loadAllPages((skipToken, maxPageSize) => Pvci_agentinventoriesService.getAll({ select: AGENT_FIELDS, orderBy: ["pvci_displayname asc"], maxPageSize, skipToken })),
          loadAllPages((skipToken, maxPageSize) => Pvci_agentthresholdsnapshotsService.getAll({ select: THRESHOLD_FIELDS, orderBy: ["pvci_capturedon desc"], maxPageSize, skipToken })),
          Pvci_governancesyncrunsService.getAll({ select: GOVERNANCE_SYNC_FIELDS, orderBy: ["pvci_startedon desc"], top: 50 }),
          loadAllPages((skipToken, maxPageSize) => Pvci_environmentinventoriesService.getAll({ select: ENVIRONMENT_FIELDS, orderBy: ["pvci_displayname asc"], maxPageSize, skipToken })),
          Pvci_inventorysyncrunsService.getAll({ select: INVENTORY_SYNC_FIELDS, orderBy: ["pvci_startedon desc"], top: 50 }),
          Pvci_creditsyncrunsService.getAll({ select: SYNC_FIELDS, orderBy: ["pvci_startedon desc"], top: 50 }),
          loadAllPages((skipToken, maxPageSize) => Pvci_credituserusagesService.getAll({ select: USER_USAGE_FIELDS, orderBy: ["pvci_usagedate desc"], maxPageSize, skipToken })),
          Pvci_creditprivacysettingsService.getAll({ select: PRIVACY_FIELDS, filter: "pvci_settingkey eq 'credit-user-disclosure'", top: 1 }),
          loadAllPages((skipToken, maxPageSize) => Pvci_transcriptsessionsService.getAll({ select: CORRELATION_SESSION_FIELDS, orderBy: ["pvci_startdatetimeutc desc"], maxPageSize, skipToken })),
        ]);
        if (cancelled) return;
        setUsage(usageResult);
        setCapacity(capacityResult);
        setAgents(agentResult);
        setThresholds(thresholdResult);
        setGovernanceSyncRuns((governanceSyncResult.data ?? []) as unknown as Pvci_governancesyncruns[]);
        setEnvironments(environmentResult);
        setInventorySyncRuns((inventorySyncResult.data ?? []) as unknown as Pvci_inventorysyncruns[]);
        setSyncRuns((syncResult.data ?? []) as unknown as Pvci_creditsyncruns[]);
        setUserUsage(userResult);
        setPrivacy(((privacyResult.data ?? [])[0] ?? null) as unknown as Pvci_creditprivacysettings | null);
        setCorrelationSessions(sessionResult);
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
    environments.forEach((row) => {
      const id = row.pvci_environmentid;
      if (id) options.set(id.toLowerCase(), row.pvci_displayname ?? id);
    });
    agents.forEach((agent) => {
      const id = agent.pvci_environmentid;
      if (id && !options.has(id.toLowerCase())) options.set(id.toLowerCase(), agent.pvci_environmentname ?? id);
    });
    capacity.forEach((row) => {
      const id = row.pvci_environmentid;
      if (id && !options.has(id.toLowerCase())) options.set(id.toLowerCase(), row.pvci_environmentname ?? id);
    });
    return [...options.entries()].sort((left, right) => left[1].localeCompare(right[1]));
  }, [agents, capacity, environments]);
  const revealUserNames = privacy?.pvci_revealusernames === true;

  const environmentScopedUsage = useMemo(
    () => usage.filter((row) => environment === "*" || sameId(row.pvci_environmentid, environment)),
    [usage, environment]
  );
  const environmentScopedAgents = useMemo(
    () => agents.filter((row) => environment === "*" || sameId(row.pvci_environmentid, environment)),
    [agents, environment]
  );
  const agentHarnessByKey = useMemo(() => {
    const values = new Map<string, Exclude<HarnessFilter, "*">>();
    environmentScopedAgents.forEach((row) => {
      values.set(
        resourceIdentityKey(row.pvci_environmentid, row.pvci_resourceid ?? row.pvci_agentinventoryid),
        normalizeHarness(row.pvci_harness)
      );
    });
    return values;
  }, [environmentScopedAgents]);
  const environmentAgents = useMemo(
    () => environmentScopedAgents.filter((row) =>
      harness === "*" || normalizeHarness(row.pvci_harness) === harness
    ),
    [environmentScopedAgents, harness]
  );
  const environmentUsage = useMemo(
    () => environmentScopedUsage.filter((row) => {
      if (harness === "*") return true;
      const effectiveHarness = agentHarnessByKey.get(resourceKey(row)) ?? normalizeHarness(row.pvci_harness);
      return effectiveHarness === harness;
    }),
    [agentHarnessByKey, environmentScopedUsage, harness]
  );
  const latestThresholdByKey = useMemo(() => {
    const values = new Map<string, Pvci_agentthresholdsnapshots>();
    thresholds.forEach((row) => {
      const key = resourceIdentityKey(row.pvci_environmentid, row.pvci_resourceid ?? "unknown");
      if (!values.has(key)) values.set(key, row);
    });
    return values;
  }, [thresholds]);
  const resourceSummaries = useMemo(() => {
    const summaries = new Map<string, ResourceSummary>();
    environmentAgents.forEach((row) => {
      const resourceId = row.pvci_resourceid ?? row.pvci_agentinventoryid;
      const key = resourceIdentityKey(row.pvci_environmentid, resourceId);
      summaries.set(key, {
        label: row.pvci_displayname ?? row.pvci_resourceid ?? "Unknown agent",
        resourceId,
        environmentId: row.pvci_environmentid,
        harness: normalizeHarness(row.pvci_harness),
        threshold: latestThresholdByKey.get(key),
        billed: 0,
        nonbilled: 0,
        facts: 0,
      });
    });
    environmentUsage.forEach((row) => {
      const key = resourceKey(row);
      const current = summaries.get(key) ?? {
        label: row.pvci_agentname ?? row.pvci_resourceid ?? "Unknown resource",
        resourceId: row.pvci_resourceid ?? row.pvci_agentname ?? "unknown",
        environmentId: row.pvci_environmentid,
        harness: agentHarnessByKey.get(key) ?? normalizeHarness(row.pvci_harness),
        threshold: latestThresholdByKey.get(key),
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
  }, [agentHarnessByKey, environmentAgents, environmentUsage, latestThresholdByKey]);
  const scopedThresholds = useMemo(
    () => [...latestThresholdByKey.values()].filter((row) => {
      if (environment !== "*" && !sameId(row.pvci_environmentid, environment)) return false;
      if (harness === "*") return true;
      const key = resourceIdentityKey(row.pvci_environmentid, row.pvci_resourceid ?? "unknown");
      return (agentHarnessByKey.get(key) ?? "unknown") === harness;
    }),
    [agentHarnessByKey, environment, harness, latestThresholdByKey]
  );
  const resourceLabelsByKey = useMemo(
    () => new Map(resourceSummaries.map(([key, summary]) => [key, summary.label])),
    [resourceSummaries]
  );
  const scopedUsage = useMemo(
    () => environmentUsage.filter((row) => resource === "*" || resourceKey(row) === resource),
    [environmentUsage, resource]
  );
  const scopedCapacity = useMemo(
    () => capacity.filter((row) => environment === "*" || sameId(row.pvci_environmentid, environment)),
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
  const selectedUserUsage = useMemo(
    () => userUsage.filter((row) => selectedUser === "*" || (row.pvci_userid ?? "unknown") === selectedUser),
    [userUsage, selectedUser]
  );
  const selectedResourceLabel = resource === "*"
    ? null
    : resourceSummaries.find(([key]) => key === resource)?.[1].label ?? resource;
  const selectedResourceSummary = resource === "*"
    ? null
    : resourceSummaries.find(([key]) => key === resource)?.[1] ?? null;
  const selectedUserLabel = selectedUser === "*"
    ? null
    : userSummaries.find(([key]) => key === selectedUser)?.[1].label ?? selectedUser;
  const environmentSessions = useMemo(
    () => correlationSessions.filter((session) => environment === "*" || sameId(session.pvci_environmentid, environment)),
    [correlationSessions, environment]
  );
  const agentSessions = useMemo(
    () => resource === "*"
      ? environmentSessions
      : environmentSessions.filter((session) =>
        (!selectedResourceSummary?.environmentId || sameId(session.pvci_environmentid, selectedResourceSummary.environmentId))
        && sessionMatchesResource(session, selectedResourceSummary?.resourceId ?? resource, selectedResourceLabel)
      ),
    [environmentSessions, resource, selectedResourceLabel, selectedResourceSummary]
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
      .filter(([, summary]) => related.has(summary.resourceId.toLowerCase()) || related.has(summary.label.toLowerCase()))
      .map(([, summary]) => ({ label: summary.label, value: summary.billed + summary.nonbilled }))
      .sort((left, right) => right.value - left.value);
  }, [userSessions, resourceSummaries]);
  const userCreditTrend = useMemo(
    () => aggregateSplitCreditPeriods(selectedUserUsage, periodGrain),
    [selectedUserUsage, periodGrain]
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
    reportedResources: maxSourceCount(selectedUserUsage.map((row) => row.pvci_resources)),
  }), [combinationSessions, scopedUsage, selectedUserUsage]);

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
  const latestInventorySync = inventorySyncRuns[0];
  const latestGovernanceSync = governanceSyncRuns[0];
  const linkedThresholdCount = scopedThresholds.filter((row) => row._pvci_agentid_value).length;
  const detailedEnvironmentCount = environments.filter((row) => row.pvci_hasdetailedaccess).length;
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
        loadAllPages((skipToken, maxPageSize) => Pvci_credituserusagesService.getAll({ select: USER_USAGE_FIELDS, orderBy: ["pvci_usagedate desc"], maxPageSize, skipToken })),
        Pvci_creditprivacysettingsService.get(privacy.pvci_creditprivacysettingid, { select: PRIVACY_FIELDS }),
      ]);
      setUserUsage(userResult);
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
      <select className="search" value={harness} onChange={(event) => { setHarness(event.target.value as HarnessFilter); setResource("*"); }}>
        <option value="*">All harness evidence</option>
        <option value="github_copilot">GitHub Copilot harness</option>
        <option value="not_github_copilot">Not GitHub Copilot harness</option>
        <option value="unknown">Unknown harness</option>
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
            <div className="si-sub muted small">{fmtFacts(summary.facts)} · {harnessLabel(summary.harness)} · {thresholdLabel(summary.threshold)}</div>
          </button>
        ))}
      </div>

      <div className="credit-nav-heading">
        <span>Users · tenant-wide</span>
        <span>{userSummaries.length}</span>
      </div>
      <div className="credit-nav-list user-nav-list">
        <button className={`session-item credit-nav-item${selectedUser === "*" ? " active" : ""}`} onClick={() => setSelectedUser("*")}>
          <div className="si-top"><span className="si-user">All users</span></div>
          <div className="si-sub muted small">{userUsage.length} tenant-wide source-period facts</div>
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
          <span>Credit sync <strong>{fmtDateTime(latestSync?.pvci_completedon)}</strong></span>
          <span>Inventory sync <strong>{fmtDateTime(latestInventorySync?.pvci_completedon)}</strong></span>
          <span>Governance sync <strong>{fmtDateTime(latestGovernanceSync?.pvci_completedon)}</strong></span>
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
            PPAC exposes user and resource credits as separate aggregate projections. User credits are tenant-wide because that projection has no environment ID. The two credit trends remain authoritative separately; transcript relationships show observed usage but do not assign user credits to an agent.
          </div>
          {resource !== "*" && agentSessions.length === 0 && (
            <div className="selection-gap">
              This PPAC billing resource does not exactly match a transcript bot ID or name. PPAC reports a user count, but not the user identities for this resource, so no user-agent session relationship is inferred.
            </div>
          )}

          <div className="kpis selection-kpis">
            {resource !== "*" && <CreditKpi label="Agent credits" value={fmtCredits(scopedTotals.total)} />}
            {selectedUser !== "*" && <CreditKpi label="User credits · tenant" value={fmtCredits(sumUserCredits(selectedUserUsage))} />}
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
                <SectionHeading text="User credit trend · tenant-wide" help="Authoritative tenant-wide PPAC user credits by source period, split into billed and non-billed lanes. The source has no environment ID, and these values are not assigned to the selected agent." />
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
                <SectionHeading text="Related users · tenant-wide credits" help="Each observed user's full tenant-wide PPAC credit total. It is context for the relationship, not this resource's or environment's attributed charge." />
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
                    {selectedUserUsage.map((row) => (
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

        <SectionHeading text="Tenant inventory" help="Environment and agent inventory collected independently of credit activity. Detailed access reflects environments where deeper Dataverse enrichment is available." className="report-subheading" />
        <div className="sync-strip">
          <span>{latestInventorySync?.pvci_name ?? "No inventory sync run"}</span>
          <span className={`conf ${latestInventorySync?.pvci_status === "success" ? "high" : "multiple"}`}>{latestInventorySync?.pvci_status ?? "not configured"}</span>
          <span>{environments.length} environments</span>
          <span>{agents.length} agents/resources</span>
          <span>{detailedEnvironmentCount} detailed access</span>
        </div>

        <SectionHeading text="Agent credit limits · read-only" help="Latest Power Platform resource-threshold state. This release reports controls but does not change them." className="report-subheading" />
        <div className="sync-strip">
          <span>{latestGovernanceSync?.pvci_name ?? "No governance sync run"}</span>
          <span className={`conf ${latestGovernanceSync?.pvci_status === "success" ? "high" : "multiple"}`}>{latestGovernanceSync?.pvci_status ?? "not configured"}</span>
          <span>{scopedThresholds.length} controls in scope</span>
          <span>{linkedThresholdCount} linked</span>
          <span>{scopedThresholds.length - linkedThresholdCount} unlinked</span>
        </div>
        <div className="credit-table-wrap">
          <table className="runtable credit-table">
            <thead><tr><th>Agent or resource</th><th>Environment ID</th><th>Used</th><th>Limit</th><th>Utilization</th><th>Alert</th><th>Enforcement</th></tr></thead>
            <tbody>
              {scopedThresholds.map((row) => {
                const key = resourceIdentityKey(row.pvci_environmentid, row.pvci_resourceid ?? "unknown");
                return (
                  <tr key={row.pvci_agentthresholdsnapshotid}>
                    <td>{resourceLabelsByKey.get(key) ?? row.pvci_resourceid ?? "Unknown resource"}</td>
                    <td className="mono">{row.pvci_environmentid ?? "Unknown"}</td>
                    <td className="mono">{fmtCredits(row.pvci_resourceconsumption ?? 0)}</td>
                    <td className="mono">{fmtCredits(row.pvci_limit ?? 0)}</td>
                    <td>{fmtPercent(thresholdUtilization(row))}</td>
                    <td>{row.pvci_notifyifovercapacity ? `${row.pvci_notificationthreshold ?? 0}%` : "Off"}</td>
                    <td><span className={`conf ${row.pvci_stopresource || row.pvci_stopifovercapacity ? "multiple" : "high"}`}>{thresholdEnforcement(row)}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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

function normalizeHarness(value?: string): Exclude<HarnessFilter, "*"> {
  if (value === "github_copilot" || value === "not_github_copilot") return value;
  return "unknown";
}

function harnessLabel(value: Exclude<HarnessFilter, "*">) {
  if (value === "github_copilot") return "GitHub harness";
  if (value === "not_github_copilot") return "Not GitHub harness";
  return "Unknown harness";
}

function thresholdLabel(row?: Pvci_agentthresholdsnapshots) {
  if (!row) return "No limit record";
  return `${fmtCredits(row.pvci_resourceconsumption ?? 0)} / ${fmtCredits(row.pvci_limit ?? 0)} credits`;
}

function thresholdUtilization(row: Pvci_agentthresholdsnapshots) {
  const limit = row.pvci_limit ?? 0;
  return limit > 0 ? (row.pvci_resourceconsumption ?? 0) / limit : 0;
}

function thresholdEnforcement(row: Pvci_agentthresholdsnapshots) {
  if (row.pvci_stopresource) return "Stopped";
  if (row.pvci_stopifovercapacity) return "Stop at limit";
  return "Monitor only";
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
  return resourceIdentityKey(row.pvci_environmentid, row.pvci_resourceid ?? row.pvci_agentname ?? "unknown");
}

function resourceIdentityKey(environmentId: string | undefined, resourceId: string) {
  return `${environmentId?.toLowerCase() ?? ""}|${resourceId.toLowerCase()}`;
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

function fmtPercent(value: number) {
  return value.toLocaleString(undefined, { style: "percent", maximumFractionDigits: 1 });
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