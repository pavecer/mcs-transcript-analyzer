import { useEffect, useMemo, useRef, useState } from "react";
import { Pvci_creditsyncrunsService } from "../generated/services/Pvci_creditsyncrunsService";
import { Pvci_environmentinventoriesService } from "../generated/services/Pvci_environmentinventoriesService";
import { Pvci_governancesyncrunsService } from "../generated/services/Pvci_governancesyncrunsService";
import { Pvci_inventorysyncrunsService } from "../generated/services/Pvci_inventorysyncrunsService";
import { Pvci_syncstatesService } from "../generated/services/Pvci_syncstatesService";
import { Pvci_thresholdchangerequestsService } from "../generated/services/Pvci_thresholdchangerequestsService";
import { Pvci_transcriptaccessrequestsService } from "../generated/services/Pvci_transcriptaccessrequestsService";
import { SolutionsService } from "../generated/services/SolutionsService";
import { WorkflowsService } from "../generated/services/WorkflowsService";
import { ConnectionreferencesService } from "../generated/services/ConnectionreferencesService";
import type { Pvci_creditsyncruns } from "../generated/models/Pvci_creditsyncrunsModel";
import type { Pvci_environmentinventories } from "../generated/models/Pvci_environmentinventoriesModel";
import type { Pvci_governancesyncruns } from "../generated/models/Pvci_governancesyncrunsModel";
import type { Pvci_inventorysyncruns } from "../generated/models/Pvci_inventorysyncrunsModel";
import type { Pvci_syncstates } from "../generated/models/Pvci_syncstatesModel";
import type { Pvci_thresholdchangerequests } from "../generated/models/Pvci_thresholdchangerequestsModel";
import type { Pvci_transcriptaccessrequests } from "../generated/models/Pvci_transcriptaccessrequestsModel";
import type { Workflows } from "../generated/models/WorkflowsModel";
import type { Connectionreferences } from "../generated/models/ConnectionreferencesModel";
import {
  assessCentralCollection,
  assessFlowConfiguration,
  assessRequestProcessor,
  assessScheduledRun,
  buildFlowDetailsUrl,
  buildFlowDiagnosticText,
  notInstalledAssessment,
  summarizeRequestQueue,
  summarizeRunHistory,
  unavailableAssessment,
  type FlowOperationAssessment,
  type FlowOperationState,
  type FlowConfigurationAssessment,
  type FlowRunEvidence,
  type FlowRunHistorySummary,
  type RequestQueueSummary,
} from "../lib/flowOperations";
import { loadAllPages } from "../lib/paging";

type OperationsDestination = "inventory" | "credits";
type OperationsFilter = "all" | "review" | "failed" | "pending" | "core" | "credits";

interface OperationsData {
  syncStates: Pvci_syncstates[];
  environments: Pvci_environmentinventories[];
  inventoryRuns: Pvci_inventorysyncruns[];
  accessRequests: Pvci_transcriptaccessrequests[];
  creditRuns: Pvci_creditsyncruns[];
  governanceRuns: Pvci_governancesyncruns[];
  thresholdRequests: Pvci_thresholdchangerequests[];
  workflows: Workflows[];
  connectionReferences: Connectionreferences[];
  creditsInstalled: boolean | null;
  errors: Partial<Record<EvidenceSource, string>>;
  refreshedOn?: string;
  evaluatedAt: number;
}

type EvidenceSource = "sync" | "central" | "inventory" | "access" | "configuration" | "credits-capability" | "credit" | "governance" | "threshold";

interface EvidenceItem {
  id: string;
  startedOn?: string;
  at?: string;
  status?: string;
  durationMs?: number;
  detail: string;
  error?: string;
}

interface OperationRow {
  id: string;
  flowId: string;
  name: string;
  solution: "Core" | "Credits";
  cadence: string;
  purpose: string;
  impact: string;
  nextStep: string;
  assessment: FlowOperationAssessment;
  configuration: FlowConfigurationAssessment;
  evidence: EvidenceItem[];
  history: FlowRunHistorySummary;
  historyCoverage: "runs" | "requests" | "sources" | "latest-only";
  queue?: RequestQueueSummary;
  destination?: OperationsDestination;
}

const EMPTY_DATA: OperationsData = {
  syncStates: [],
  environments: [],
  inventoryRuns: [],
  accessRequests: [],
  creditRuns: [],
  governanceRuns: [],
  thresholdRequests: [],
  workflows: [],
  connectionReferences: [],
  creditsInstalled: null,
  errors: {},
  evaluatedAt: 0,
};

const HOUR = 60 * 60 * 1000;
const HOURLY_STALE_AFTER = 2.5 * HOUR;
const DAILY_STALE_AFTER = 36 * HOUR;
const PROCESSOR_OVERDUE_AFTER = 10 * 60 * 1000;
const EVIDENCE_TIMEOUT_MS = 15_000;
const PACKAGED_FLOW_IDS = [
  "eee71534-988d-f111-8077-7ced8d95b46e",
  "371b3cad-8596-f111-8076-7ced8d95b46e",
  "320f4f61-b895-f111-8076-7ced8d95b46e",
  "f324dbaa-6e9d-f111-b8de-7ced8d95b46e",
  "0bfaa799-f094-f111-8076-7ced8d95b46e",
  "1afedf5c-1396-f111-8076-7ced8d95b46e",
  "c8d754c8-1896-f111-8076-7ced8d95b46e",
];
const PACKAGED_CONNECTIONS = [
  "pvci_centralcollector",
  "pvci_dataversesync",
  "pvci_powerplatformadminv2",
  "pvci_licensinghttp",
  "pvci_powerplatformapi",
];

export function OperationsOverview({ hostEnvironmentId, onNavigate }: {
  hostEnvironmentId?: string;
  onNavigate: (destination: OperationsDestination) => void;
}) {
  const [data, setData] = useState<OperationsData>(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<OperationsFilter>("all");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [pageVisible, setPageVisible] = useState(() => document.visibilityState === "visible");
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "error">("idle");
  const reviewRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      setLoading(true);
      const next: OperationsData = { ...EMPTY_DATA, errors: {} };

      try {
        const solutionResult = await withEvidenceTimeout(SolutionsService.getAll({
          select: ["solutionid"],
          filter: "uniquename eq 'pvConversationInsightsCredits'",
          top: 1,
        }));
        next.creditsInstalled = (solutionResult.data ?? []).length > 0;
      } catch (reason) {
        next.errors["credits-capability"] = errorMessage(reason);
      }

      const coreResults = await Promise.allSettled([
        withEvidenceTimeout(Pvci_syncstatesService.getAll({
          select: ["pvci_syncstateid", "pvci_name", "pvci_lastrunon", "pvci_lastrunstatus", "pvci_recordsprocessed", "pvci_lasterror"],
          filter: "pvci_name eq 'default'",
          top: 1,
        })),
        withEvidenceTimeout(loadAllPages((skipToken, maxPageSize) => Pvci_environmentinventoriesService.getAll({
          select: [
            "pvci_environmentinventoryid", "pvci_environmentid", "pvci_displayname",
            "pvci_transcriptcollectorenabled", "pvci_transcriptlastcollectedon",
            "pvci_transcriptlastcollectionstatus", "pvci_transcriptlastcollectionerror",
            "pvci_transcriptlastbatchcount",
          ],
          maxPageSize,
          skipToken,
        }))),
        withEvidenceTimeout(Pvci_inventorysyncrunsService.getAll({
          select: ["pvci_inventorysyncrunid", "pvci_name", "pvci_startedon", "pvci_completedon", "pvci_status", "pvci_environmentcount", "pvci_agentcount", "pvci_rejectedcount", "pvci_error"],
          orderBy: ["pvci_startedon desc"],
          top: 10,
        })),
        withEvidenceTimeout(Pvci_transcriptaccessrequestsService.getAll({
          select: ["pvci_transcriptaccessrequestid", "pvci_name", "pvci_status", "pvci_requestedon", "pvci_processedon", "pvci_accessstatus", "pvci_error"],
          orderBy: ["pvci_requestedon desc"],
          top: 25,
        })),
        withEvidenceTimeout(Promise.all([
          WorkflowsService.getAll({
            select: ["workflowid", "name", "statecode", "statuscode"],
            filter: PACKAGED_FLOW_IDS.map((id) => `workflowid eq ${id}`).join(" or "),
            top: PACKAGED_FLOW_IDS.length,
          }),
          ConnectionreferencesService.getAll({
            select: ["connectionreferenceid", "connectionreferencelogicalname", "connectionid", "statecode", "statuscode"],
            filter: PACKAGED_CONNECTIONS.map((name) => `connectionreferencelogicalname eq '${name}'`).join(" or "),
            top: PACKAGED_CONNECTIONS.length,
          }),
        ])),
      ]);

      assignResult(coreResults[0], "sync", next, (result) => {
        next.syncStates = (result.data ?? []) as unknown as Pvci_syncstates[];
      });
      assignResult(coreResults[1], "central", next, (result) => {
        next.environments = result;
      });
      assignResult(coreResults[2], "inventory", next, (result) => {
        next.inventoryRuns = (result.data ?? []) as unknown as Pvci_inventorysyncruns[];
      });
      assignResult(coreResults[3], "access", next, (result) => {
        next.accessRequests = (result.data ?? []) as unknown as Pvci_transcriptaccessrequests[];
      });
      assignResult(coreResults[4], "configuration", next, ([workflowResult, connectionResult]) => {
        next.workflows = (workflowResult.data ?? []) as unknown as Workflows[];
        next.connectionReferences = (connectionResult.data ?? []) as unknown as Connectionreferences[];
      });

      if (next.creditsInstalled) {
        const creditResults = await Promise.allSettled([
          withEvidenceTimeout(Pvci_creditsyncrunsService.getAll({
            select: ["pvci_creditsyncrunid", "pvci_name", "pvci_startedon", "pvci_completedon", "pvci_status", "pvci_sourcecount", "pvci_rejectedcount", "pvci_error"],
            orderBy: ["pvci_startedon desc"],
            top: 10,
          })),
          withEvidenceTimeout(Pvci_governancesyncrunsService.getAll({
            select: ["pvci_governancesyncrunid", "pvci_name", "pvci_startedon", "pvci_completedon", "pvci_status", "pvci_thresholdcount", "pvci_rejectedcount", "pvci_error"],
            orderBy: ["pvci_startedon desc"],
            top: 10,
          })),
          withEvidenceTimeout(Pvci_thresholdchangerequestsService.getAll({
            select: ["pvci_thresholdchangerequestid", "pvci_name", "pvci_status", "pvci_requestedon", "pvci_processedon", "pvci_error"],
            orderBy: ["pvci_requestedon desc"],
            top: 25,
          })),
        ]);
        assignResult(creditResults[0], "credit", next, (result) => {
          next.creditRuns = (result.data ?? []) as unknown as Pvci_creditsyncruns[];
        });
        assignResult(creditResults[1], "governance", next, (result) => {
          next.governanceRuns = (result.data ?? []) as unknown as Pvci_governancesyncruns[];
        });
        assignResult(creditResults[2], "threshold", next, (result) => {
          next.thresholdRequests = (result.data ?? []) as unknown as Pvci_thresholdchangerequests[];
        });
      }

      const refreshedAt = new Date();
      next.refreshedOn = refreshedAt.toISOString();
      next.evaluatedAt = refreshedAt.getTime();
      if (!cancelled) {
        setData(next);
        setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [refreshVersion]);

  useEffect(() => {
    const handleVisibility = () => {
      const visible = document.visibilityState === "visible";
      setPageVisible(visible);
      if (visible && autoRefresh) setRefreshVersion((current) => current + 1);
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [autoRefresh]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") setRefreshVersion((current) => current + 1);
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [autoRefresh]);

  const rows = useMemo(() => buildRows(data, data.evaluatedAt), [data]);
  const exceptionRows = rows.filter(rowNeedsReview);
  const selected = rows.find((row) => row.id === selectedId)
    ?? exceptionRows.sort((left, right) => statePriority(left.assessment.state) - statePriority(right.assessment.state))[0]
    ?? rows[0];
  const stateCounts = countStates(rows);
  const configurationIssueCount = rows.filter((row) => configurationNeedsReview(row.configuration)).length;
  const filteredRows = rows.filter((row) => matchesOperationsFilter(row, filter));
  const initialLoading = loading && !data.refreshedOn;
  const selectedFlowUrl = selected ? buildFlowDetailsUrl(hostEnvironmentId, selected.flowId) : undefined;

  const refresh = () => {
    setLoading(true);
    setRefreshVersion((current) => current + 1);
  };

  const review = (rowId: string) => {
    setSelectedId(rowId);
    setCopyStatus("idle");
    requestAnimationFrame(() => reviewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const copyDiagnostics = async () => {
    if (!selected) return;
    try {
      if (!navigator.clipboard) throw new Error("Clipboard API unavailable");
      await navigator.clipboard.writeText(buildFlowDiagnosticText({
        generatedOn: new Date().toISOString(),
        flowName: selected.name,
        flowId: selected.flowId,
        environmentId: hostEnvironmentId,
        solution: selected.solution,
        cadence: selected.cadence,
        state: selected.assessment.state,
        summary: selected.assessment.summary,
        configurationState: selected.configuration.state,
        configurationSummary: selected.configuration.summary,
        missingConnections: selected.configuration.missingConnections,
        latestEvidenceOn: selected.assessment.latestOn,
        lastAttemptOn: selected.history.lastAttemptOn,
        lastSuccessOn: selected.history.lastSuccessOn,
        consecutiveFailures: selected.historyCoverage === "runs" || selected.historyCoverage === "requests"
          ? selected.history.consecutiveFailures
          : undefined,
        pendingCount: selected.queue?.pendingCount,
        overdueCount: selected.queue?.overdueCount,
        error: selected.assessment.error,
        flowUrl: selectedFlowUrl,
      }));
      setCopyStatus("copied");
    } catch {
      setCopyStatus("error");
    }
  };

  return (
    <div className="operations-overview">
      <header className="operations-title">
        <div>
          <span className="report-eyebrow">Operational control plane</span>
          <h2>Telemetry flow operations</h2>
          <p>Health, freshness, and retained execution evidence for every packaged collector and request processor.</p>
        </div>
        <div className="operations-refresh-group">
          <span>Checked {formatDateTime(data.refreshedOn)}</span>
          <label className="operations-auto-refresh" title="Refresh retained evidence every 60 seconds while this page is visible.">
            <input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} />
            {autoRefresh ? pageVisible ? "Auto · 60s" : "Auto paused" : "Auto off"}
          </label>
          <button type="button" className="inventory-refresh" disabled={loading} onClick={refresh} title="Reload operational evidence">
            <span aria-hidden="true">↻</span> {loading ? "Refreshing" : "Refresh evidence"}
          </button>
        </div>
      </header>

      <section className={`operations-decision ${initialLoading ? "attention" : exceptionRows.some((row) => row.assessment.state === "failed") ? "failed" : exceptionRows.length ? "attention" : "healthy"}`} aria-live="polite">
        <div>
          <span className="report-eyebrow">Current decision</span>
          <strong>{initialLoading
            ? "Loading operational evidence"
            : exceptionRows.length
              ? `${exceptionRows.length} of ${rows.length} flows need review`
              : "All installed flows have current healthy evidence"}</strong>
          <p>{initialLoading
            ? "Reading each retained run and status source. No health conclusion is available yet."
            : selected && exceptionRows.includes(selected)
              ? `${selected.name}: ${rowExceptionSummary(selected)}`
              : "No current flow exception is retained in Dataverse."}</p>
        </div>
        {!initialLoading && selected?.destination && exceptionRows.includes(selected) && (
          <button type="button" className="privacy-action" onClick={() => onNavigate(selected.destination!)}>
            {selected.nextStep}
          </button>
        )}
      </section>

      {!initialLoading && <>
      <section className="operations-kpis" aria-label="Flow health summary">
        <OperationKpi label="Healthy" value={stateCounts.healthy} tone="good" />
        <OperationKpi label="Failed" value={stateCounts.failed} tone="bad" />
        <OperationKpi label="Overdue" value={stateCounts.stale} tone="warn" />
        <OperationKpi label="Attention" value={stateCounts.attention} tone="warn" />
        <OperationKpi label="Unknown" value={stateCounts.unknown} />
        <OperationKpi label="Unavailable" value={stateCounts.unavailable} />
        <OperationKpi label="Not installed" value={stateCounts["not-installed"]} />
        <OperationKpi label="Configuration" value={configurationIssueCount} tone={configurationIssueCount ? "warn" : "good"} />
      </section>

      {selected && (
        <section className="operations-detail" ref={reviewRef} aria-label={`${selected.name} evidence`}>
          <header>
            <div>
              <span className="report-eyebrow">Selected capability</span>
              <h3>{selected.name}</h3>
            </div>
            <OperationStatus assessment={selected.assessment} />
          </header>
          {(selected.assessment.error || selected.assessment.state === "failed") && (
            <div className="operations-detail-error">
              <strong>Impact</strong>
              <span>{selected.impact}</span>
              {selected.assessment.error && <code>{selected.assessment.error}</code>}
            </div>
          )}
          <div className="operations-detail-actions">
            <p><strong>Recommended action:</strong> {selected.nextStep}.</p>
            <div className="operations-detail-buttons">
              {selected.destination && <button type="button" className="privacy-action" onClick={() => onNavigate(selected.destination!)}>{selected.nextStep}</button>}
              <button type="button" className="flow-direct-link" onClick={() => void copyDiagnostics()}>Copy diagnostics</button>
              {selectedFlowUrl
                ? <a className="flow-direct-link" href={selectedFlowUrl} target="_blank" rel="noreferrer" aria-label={`Open ${selected.name} in Power Automate`}>Open flow</a>
                : <span className="muted small" title="The Power Apps host environment is not available.">Flow link unavailable</span>}
            </div>
          </div>
          {copyStatus !== "idle" && <p className={`operations-copy-status ${copyStatus}`} role="status">{copyStatus === "copied" ? "Diagnostics copied" : "Diagnostics could not be copied"}</p>}
          <dl className="operations-evidence-summary">
            <EvidenceFact label="Configuration" value={selected.configuration.summary} tone={configurationNeedsReview(selected.configuration) ? "warn" : undefined} />
            <EvidenceFact label="Last attempt" value={formatDateTime(selected.history.lastAttemptOn)} />
            <EvidenceFact label="Last success" value={formatDateTime(selected.history.lastSuccessOn)} />
            <EvidenceFact
              label="Failure streak"
              value={selected.historyCoverage === "latest-only" || selected.historyCoverage === "sources"
                ? "Not retained"
                : String(selected.history.consecutiveFailures)}
              tone={selected.history.consecutiveFailures > 0 ? "bad" : undefined}
            />
            <EvidenceFact label="Latest duration" value={formatDuration(selected.history.latestDurationMs)} />
            <EvidenceFact label="Success baseline" value={formatDuration(selected.history.successfulDurationBaselineMs)} />
            <EvidenceFact
              label="Duration change"
              value={formatDurationRegression(selected.history.durationRegressionRatio)}
              tone={(selected.history.durationRegressionRatio ?? 0) >= 1.5 ? "warn" : undefined}
            />
            {selected.queue && <EvidenceFact label="Pending requests" value={String(selected.queue.pendingCount)} tone={selected.queue.pendingCount ? "warn" : undefined} />}
            {selected.queue && <EvidenceFact label="Overdue requests" value={String(selected.queue.overdueCount)} tone={selected.queue.overdueCount ? "bad" : undefined} />}
          </dl>
          <h4>Recent retained evidence</h4>
          <RunHistoryStrip evidence={selected.evidence} />
          <div className="operations-history">
            {!selected.evidence.length && <p className="muted">No execution history is retained for this capability.</p>}
            {selected.evidence.map((item) => (
              <div key={item.id} className="operations-history-row">
                <span>{formatDateTime(item.at)}</span>
                <OperationStatus assessment={{ state: statusState(item.status), summary: item.status ?? "Unknown" }} compact />
                <span>{item.detail}{item.durationMs != null ? ` · ${formatDuration(item.durationMs)}` : ""}</span>
                {item.error && <code>{item.error}</code>}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="operations-trigger-boundary" aria-label="Manual run availability">
        <div>
          <strong>Manual run is not available from the app yet</strong>
          <span>The packaged flows use recurrence triggers and expose no audited Power Apps run command. Refresh reloads evidence only; it does not start a flow.</span>
        </div>
        <span className="conf none">recurrence only</span>
      </section>

      <div className="operations-toolbar">
        <div className="segmented operations-filters" aria-label="Filter flow operations">
          {([
            ["all", "All"],
            ["review", "Needs review"],
            ["failed", "Failed / overdue"],
            ["pending", "Pending"],
            ["core", "Core"],
            ["credits", "Credits"],
          ] as Array<[OperationsFilter, string]>).map(([value, label]) => (
            <button key={value} type="button" className={filter === value ? "on" : ""} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>
          ))}
        </div>
        <span className="muted small">{filteredRows.length} of {rows.length} flows</span>
      </div>

      <div className="operations-table-wrap">
        <table className="runtable operations-table">
          <thead><tr><th>Flow capability</th><th>Package</th><th>Cadence</th><th>Configuration</th><th>Status</th><th>Latest evidence</th><th>Result</th><th>Action</th></tr></thead>
          <tbody>
            {!filteredRows.length && <tr><td colSpan={8} className="muted">No flows match this filter.</td></tr>}
            {filteredRows.map((row) => {
              const flowUrl = buildFlowDetailsUrl(hostEnvironmentId, row.flowId);
              return <tr key={row.id} className={selected?.id === row.id ? "selected" : undefined}>
                <td data-label="Flow capability"><strong>{row.name}</strong><span>{row.purpose}</span></td>
                <td data-label="Package">{row.solution}</td>
                <td data-label="Cadence">{row.cadence}</td>
                <td data-label="Configuration"><ConfigurationStatus assessment={row.configuration} /></td>
                <td data-label="Status"><OperationStatus assessment={row.assessment} /></td>
                <td data-label="Latest evidence">{formatDateTime(row.assessment.latestOn)}</td>
                <td data-label="Result" title={row.assessment.error}><span>{row.assessment.summary}</span>{row.assessment.error && <small>{row.assessment.error}</small>}</td>
                <td data-label="Action"><div className="operations-row-actions">
                  <button type="button" className="onboarding-link" onClick={() => review(row.id)}>Review</button>
                  {flowUrl
                    ? <a className="onboarding-link" href={flowUrl} target="_blank" rel="noreferrer" aria-label={`Open ${row.name} in Power Automate`}>Open flow</a>
                    : <span className="muted small">Flow link unavailable</span>}
                </div></td>
              </tr>;
            })}
          </tbody>
        </table>
      </div>
      </>}
    </div>
  );
}

function buildRows(data: OperationsData, now: number): OperationRow[] {
  const syncState = data.syncStates[0];
  const inventoryRun = data.inventoryRuns[0];
  const creditRun = data.creditRuns[0];
  const governanceRun = data.governanceRuns[0];
  const syncHistoryRuns: FlowRunEvidence[] = syncState ? [{
    status: syncState.pvci_lastrunstatus,
    completedOn: syncState.pvci_lastrunon,
  }] : [];
  const centralHistoryRuns: FlowRunEvidence[] = data.environments
    .filter((row) => row.pvci_transcriptcollectorenabled)
    .map((row) => ({ status: row.pvci_transcriptlastcollectionstatus, completedOn: row.pvci_transcriptlastcollectedon }));
  const inventoryHistoryRuns: FlowRunEvidence[] = data.inventoryRuns.map((run) => toRunEvidence(
    run.pvci_status, run.pvci_startedon, run.pvci_completedon,
  ));
  const accessHistoryRuns: FlowRunEvidence[] = data.accessRequests.map((request) => ({
    status: request.pvci_status,
    startedOn: request.pvci_requestedon,
    completedOn: request.pvci_processedon,
    durationMs: durationBetween(request.pvci_requestedon, request.pvci_processedon),
  }));
  const creditHistoryRuns: FlowRunEvidence[] = data.creditRuns.map((run) => toRunEvidence(
    run.pvci_status, run.pvci_startedon, run.pvci_completedon,
  ));
  const governanceHistoryRuns: FlowRunEvidence[] = data.governanceRuns.map((run) => toRunEvidence(
    run.pvci_status, run.pvci_startedon, run.pvci_completedon,
  ));
  const thresholdHistoryRuns: FlowRunEvidence[] = data.thresholdRequests.map((request) => ({
    status: request.pvci_status,
    startedOn: request.pvci_requestedon,
    completedOn: request.pvci_processedon,
    durationMs: durationBetween(request.pvci_requestedon, request.pvci_processedon),
  }));
  const accessQueue = summarizeRequestQueue(data.accessRequests.map((request) => ({
    status: request.pvci_status,
    requestedOn: request.pvci_requestedon,
    processedOn: request.pvci_processedon,
  })), now, PROCESSOR_OVERDUE_AFTER);
  const thresholdQueue = summarizeRequestQueue(data.thresholdRequests.map((request) => ({
    status: request.pvci_status,
    requestedOn: request.pvci_requestedon,
    processedOn: request.pvci_processedon,
  })), now, PROCESSOR_OVERDUE_AFTER);
  const creditCapabilityUnavailable = data.creditsInstalled == null;
  const mappedConnections = new Set(data.connectionReferences
    .filter((reference) => reference.connectionid && reference.statecode === 0)
    .map((reference) => reference.connectionreferencelogicalname));
  const configurationFor = (flowId: string, requiredConnections: string[], optional = false): FlowConfigurationAssessment => {
    if (optional && data.creditsInstalled === false) return { state: "not-installed", summary: "Optional Credits add-on is not installed", missingConnections: [] };
    if (data.errors.configuration) return { state: "unavailable", summary: "Configuration evidence could not be read", missingConnections: [] };
    const workflow = data.workflows.find((row) => row.workflowid.toLowerCase() === flowId);
    return assessFlowConfiguration(workflow?.statecode, workflow?.statuscode, requiredConnections, mappedConnections);
  };
  const optionalAssessment = (source: EvidenceSource, assessment: () => FlowOperationAssessment) => {
    if (data.errors[source]) return unavailableAssessment(data.errors[source]);
    if (creditCapabilityUnavailable) return unavailableAssessment(data.errors["credits-capability"]);
    if (!data.creditsInstalled) return notInstalledAssessment();
    return assessment();
  };

  const rows: OperationRow[] = [
    {
      id: "transcript-sync",
      flowId: "eee71534-988d-f111-8077-7ced8d95b46e",
      name: "Sync Conversation Transcripts",
      solution: "Core",
      cadence: "Hourly",
      purpose: "Imports local conversation transcripts and updates the incremental watermark.",
      impact: "New local sessions can stop appearing in analysis until transcript synchronization recovers.",
      nextStep: "Review transcript sync state with an administrator",
      assessment: data.errors.sync
        ? unavailableAssessment(data.errors.sync)
        : assessScheduledRun(syncState && {
            status: syncState.pvci_lastrunstatus,
            completedOn: syncState.pvci_lastrunon,
            processedCount: syncState.pvci_recordsprocessed,
            error: syncState.pvci_lasterror,
          }, now, HOURLY_STALE_AFTER),
          configuration: configurationFor("eee71534-988d-f111-8077-7ced8d95b46e", ["pvci_dataversesync"]),
      history: summarizeRunHistory(syncHistoryRuns),
      historyCoverage: "latest-only",
      evidence: syncState ? [{
        id: syncState.pvci_syncstateid,
        startedOn: syncState.pvci_lastrunon,
        at: syncState.pvci_lastrunon,
        status: syncState.pvci_lastrunstatus,
        detail: countLabel(syncState.pvci_recordsprocessed, "record processed", "records processed"),
        error: syncState.pvci_lasterror,
      }] : [],
    },
    {
      id: "central-transcripts",
      flowId: "371b3cad-8596-f111-8076-7ced8d95b46e",
      name: "Collect Central Transcripts",
      solution: "Core",
      cadence: "Hourly",
      purpose: "Collects bounded transcript batches from enabled remote environments.",
      impact: "Remote source sessions can become stale or remain unavailable in the collector environment.",
      nextStep: "Open Inventory",
      destination: "inventory",
      assessment: data.errors.central
        ? unavailableAssessment(data.errors.central)
        : assessCentralCollection(data.environments.map((row) => ({
            enabled: row.pvci_transcriptcollectorenabled,
            status: row.pvci_transcriptlastcollectionstatus,
            completedOn: row.pvci_transcriptlastcollectedon,
            batchCount: row.pvci_transcriptlastbatchcount,
            error: row.pvci_transcriptlastcollectionerror,
          })), now, HOURLY_STALE_AFTER),
          configuration: configurationFor("371b3cad-8596-f111-8076-7ced8d95b46e", ["pvci_centralcollector"]),
      history: summarizeProjectionHistory(centralHistoryRuns),
      historyCoverage: "sources",
      evidence: data.environments.filter((row) => row.pvci_transcriptcollectorenabled).map((row) => ({
        id: row.pvci_environmentinventoryid,
        startedOn: row.pvci_transcriptlastcollectedon,
        at: row.pvci_transcriptlastcollectedon,
        status: row.pvci_transcriptlastcollectionstatus,
        detail: `${row.pvci_displayname ?? row.pvci_environmentid ?? "Unknown environment"} · ${countLabel(row.pvci_transcriptlastbatchcount, "record", "records")}`,
        error: row.pvci_transcriptlastcollectionerror,
      })),
    },
    {
      id: "tenant-inventory",
      flowId: "320f4f61-b895-f111-8076-7ced8d95b46e",
      name: "Collect Tenant Agent Inventory",
      solution: "Core",
      cadence: "Daily",
      purpose: "Discovers tenant environments and Copilot Studio agents used by operational views.",
      impact: "Environment and agent readiness can be stale, so collection and credit scope decisions may be wrong.",
      nextStep: "Open Inventory",
      destination: "inventory",
      assessment: data.errors.inventory
        ? unavailableAssessment(data.errors.inventory)
        : assessScheduledRun(inventoryRun && {
            status: inventoryRun.pvci_status,
            completedOn: inventoryRun.pvci_completedon,
            startedOn: inventoryRun.pvci_startedon,
            processedCount: inventoryRun.pvci_agentcount,
            rejectedCount: inventoryRun.pvci_rejectedcount,
            error: inventoryRun.pvci_error,
          }, now, DAILY_STALE_AFTER),
          configuration: configurationFor("320f4f61-b895-f111-8076-7ced8d95b46e", ["pvci_powerplatformadminv2", "pvci_dataversesync"]),
      history: summarizeRunHistory(inventoryHistoryRuns),
      historyCoverage: "runs",
      evidence: data.inventoryRuns.map((run) => ({
        id: run.pvci_inventorysyncrunid,
        startedOn: run.pvci_startedon,
        at: run.pvci_completedon ?? run.pvci_startedon,
        status: run.pvci_status,
        durationMs: durationBetween(run.pvci_startedon, run.pvci_completedon),
        detail: `${countLabel(run.pvci_environmentcount, "environment", "environments")} · ${countLabel(run.pvci_agentcount, "agent", "agents")}`,
        error: run.pvci_error,
      })),
    },
    {
      id: "source-verification",
      flowId: "f324dbaa-6e9d-f111-b8de-7ced8d95b46e",
      name: "Verify Transcript Source Access",
      solution: "Core",
      cadence: "Every minute",
      purpose: "Processes queued source-access verification requests.",
      impact: "Sources can remain blocked in onboarding and cannot be enabled for central collection.",
      nextStep: "Open Inventory",
      destination: "inventory",
      assessment: data.errors.access
        ? unavailableAssessment(data.errors.access)
        : assessRequestProcessor(data.accessRequests.map((request) => ({
            status: request.pvci_status,
            requestedOn: request.pvci_requestedon,
            processedOn: request.pvci_processedon,
            error: request.pvci_error,
          })), now, PROCESSOR_OVERDUE_AFTER),
          configuration: configurationFor("f324dbaa-6e9d-f111-b8de-7ced8d95b46e", ["pvci_centralcollector"]),
      history: summarizeRunHistory(accessHistoryRuns),
      historyCoverage: "requests",
      queue: accessQueue,
      evidence: data.accessRequests.map((request) => ({
        id: request.pvci_transcriptaccessrequestid,
        startedOn: request.pvci_requestedon,
        at: request.pvci_processedon ?? request.pvci_requestedon,
        status: request.pvci_status,
        durationMs: durationBetween(request.pvci_requestedon, request.pvci_processedon),
        detail: `${request.pvci_name} · ${request.pvci_accessstatus ?? "access result pending"}`,
        error: request.pvci_error,
      })),
    },
    {
      id: "credit-usage",
      flowId: "0bfaa799-f094-f111-8076-7ced8d95b46e",
      name: "Collect Copilot Credit Usage",
      solution: "Credits",
      cadence: "Daily",
      purpose: "Imports tenant credit usage, capacity, and attribution evidence.",
      impact: "Credit usage and capacity decisions can be based on stale or incomplete evidence.",
      nextStep: "Open Credits",
      destination: "credits",
      assessment: optionalAssessment("credit", () => assessScheduledRun(creditRun && {
        status: creditRun.pvci_status,
        completedOn: creditRun.pvci_completedon,
        startedOn: creditRun.pvci_startedon,
        processedCount: creditRun.pvci_sourcecount,
        rejectedCount: creditRun.pvci_rejectedcount,
        error: creditRun.pvci_error,
      }, now, DAILY_STALE_AFTER)),
      configuration: configurationFor("0bfaa799-f094-f111-8076-7ced8d95b46e", ["pvci_licensinghttp", "pvci_dataversesync"], true),
      history: summarizeRunHistory(creditHistoryRuns),
      historyCoverage: "runs",
      evidence: data.creditRuns.map((run) => ({
        id: run.pvci_creditsyncrunid,
        startedOn: run.pvci_startedon,
        at: run.pvci_completedon ?? run.pvci_startedon,
        status: run.pvci_status,
        durationMs: durationBetween(run.pvci_startedon, run.pvci_completedon),
        detail: countLabel(run.pvci_sourcecount, "source row", "source rows"),
        error: run.pvci_error,
      })),
    },
    {
      id: "credit-governance",
      flowId: "1afedf5c-1396-f111-8076-7ced8d95b46e",
      name: "Collect Credit Governance",
      solution: "Credits",
      cadence: "Daily",
      purpose: "Collects resource thresholds and governance configuration.",
      impact: "Threshold controls and over-capacity decisions can be stale or incomplete.",
      nextStep: "Open Credits",
      destination: "credits",
      assessment: optionalAssessment("governance", () => assessScheduledRun(governanceRun && {
        status: governanceRun.pvci_status,
        completedOn: governanceRun.pvci_completedon,
        startedOn: governanceRun.pvci_startedon,
        processedCount: governanceRun.pvci_thresholdcount,
        rejectedCount: governanceRun.pvci_rejectedcount,
        error: governanceRun.pvci_error,
      }, now, DAILY_STALE_AFTER)),
      configuration: configurationFor("1afedf5c-1396-f111-8076-7ced8d95b46e", ["pvci_powerplatformapi", "pvci_dataversesync"], true),
      history: summarizeRunHistory(governanceHistoryRuns),
      historyCoverage: "runs",
      evidence: data.governanceRuns.map((run) => ({
        id: run.pvci_governancesyncrunid,
        startedOn: run.pvci_startedon,
        at: run.pvci_completedon ?? run.pvci_startedon,
        status: run.pvci_status,
        durationMs: durationBetween(run.pvci_startedon, run.pvci_completedon),
        detail: countLabel(run.pvci_thresholdcount, "threshold", "thresholds"),
        error: run.pvci_error,
      })),
    },
    {
      id: "governance-requests",
      flowId: "c8d754c8-1896-f111-8076-7ced8d95b46e",
      name: "Apply Credit Governance Requests",
      solution: "Credits",
      cadence: "Every minute",
      purpose: "Processes audited credit-threshold change requests.",
      impact: "Approved governance changes can remain unapplied or fail validation.",
      nextStep: "Open Credits",
      destination: "credits",
      assessment: optionalAssessment("threshold", () => assessRequestProcessor(data.thresholdRequests.map((request) => ({
        status: request.pvci_status,
        requestedOn: request.pvci_requestedon,
        processedOn: request.pvci_processedon,
        error: request.pvci_error,
      })), now, PROCESSOR_OVERDUE_AFTER)),
      configuration: configurationFor("c8d754c8-1896-f111-8076-7ced8d95b46e", ["pvci_powerplatformapi", "pvci_dataversesync"], true),
      history: summarizeRunHistory(thresholdHistoryRuns),
      historyCoverage: "requests",
      queue: thresholdQueue,
      evidence: data.thresholdRequests.map((request) => ({
        id: request.pvci_thresholdchangerequestid,
        startedOn: request.pvci_requestedon,
        at: request.pvci_processedon ?? request.pvci_requestedon,
        status: request.pvci_status,
        durationMs: durationBetween(request.pvci_requestedon, request.pvci_processedon),
        detail: request.pvci_name,
        error: request.pvci_error,
      })),
    },
  ];
  return rows.map(promoteOperationalSignals);
}

function promoteOperationalSignals(row: OperationRow): OperationRow {
  if (row.assessment.state !== "healthy" || (row.history.durationRegressionRatio ?? 0) < 1.5) return row;
  return {
    ...row,
    assessment: {
      ...row.assessment,
      state: "attention",
      summary: `Latest run is ${formatDurationRegression(row.history.durationRegressionRatio).toLowerCase()} than its successful baseline`,
    },
  };
}

function matchesOperationsFilter(row: OperationRow, filter: OperationsFilter) {
  if (filter === "review") return rowNeedsReview(row);
  if (filter === "failed") return row.assessment.state === "failed" || row.assessment.state === "stale" || ["dlp-violation", "suspended"].includes(row.configuration.state);
  if (filter === "pending") return (row.queue?.pendingCount ?? 0) > 0;
  if (filter === "core") return row.solution === "Core";
  if (filter === "credits") return row.solution === "Credits";
  return true;
}

function assignResult<T>(
  result: PromiseSettledResult<T>,
  source: EvidenceSource,
  target: OperationsData,
  assign: (value: T) => void,
) {
  if (result.status === "fulfilled") assign(result.value);
  else target.errors[source] = errorMessage(result.reason);
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : String(reason);
}

async function withEvidenceTimeout<T>(promise: Promise<T>): Promise<T> {
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error("Operational evidence request timed out")), EVIDENCE_TIMEOUT_MS);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}

function countLabel(value: number | undefined, singular: string, plural: string) {
  if (value == null) return "count unavailable";
  return `${value.toLocaleString()} ${value === 1 ? singular : plural}`;
}

function formatDateTime(value?: string) {
  if (!value) return "No retained evidence";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function statusState(status?: string): FlowOperationState {
  const normalized = status?.trim().toLowerCase();
  if (["success", "succeeded", "completed", "verified", "applied"].includes(normalized ?? "")) return "healthy";
  if (["failed", "failure", "error", "rejected"].includes(normalized ?? "")) return "failed";
  if (["pending", "processing", "submitted", "in progress"].includes(normalized ?? "")) return "attention";
  return "unknown";
}

function statePriority(state: FlowOperationState) {
  return ({ failed: 0, unavailable: 1, stale: 2, attention: 3, unknown: 4, healthy: 5, "not-installed": 6 })[state];
}

function countStates(rows: OperationRow[]): Record<FlowOperationState, number> {
  const counts: Record<FlowOperationState, number> = {
    healthy: 0,
    attention: 0,
    failed: 0,
    stale: 0,
    unknown: 0,
    unavailable: 0,
    "not-installed": 0,
  };
  rows.forEach((row) => { counts[row.assessment.state] += 1; });
  return counts;
}

function OperationKpi({ label, value, tone }: { label: string; value: number; tone?: "good" | "warn" | "bad" }) {
  return <div className="kpi"><span className="kpi-label">{label}</span><span className={`kpi-value ${tone ?? ""}`}>{value}</span></div>;
}

function OperationStatus({ assessment, compact = false }: { assessment: FlowOperationAssessment; compact?: boolean }) {
  const label = assessment.state === "not-installed" ? "Not installed" : assessment.state;
  return <span className={`operation-state ${assessment.state}${compact ? " compact" : ""}`}>{label}</span>;
}

function toRunEvidence(status?: string, startedOn?: string, completedOn?: string): FlowRunEvidence {
  return { status, startedOn, completedOn, durationMs: durationBetween(startedOn, completedOn) };
}

function durationBetween(startedOn?: string, completedOn?: string) {
  if (!startedOn || !completedOn) return undefined;
  const started = Date.parse(startedOn);
  const completed = Date.parse(completedOn);
  if (Number.isNaN(started) || Number.isNaN(completed) || completed < started) return undefined;
  return completed - started;
}

function summarizeProjectionHistory(runs: FlowRunEvidence[]): FlowRunHistorySummary {
  const ordered = [...runs].sort((left, right) =>
    Date.parse(right.completedOn ?? right.startedOn ?? "") - Date.parse(left.completedOn ?? left.startedOn ?? ""));
  const successful = ordered.filter((run) => statusState(run.status) === "healthy");
  return {
    lastAttemptOn: ordered[0]?.completedOn ?? ordered[0]?.startedOn,
    lastSuccessOn: successful[0]?.completedOn ?? successful[0]?.startedOn,
    consecutiveFailures: 0,
  };
}

function formatDuration(value?: number) {
  if (value == null) return "Not retained";
  if (value < 1000) return `${Math.round(value)} ms`;
  if (value < 60_000) return `${(value / 1000).toFixed(value < 10_000 ? 1 : 0)} s`;
  return `${(value / 60_000).toFixed(1)} min`;
}

function formatDurationRegression(ratio?: number) {
  if (ratio == null) return "Not enough history";
  const percent = Math.round((ratio - 1) * 100);
  if (Math.abs(percent) < 5) return "Near baseline";
  return `${Math.abs(percent)}% ${percent > 0 ? "slower" : "faster"}`;
}

function EvidenceFact({ label, value, tone }: { label: string; value: string; tone?: "warn" | "bad" }) {
  return <div><dt>{label}</dt><dd className={tone}>{value}</dd></div>;
}

function RunHistoryStrip({ evidence }: { evidence: EvidenceItem[] }) {
  if (!evidence.length) return <p className="muted small">No retained sequence is available for this capability.</p>;
  return <div className="operations-run-strip" aria-label="Recent execution outcomes, newest first">
    {evidence.slice(0, 10).map((item) => {
      const state = statusState(item.status);
      const label = `${formatDateTime(item.at)} · ${item.status ?? "Unknown"}${item.durationMs != null ? ` · ${formatDuration(item.durationMs)}` : ""}`;
      return <span key={item.id} className={`operations-run-mark ${state}`} title={label} aria-label={label} />;
    })}
  </div>;
}

function configurationNeedsReview(assessment: FlowConfigurationAssessment) {
  return !["ready", "not-installed"].includes(assessment.state);
}

function rowNeedsReview(row: OperationRow) {
  return !["healthy", "not-installed"].includes(row.assessment.state) || configurationNeedsReview(row.configuration);
}

function rowExceptionSummary(row: OperationRow) {
  if (configurationNeedsReview(row.configuration)) return `Configuration: ${row.configuration.summary}`;
  return row.assessment.summary;
}

function ConfigurationStatus({ assessment }: { assessment: FlowConfigurationAssessment }) {
  const label = assessment.state === "not-installed" ? "Not installed" : assessment.state.replace("-", " ");
  return <span className={`configuration-state ${assessment.state}`} title={assessment.missingConnections.join(", ") || assessment.summary}>{label}</span>;
}