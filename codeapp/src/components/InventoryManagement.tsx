import { useEffect, useMemo, useState } from "react";
import { Pvci_environmentinventoriesService } from "../generated/services/Pvci_environmentinventoriesService";
import { Pvci_inventorysyncrunsService } from "../generated/services/Pvci_inventorysyncrunsService";
import { Pvci_transcriptaccessrequestsService } from "../generated/services/Pvci_transcriptaccessrequestsService";
import { Pvci_agentinventoriesService } from "../generated/services/Pvci_agentinventoriesService";
import type { Pvci_environmentinventories } from "../generated/models/Pvci_environmentinventoriesModel";
import type { Pvci_inventorysyncruns } from "../generated/models/Pvci_inventorysyncrunsModel";
import type { Pvci_transcriptaccessrequests } from "../generated/models/Pvci_transcriptaccessrequestsModel";
import type { Pvci_agentinventories } from "../generated/models/Pvci_agentinventoriesModel";
import { AgentInventory } from "./AgentInventory";
import { loadAllPages } from "../lib/paging";
import {
  canEnableTranscriptCollector,
  isActiveTranscriptAccessRequest,
  matchesInventoryFilter,
  transcriptOnboardingStatusLabel,
  type InventoryFilter,
  type TranscriptOnboardingMode,
} from "../lib/transcriptAccessState";

const ENVIRONMENT_FIELDS = [
  "pvci_environmentinventoryid", "pvci_tenantid", "pvci_environmentid", "pvci_displayname", "pvci_environmenturl",
  "pvci_environmenttype", "pvci_geo", "pvci_state", "pvci_ismanaged", "pvci_hasdataverse",
  "pvci_hasdetailedaccess", "pvci_lastsyncedon", "pvci_transcriptaccessstatus",
  "pvci_transcriptaccessreason", "pvci_transcriptprobeon", "pvci_transcriptsamplecount",
  "pvci_transcriptcollectorenabled", "pvci_transcriptlastcollectedon",
  "pvci_transcriptlastcollectionstatus", "pvci_transcriptlastcollectionerror",
  "pvci_transcriptlastbatchcount", "pvci_transcriptonboardingmode",
  "pvci_transcriptonboardingstatus", "pvci_transcriptcollectorapplicationid",
  "pvci_transcriptaccesslastverifiedon", "pvci_transcriptaccessroleverified",
  "pvci_transcriptelevationcleanupverified", "pvci_transcriptonboardinglasterror",
];

const INVENTORY_SYNC_FIELDS = [
  "pvci_inventorysyncrunid", "pvci_name", "pvci_source", "pvci_startedon", "pvci_completedon",
  "pvci_status", "pvci_environmentcount", "pvci_agentcount", "pvci_createdcount",
  "pvci_updatedcount", "pvci_rejectedcount", "pvci_error",
];

const ACCESS_REQUEST_FIELDS = [
  "pvci_transcriptaccessrequestid", "pvci_name", "pvci_environmentid", "pvci_environmenturl",
  "pvci_action", "pvci_requestedmode", "pvci_status", "pvci_requestedon", "pvci_processedon",
  "pvci_accessstatus", "pvci_roleverified", "pvci_elevationcleanupverified", "pvci_evidence",
  "pvci_error", "createdon", "_pvci_environmentinventoryid_value",
];

const AGENT_FIELDS = [
  "pvci_agentinventoryid", "pvci_tenantid", "pvci_environmentid", "pvci_environmentname",
  "pvci_resourceid", "pvci_botid", "pvci_displayname", "pvci_schemaname", "pvci_authoringorigin",
  "pvci_published", "pvci_lastsyncedon", "pvci_evidencejson",
];

function createTranscriptVerificationRequestKey() {
  return `transcript-verify-${crypto.randomUUID()}`;
}

export function InventoryManagement({ hostEnvironmentId, onCollectorStateChange, onOpenSession }: {
  hostEnvironmentId?: string;
  onCollectorStateChange: (environmentId: string, enabled: boolean) => void;
  onOpenSession: (sessionId: string) => void;
}) {
  const [environments, setEnvironments] = useState<Pvci_environmentinventories[]>([]);
  const [latestSync, setLatestSync] = useState<Pvci_inventorysyncruns | null>(null);
  const [accessRequests, setAccessRequests] = useState<Pvci_transcriptaccessrequests[]>([]);
  const [agents, setAgents] = useState<Pvci_agentinventories[]>([]);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [inventoryView, setInventoryView] = useState<"environments" | "agents">("environments");
  const [agentFocusEnvironmentId, setAgentFocusEnvironmentId] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<InventoryFilter>("all");
  const [collectorBusyId, setCollectorBusyId] = useState<string | null>(null);
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState<string | null>(null);
  const [onboardingMode, setOnboardingMode] = useState<TranscriptOnboardingMode>("SourceManaged");
  const [onboardingBusy, setOnboardingBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      loadAllPages((skipToken, maxPageSize) => Pvci_environmentinventoriesService.getAll({
        select: ENVIRONMENT_FIELDS,
        orderBy: ["pvci_displayname asc"],
        maxPageSize,
        skipToken,
      })),
      Pvci_inventorysyncrunsService.getAll({
        select: INVENTORY_SYNC_FIELDS,
        orderBy: ["pvci_startedon desc"],
        top: 1,
      }),
      Pvci_transcriptaccessrequestsService.getAll({
        select: ACCESS_REQUEST_FIELDS,
        orderBy: ["createdon desc"],
        top: 200,
      }),
      loadAllPages((skipToken, maxPageSize) => Pvci_agentinventoriesService.getAll({
        select: AGENT_FIELDS,
        orderBy: ["pvci_displayname asc"],
        maxPageSize,
        skipToken,
      })).catch((reason) => {
        if (!cancelled) setAgentError(reason instanceof Error ? reason.message : String(reason));
        return [] as Pvci_agentinventories[];
      }),
    ]).then(([environmentRows, syncResult, requestResult, agentRows]) => {
      if (cancelled) return;
      setEnvironments(environmentRows);
      setLatestSync(((syncResult.data ?? [])[0] ?? null) as unknown as Pvci_inventorysyncruns | null);
      setAccessRequests((requestResult.data ?? []) as unknown as Pvci_transcriptaccessrequests[]);
      setAgents(agentRows);
    }).catch((reason) => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [refreshKey]);

  useEffect(() => {
    if (!accessRequests.some((request) => isActiveTranscriptAccessRequest(request.pvci_status))) return;
    const timer = window.setTimeout(() => setRefreshKey((current) => current + 1), 15_000);
    return () => window.clearTimeout(timer);
  }, [accessRequests]);

  const refresh = () => {
    setLoading(true);
    setError(null);
    setRefreshKey((current) => current + 1);
  };

  const metrics = useMemo(() => {
    const dataverseReady = environments.filter((row) => row.pvci_hasdataverse && row.pvci_environmenturl).length;
    const enabled = environments.filter((row) => row.pvci_transcriptcollectorenabled).length;
    const readable = environments.filter((row) => canEnableTranscriptCollector("Verified", row.pvci_transcriptaccessstatus)).length;
    const denied = environments.filter((row) => row.pvci_transcriptaccessstatus === "access_denied").length;
    const notReady = environments.length - dataverseReady;
    return { dataverseReady, enabled, readable, denied, notReady };
  }, [environments]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return environments.filter((row) => {
      if (!matchesInventoryFilter(row, filter)) return false;
      if (!query) return true;
      return [
        row.pvci_displayname,
        row.pvci_environmentid,
        row.pvci_environmenttype,
        row.pvci_geo,
        row.pvci_transcriptaccessstatus,
      ].some((value) => (value ?? "").toLowerCase().includes(query));
    });
  }, [environments, filter, search]);

  const selectedEnvironment = environments.find((row) => row.pvci_environmentinventoryid === selectedEnvironmentId) ?? null;
  const selectedRequests = selectedEnvironment
    ? accessRequests.filter((request) => request.pvci_environmentid?.toLowerCase() === selectedEnvironment.pvci_environmentid?.toLowerCase())
    : [];
  const selectedHasActiveRequest = selectedRequests.some((request) => isActiveTranscriptAccessRequest(request.pvci_status));
  const agentCounts = useMemo(() => {
    const counts = new Map<string, number>();
    agents.forEach((agent) => {
      const environmentId = agent.pvci_environmentid?.toLowerCase();
      if (environmentId) counts.set(environmentId, (counts.get(environmentId) ?? 0) + 1);
    });
    return counts;
  }, [agents]);

  const showAgents = (environmentId?: string) => {
    setAgentFocusEnvironmentId(environmentId);
    setInventoryView("agents");
  };

  const openOnboarding = (row: Pvci_environmentinventories) => {
    setSelectedEnvironmentId(row.pvci_environmentinventoryid);
    setOnboardingMode((row.pvci_transcriptonboardingmode as TranscriptOnboardingMode | undefined) ?? "SourceManaged");
    setNotice(null);
    setError(null);
  };

  const submitVerificationRequest = async () => {
    if (!selectedEnvironment || onboardingBusy || selectedHasActiveRequest) return;
    if (!selectedEnvironment.pvci_environmentid || !selectedEnvironment.pvci_environmenturl) {
      setError("Source verification requires an environment ID and Dataverse URL.");
      return;
    }
    if (!window.confirm(
      `Verify source-managed transcript access for ${environmentLabel(selectedEnvironment)}? The packaged processor will perform an ID-only read with the collector identity.`
    )) return;

    setOnboardingBusy(true);
    setNotice(null);
    setError(null);
    try {
      const now = new Date().toISOString();
      const payload = {
        pvci_name: `Verify · ${environmentLabel(selectedEnvironment)}`,
        pvci_requestkey: createTranscriptVerificationRequestKey(),
        pvci_environmentid: selectedEnvironment.pvci_environmentid,
        pvci_environmenturl: selectedEnvironment.pvci_environmenturl,
        pvci_action: "Verify",
        pvci_requestedmode: "SourceManaged",
        pvci_status: "Pending",
        pvci_requestedon: now,
        "pvci_EnvironmentInventoryId@odata.bind": `/pvci_environmentinventories(${selectedEnvironment.pvci_environmentinventoryid})`,
      };
      await Pvci_transcriptaccessrequestsService.create(
        payload as unknown as Parameters<typeof Pvci_transcriptaccessrequestsService.create>[0]
      );
      setEnvironments((current) => current.map((row) => row.pvci_environmentinventoryid === selectedEnvironment.pvci_environmentinventoryid
        ? { ...row, pvci_transcriptonboardingmode: "SourceManaged", pvci_transcriptonboardingstatus: "Pending" }
        : row));
      setNotice(`${environmentLabel(selectedEnvironment)} verification queued.`);
      setRefreshKey((current) => current + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setOnboardingBusy(false);
    }
  };

  const excludeSource = async () => {
    if (!selectedEnvironment || onboardingBusy) return;
    if (!window.confirm(`Exclude ${environmentLabel(selectedEnvironment)} from transcript collection?`)) return;
    setOnboardingBusy(true);
    setNotice(null);
    setError(null);
    try {
      await Pvci_environmentinventoriesService.update(selectedEnvironment.pvci_environmentinventoryid, {
        pvci_transcriptonboardingmode: "Excluded",
        pvci_transcriptonboardingstatus: "Excluded",
        pvci_transcriptcollectorenabled: false,
      });
      setEnvironments((current) => current.map((row) => row.pvci_environmentinventoryid === selectedEnvironment.pvci_environmentinventoryid
        ? { ...row, pvci_transcriptonboardingmode: "Excluded", pvci_transcriptonboardingstatus: "Excluded", pvci_transcriptcollectorenabled: false }
        : row));
      setNotice(`${environmentLabel(selectedEnvironment)} excluded from transcript collection.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setOnboardingBusy(false);
    }
  };

  const setCollectorEnabled = async (row: Pvci_environmentinventories, enabled: boolean) => {
    const id = row.pvci_environmentinventoryid;
    if (!id || collectorBusyId) return;
    if (enabled && !canEnableTranscriptCollector(row.pvci_transcriptonboardingstatus, row.pvci_transcriptaccessstatus)) {
      setError("Transcript collection can be enabled only after onboarding is Verified and the source probe is readable.");
      return;
    }
    if (enabled && !window.confirm(
      `Enable cross-environment transcript collection for ${environmentLabel(row)}? Transcript data will be copied from this remote environment and stored in the Dataverse environment where Conversation Insights is installed. Confirm that you are authorized to move and retain this data. Disabling collection later stops future imports but does not delete data already copied.`
    )) return;

    setCollectorBusyId(id);
    setNotice(null);
    setError(null);
    try {
      await Pvci_environmentinventoriesService.update(id, {
        pvci_transcriptcollectorenabled: enabled,
      });
      setEnvironments((current) => current.map((environmentRow) =>
        environmentRow.pvci_environmentinventoryid === id
          ? { ...environmentRow, pvci_transcriptcollectorenabled: enabled }
          : environmentRow
      ));
      if (row.pvci_environmentid) onCollectorStateChange(row.pvci_environmentid, enabled);
      setNotice(`${environmentLabel(row)} collection ${enabled ? "enabled" : "disabled"}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setCollectorBusyId(null);
    }
  };

  return (
    <div className="inventory-management">
      <header className="inventory-title">
        <div>
          <span className="report-eyebrow">Solution configuration</span>
          <h2>Inventory management</h2>
          <p>Tenant environment discovery, source readiness, transcript access, and collection state.</p>
        </div>
        <button
          type="button"
          className="inventory-refresh"
          disabled={loading}
          onClick={refresh}
        >
          <span aria-hidden="true">↻</span> {loading ? "Refreshing" : "Refresh data"}
        </button>
      </header>

      {error && <div className="error inventory-error">{error}</div>}
      {notice && <p className="collector-notice" role="status">{notice}</p>}

      <section className="inventory-sync" aria-label="Latest tenant inventory sync">
        <div>
          <span className="report-eyebrow">Latest tenant inventory</span>
          <strong>{latestSync?.pvci_name ?? "No inventory sync run"}</strong>
        </div>
        <span className={`conf ${latestSync?.pvci_status === "success" ? "high" : "multiple"}`}>
          {latestSync?.pvci_status ?? "not configured"}
        </span>
        <span>Completed {fmtDateTime(latestSync?.pvci_completedon)}</span>
        <span>{latestSync?.pvci_agentcount ?? 0} agents/resources</span>
        <span>{latestSync?.pvci_rejectedcount ?? 0} rejected</span>
      </section>

      <section className="inventory-kpis" aria-label="Source readiness summary">
        <InventoryKpi label="Discovered" value={environments.length} filter="all" activeFilter={filter} onSelect={setFilter} />
        <InventoryKpi label="Dataverse ready" value={metrics.dataverseReady} tone="good" filter="ready" activeFilter={filter} onSelect={setFilter} />
        <InventoryKpi label="Collector enabled" value={metrics.enabled} tone={metrics.enabled ? "good" : "warn"} filter="enabled" activeFilter={filter} onSelect={setFilter} />
        <InventoryKpi label="Transcript readable" value={metrics.readable} tone="good" filter="readable" activeFilter={filter} onSelect={setFilter} />
        <InventoryKpi label="Access denied" value={metrics.denied} tone={metrics.denied ? "bad" : "good"} filter="denied" activeFilter={filter} onSelect={setFilter} />
        <InventoryKpi label="Not ready" value={metrics.notReady} tone={metrics.notReady ? "warn" : "good"} filter="not-ready" activeFilter={filter} onSelect={setFilter} />
      </section>

      <div className="segmented inventory-view-switch" aria-label="Inventory view">
        <button type="button" className={inventoryView === "environments" ? "on" : ""} onClick={() => setInventoryView("environments")}>Environments</button>
        <button type="button" className={inventoryView === "agents" ? "on" : ""} onClick={() => showAgents()}>Agents ({agents.length})</button>
      </div>

      {inventoryView === "agents" && <AgentInventory
        key={agentFocusEnvironmentId ?? "all-environments"}
        agents={agents}
        environments={environments}
        hostEnvironmentId={hostEnvironmentId}
        loading={loading}
        error={agentError}
        focusEnvironmentId={agentFocusEnvironmentId}
        onOpenSession={onOpenSession}
      />}

      {inventoryView === "environments" && <>

      {selectedEnvironment && <section className="onboarding-workspace" aria-label={`Transcript onboarding for ${environmentLabel(selectedEnvironment)}`}>
        <div className="onboarding-head">
          <div>
            <span className="report-eyebrow">Transcript source onboarding</span>
            <h3>{environmentLabel(selectedEnvironment)}</h3>
            <span className="inventory-row-id">{selectedEnvironment.pvci_environmenturl}</span>
          </div>
          <button type="button" className="onboarding-close" onClick={() => setSelectedEnvironmentId(null)} aria-label="Close transcript source onboarding">×</button>
        </div>
        <div className="onboarding-grid">
          <label>
            Authorization mode
            <select value={onboardingMode} onChange={(event) => setOnboardingMode(event.target.value as TranscriptOnboardingMode)} disabled={onboardingBusy || selectedHasActiveRequest}>
              <option value="SourceManaged">Source-managed</option>
              <option value="AdministratorBootstrap" disabled>Administrator bootstrap · reconciler unavailable</option>
              <option value="Excluded">Excluded</option>
            </select>
          </label>
          <OnboardingFact label="Status" value={transcriptOnboardingStatusLabel(selectedEnvironment.pvci_transcriptonboardingstatus)} />
          <OnboardingFact label="Access" value={transcriptAccessLabel(selectedEnvironment.pvci_transcriptaccessstatus)} />
          <OnboardingFact label="Least-privilege role" value={selectedEnvironment.pvci_transcriptaccessroleverified ? "Verified" : "Not verified by probe"} />
          <OnboardingFact label="Elevation cleanup" value={selectedEnvironment.pvci_transcriptelevationcleanupverified ? "Verified" : "Not applicable or unverified"} />
          <OnboardingFact label="Last verified" value={fmtDateTime(selectedEnvironment.pvci_transcriptaccesslastverifiedon)} />
        </div>
        {onboardingMode === "SourceManaged" && <p className="onboarding-guidance">Grant the collector application the packaged transcript reader role in this source environment, then submit verification. The probe reads only one transcript ID and does not prove the exact assigned role.</p>}
        {onboardingMode === "AdministratorBootstrap" && <p className="onboarding-guidance warning">Administrator bootstrap will become available only when the external reconciler can provision the application user, assign the least-privilege role, and prove temporary elevation cleanup.</p>}
        {onboardingMode === "Excluded" && <p className="onboarding-guidance">Exclusion disables collection for this source and records the current inventory mode as Excluded.</p>}
        <div className="onboarding-actions">
          {onboardingMode === "SourceManaged" && <button type="button" className="privacy-action" disabled={onboardingBusy || selectedHasActiveRequest || !selectedEnvironment.pvci_environmenturl} onClick={() => void submitVerificationRequest()}>{selectedHasActiveRequest ? "Verification in progress" : onboardingBusy ? "Submitting" : "Verify access"}</button>}
          {onboardingMode === "AdministratorBootstrap" && <button type="button" className="privacy-action" disabled>Bootstrap unavailable</button>}
          {onboardingMode === "Excluded" && <button type="button" className="privacy-action revoke" disabled={onboardingBusy} onClick={() => void excludeSource()}>{onboardingBusy ? "Saving" : "Exclude source"}</button>}
        </div>
        <h4>Request history</h4>
        <div className="inventory-table-wrap">
          <table className="runtable onboarding-history">
            <thead><tr><th>Requested</th><th>Action</th><th>Status</th><th>Access result</th><th>Evidence or error</th></tr></thead>
            <tbody>
              {!selectedRequests.length && <tr><td colSpan={5} className="muted">No verification requests for this source.</td></tr>}
              {selectedRequests.slice(0, 10).map((request) => <tr key={request.pvci_transcriptaccessrequestid}>
                <td>{fmtDateTime(request.pvci_requestedon ?? request.createdon)}</td>
                <td>{request.pvci_action ?? "Unknown"}</td>
                <td><span className={`conf ${request.pvci_status === "Verified" ? "high" : request.pvci_status === "Failed" ? "risk-critical" : "multiple"}`}>{request.pvci_status ?? "Unknown"}</span></td>
                <td>{transcriptAccessLabel(request.pvci_accessstatus)}</td>
                <td title={request.pvci_error}>{request.pvci_error || request.pvci_evidence || "Pending processor result"}</td>
              </tr>)}
            </tbody>
          </table>
        </div>
      </section>}

      <div className="inventory-toolbar">
        <input
          className="search"
          type="search"
          placeholder="Search environment, ID, type, region, or access state…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <select className="search" value={filter} onChange={(event) => setFilter(event.target.value as InventoryFilter)}>
          <option value="all">All environments</option>
          <option value="ready">Dataverse ready</option>
          <option value="enabled">Collector enabled</option>
          <option value="readable">Transcript readable</option>
          <option value="denied">Access denied</option>
          <option value="not-ready">Dataverse not ready</option>
        </select>
        <span className="muted small">{filtered.length} of {environments.length}</span>
      </div>

      <div className="inventory-table-wrap">
        <table className="runtable inventory-table">
          <thead>
            <tr>
              <th>Environment</th>
              <th>Result</th>
              <th>Platform</th>
              <th>Dataverse</th>
              <th>Detailed access</th>
              <th>Transcript access</th>
              <th>Onboarding</th>
              <th>Agents</th>
              <th>Collector</th>
              <th>Last probe</th>
              <th>Watermark</th>
              <th>Last batch</th>
            </tr>
          </thead>
          <tbody>
            {loading && !environments.length && <tr><td colSpan={12} className="muted">Loading inventory…</td></tr>}
            {!loading && !filtered.length && <tr><td colSpan={12} className="muted">No environments match the current filter.</td></tr>}
            {filtered.map((row) => (
              <tr key={row.pvci_environmentinventoryid}>
                <td title={row.pvci_environmentid}>
                  <strong>{environmentLabel(row)}</strong>
                  <span className="inventory-row-id">{row.pvci_environmentid}</span>
                </td>
                <td title={row.pvci_transcriptlastcollectionerror}>
                  {row.pvci_transcriptlastcollectionstatus
                    ? <span className={`conf ${row.pvci_transcriptlastcollectionstatus === "success" ? "high" : "multiple"}`}>{row.pvci_transcriptlastcollectionstatus}</span>
                    : <span className="muted">Not run</span>}
                </td>
                <td>
                  <span>{row.pvci_environmenttype ?? "Unknown"}</span>
                  <span className="inventory-row-id">{row.pvci_geo ?? row.pvci_state ?? "Region unknown"}</span>
                </td>
                <td title={row.pvci_environmenturl}>
                  <span className={`conf ${row.pvci_hasdataverse && row.pvci_environmenturl ? "high" : "multiple"}`}>
                    {row.pvci_hasdataverse && row.pvci_environmenturl ? "Ready" : row.pvci_hasdataverse ? "URL missing" : "Unavailable"}
                  </span>
                </td>
                <td><span className={`conf ${row.pvci_hasdetailedaccess ? "high" : "multiple"}`}>{row.pvci_hasdetailedaccess ? "Available" : "Limited"}</span></td>
                <td title={row.pvci_transcriptaccessreason}>
                  <span className={`conf ${transcriptAccessClass(row.pvci_transcriptaccessstatus)}`}>{transcriptAccessLabel(row.pvci_transcriptaccessstatus)}</span>
                </td>
                <td>
                  <button type="button" className="onboarding-link" onClick={() => openOnboarding(row)}>
                    {transcriptOnboardingStatusLabel(row.pvci_transcriptonboardingstatus)}
                  </button>
                  <span className="inventory-row-id">{onboardingModeLabel(row.pvci_transcriptonboardingmode)}</span>
                </td>
                <td>{row.pvci_environmentid && (agentCounts.get(row.pvci_environmentid.toLowerCase()) ?? 0) > 0
                  ? <button type="button" className="onboarding-link" onClick={() => showAgents(row.pvci_environmentid)}>{agentCounts.get(row.pvci_environmentid.toLowerCase())} discovered</button>
                  : <span className="muted">None discovered</span>}</td>
                <td>
                  {row.pvci_environmentid?.toLowerCase() === hostEnvironmentId?.toLowerCase() ? (
                    <span className="conf high">Local automatic</span>
                  ) : <label className="collector-toggle" title={!canEnableTranscriptCollector(row.pvci_transcriptonboardingstatus, row.pvci_transcriptaccessstatus) ? "Complete transcript source verification before enabling collection." : undefined}>
                    <input
                      type="checkbox"
                      checked={row.pvci_transcriptcollectorenabled ?? false}
                      disabled={collectorBusyId !== null || (!row.pvci_transcriptcollectorenabled && !canEnableTranscriptCollector(row.pvci_transcriptonboardingstatus, row.pvci_transcriptaccessstatus))}
                      onChange={(event) => void setCollectorEnabled(row, event.target.checked)}
                      aria-label={`${row.pvci_transcriptcollectorenabled ? "Disable" : "Enable"} transcript collection for ${environmentLabel(row)}`}
                    />
                    <span>{collectorBusyId === row.pvci_environmentinventoryid ? "Saving" : row.pvci_transcriptcollectorenabled ? "Enabled" : "Off"}</span>
                  </label>}
                </td>
                <td>{fmtDateTime(row.pvci_transcriptprobeon)}</td>
                <td>{fmtDateTime(row.pvci_transcriptlastcollectedon)}</td>
                <td className="mono">{row.pvci_transcriptlastbatchcount ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </>}

    </div>
  );
}

function InventoryKpi({ label, value, tone, filter, activeFilter, onSelect }: {
  label: string;
  value: number;
  tone?: string;
  filter: InventoryFilter;
  activeFilter: InventoryFilter;
  onSelect: (filter: InventoryFilter) => void;
}) {
  const active = filter === activeFilter;
  return <button type="button" className={`kpi inventory-kpi-filter${active ? " active" : ""}`} aria-pressed={active} onClick={() => onSelect(filter)}>
    <span className="kpi-label">{label}</span>
    <span className={`kpi-value ${tone ?? ""}`}>{value}</span>
  </button>;
}

function OnboardingFact({ label, value }: { label: string; value: string }) {
  return <div className="onboarding-fact"><span>{label}</span><strong>{value}</strong></div>;
}

function environmentLabel(row: Pvci_environmentinventories) {
  return row.pvci_displayname ?? row.pvci_environmentid ?? "Unknown environment";
}

function transcriptAccessLabel(status?: string) {
  if (status === "readable_with_rows") return "Readable · data";
  if (status === "readable_empty") return "Readable · empty";
  if (status === "access_denied") return "Access denied";
  if (status === "unavailable") return "Unavailable";
  if (status === "auth_error") return "Auth error";
  return status ?? "Not probed";
}

function onboardingModeLabel(mode?: string) {
  if (mode === "SourceManaged") return "Source-managed";
  if (mode === "AdministratorBootstrap") return "Administrator bootstrap";
  if (mode === "Excluded") return "Excluded";
  return "Mode not selected";
}

function transcriptAccessClass(status?: string) {
  if (status === "readable_with_rows") return "high";
  if (status === "readable_empty") return "multiple";
  if (!status) return "multiple";
  return "risk-critical";
}

function fmtDateTime(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
