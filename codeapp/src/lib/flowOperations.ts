export type FlowOperationState = "healthy" | "attention" | "failed" | "stale" | "unknown" | "unavailable" | "not-installed";

export interface FlowRunEvidence {
  status?: string;
  completedOn?: string;
  startedOn?: string;
  durationMs?: number;
  processedCount?: number;
  rejectedCount?: number;
  error?: string;
}

export interface CentralCollectionEvidence {
  enabled?: boolean;
  status?: string;
  completedOn?: string;
  batchCount?: number;
  error?: string;
}

export interface RequestEvidence {
  status?: string;
  requestedOn?: string;
  processedOn?: string;
  error?: string;
}

export interface FlowOperationAssessment {
  state: FlowOperationState;
  latestOn?: string;
  summary: string;
  error?: string;
}

const SUCCESS_STATUSES = new Set(["success", "succeeded", "completed", "verified", "applied"]);
const FAILED_STATUSES = new Set(["failed", "failure", "error", "rejected"]);
const ACTIVE_REQUEST_STATUSES = new Set(["pending", "processing", "submitted", "in progress"]);

function normalizedStatus(status?: string) {
  return status?.trim().toLowerCase();
}

function timestamp(value?: string) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function isOlderThan(value: string | undefined, now: number, staleAfterMs: number) {
  const observedAt = timestamp(value);
  return observedAt == null || now - observedAt > staleAfterMs;
}

function observedCount(value: number | undefined, singular: string, plural: string) {
  if (value == null) return "count unavailable";
  return `${value.toLocaleString()} ${value === 1 ? singular : plural}`;
}

export function assessScheduledRun(
  evidence: FlowRunEvidence | null | undefined,
  now: number,
  staleAfterMs: number,
): FlowOperationAssessment {
  if (!evidence) return { state: "unknown", summary: "No run evidence" };

  const status = normalizedStatus(evidence.status);
  const latestOn = evidence.completedOn ?? evidence.startedOn;
  if (status && FAILED_STATUSES.has(status)) {
    return {
      state: "failed",
      latestOn,
      summary: observedCount(evidence.rejectedCount, "rejected record", "rejected records"),
      error: evidence.error,
    };
  }
  if (!status || !SUCCESS_STATUSES.has(status)) {
    return { state: "attention", latestOn, summary: evidence.status ?? "Run status unavailable", error: evidence.error };
  }
  if (isOlderThan(latestOn, now, staleAfterMs)) {
    return { state: "stale", latestOn, summary: `Last success is overdue · ${observedCount(evidence.processedCount, "record", "records")}` };
  }
  return { state: "healthy", latestOn, summary: observedCount(evidence.processedCount, "record", "records") };
}

export function assessCentralCollection(
  sources: CentralCollectionEvidence[],
  now: number,
  staleAfterMs: number,
): FlowOperationAssessment {
  const enabled = sources.filter((source) => source.enabled);
  if (!enabled.length) return { state: "attention", summary: "No remote sources enabled" };

  const failed = enabled.filter((source) => {
    const status = normalizedStatus(source.status);
    return Boolean(status && FAILED_STATUSES.has(status));
  });
  const latestOn = enabled
    .map((source) => source.completedOn)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1);
  if (failed.length) {
    return {
      state: "failed",
      latestOn,
      summary: `${failed.length} of ${enabled.length} enabled sources failed`,
      error: failed.find((source) => source.error)?.error,
    };
  }

  const unknown = enabled.filter((source) => !normalizedStatus(source.status));
  if (unknown.length) {
    return { state: "unknown", latestOn, summary: `${unknown.length} of ${enabled.length} enabled sources have no result` };
  }

  const stale = enabled.filter((source) => isOlderThan(source.completedOn, now, staleAfterMs));
  if (stale.length) {
    return { state: "stale", latestOn, summary: `${stale.length} of ${enabled.length} enabled sources are overdue` };
  }

  const batchCount = enabled.reduce<number | undefined>((total, source) => {
    if (source.batchCount == null) return total;
    return (total ?? 0) + source.batchCount;
  }, undefined);
  return {
    state: "healthy",
    latestOn,
    summary: `${enabled.length} enabled sources · ${observedCount(batchCount, "record in latest batches", "records in latest batches")}`,
  };
}

export function assessRequestProcessor(
  requests: RequestEvidence[],
  now: number,
  overdueAfterMs: number,
): FlowOperationAssessment {
  if (!requests.length) return { state: "unknown", summary: "No request execution evidence" };

  const sorted = [...requests].sort((left, right) =>
    (timestamp(right.requestedOn) ?? 0) - (timestamp(left.requestedOn) ?? 0));
  const active = sorted.filter((request) => ACTIVE_REQUEST_STATUSES.has(normalizedStatus(request.status) ?? ""));
  const overdue = active.filter((request) => isOlderThan(request.requestedOn, now, overdueAfterMs));
  const latest = sorted[0];
  const latestOn = latest.processedOn ?? latest.requestedOn;
  const latestStatus = normalizedStatus(latest.status);

  if (latestStatus && FAILED_STATUSES.has(latestStatus)) {
    return { state: "failed", latestOn, summary: "Latest request failed", error: latest.error };
  }
  if (overdue.length) {
    return { state: "stale", latestOn, summary: `${overdue.length} pending ${overdue.length === 1 ? "request is" : "requests are"} overdue` };
  }
  if (active.length) {
    return { state: "attention", latestOn, summary: `${active.length} ${active.length === 1 ? "request" : "requests"} in progress` };
  }
  if (latestStatus && SUCCESS_STATUSES.has(latestStatus)) {
    return { state: "healthy", latestOn, summary: "Latest request completed" };
  }
  return { state: "unknown", latestOn, summary: latest.status ?? "Request status unavailable", error: latest.error };
}

export function notInstalledAssessment(): FlowOperationAssessment {
  return { state: "not-installed", summary: "Optional Credits add-on is not installed" };
}

export function unavailableAssessment(error?: string): FlowOperationAssessment {
  return { state: "unavailable", summary: "Operational evidence could not be read", error };
}

export function buildFlowDetailsUrl(environmentId: string | undefined, flowId: string): string | undefined {
  if (!environmentId?.trim()) return undefined;
  return `https://make.powerautomate.com/environments/${encodeURIComponent(environmentId)}/flows/${encodeURIComponent(flowId)}/details`;
}

export interface FlowRunHistorySummary {
  lastAttemptOn?: string;
  lastSuccessOn?: string;
  consecutiveFailures: number;
  latestDurationMs?: number;
  successfulDurationBaselineMs?: number;
  durationRegressionRatio?: number;
}

export function summarizeRunHistory(runs: FlowRunEvidence[]): FlowRunHistorySummary {
  const ordered = [...runs].sort((left, right) =>
    (timestamp(right.completedOn ?? right.startedOn) ?? 0) - (timestamp(left.completedOn ?? left.startedOn) ?? 0));
  const lastAttempt = ordered[0];
  const lastSuccess = ordered.find((run) => SUCCESS_STATUSES.has(normalizedStatus(run.status) ?? ""));
  const consecutiveFailures = ordered.findIndex((run) => !FAILED_STATUSES.has(normalizedStatus(run.status) ?? ""));
  const latestDurationMs = lastAttempt?.durationMs;
  const priorSuccessfulDurations = ordered
    .slice(1)
    .filter((run) => SUCCESS_STATUSES.has(normalizedStatus(run.status) ?? "") && run.durationMs != null)
    .map((run) => run.durationMs!);
  const successfulDurationBaselineMs = priorSuccessfulDurations.length
    ? priorSuccessfulDurations.reduce((sum, duration) => sum + duration, 0) / priorSuccessfulDurations.length
    : undefined;
  const durationRegressionRatio = latestDurationMs != null && successfulDurationBaselineMs
    ? latestDurationMs / successfulDurationBaselineMs
    : undefined;

  return {
    lastAttemptOn: lastAttempt?.completedOn ?? lastAttempt?.startedOn,
    lastSuccessOn: lastSuccess?.completedOn ?? lastSuccess?.startedOn,
    consecutiveFailures: consecutiveFailures === -1 ? ordered.length : Math.max(consecutiveFailures, 0),
    latestDurationMs,
    successfulDurationBaselineMs,
    durationRegressionRatio,
  };
}

export interface RequestQueueSummary {
  pendingCount: number;
  overdueCount: number;
}

export function summarizeRequestQueue(
  requests: RequestEvidence[],
  now: number,
  overdueAfterMs: number,
): RequestQueueSummary {
  const active = requests.filter((request) => ACTIVE_REQUEST_STATUSES.has(normalizedStatus(request.status) ?? ""));
  return {
    pendingCount: active.length,
    overdueCount: active.filter((request) => isOlderThan(request.requestedOn, now, overdueAfterMs)).length,
  };
}

export interface FlowDiagnosticInput {
  generatedOn: string;
  flowName: string;
  flowId: string;
  environmentId?: string;
  solution: string;
  cadence: string;
  state: FlowOperationState;
  summary: string;
  configurationState?: FlowConfigurationState;
  configurationSummary?: string;
  missingConnections?: string[];
  latestEvidenceOn?: string;
  lastAttemptOn?: string;
  lastSuccessOn?: string;
  consecutiveFailures?: number;
  pendingCount?: number;
  overdueCount?: number;
  error?: string;
  flowUrl?: string;
}

export function buildFlowDiagnosticText(input: FlowDiagnosticInput): string {
  const lines = [
    "Conversation Insights · Flow diagnostics",
    `Generated (UTC): ${input.generatedOn}`,
    `Flow: ${input.flowName}`,
    `Flow ID: ${input.flowId}`,
    `Environment ID: ${input.environmentId ?? "Unavailable"}`,
    `Package: ${input.solution}`,
    `Cadence: ${input.cadence}`,
    `State: ${input.state}`,
    `Summary: ${input.summary}`,
    `Latest evidence: ${input.latestEvidenceOn ?? "Unavailable"}`,
    `Last attempt: ${input.lastAttemptOn ?? "Unavailable"}`,
    `Last success: ${input.lastSuccessOn ?? "Unavailable"}`,
  ];
  if (input.configurationState) lines.push(`Configuration: ${input.configurationState}`);
  if (input.configurationSummary) lines.push(`Configuration summary: ${input.configurationSummary}`);
  if (input.missingConnections?.length) lines.push(`Missing connections: ${input.missingConnections.join(", ")}`);
  if (input.consecutiveFailures != null) lines.push(`Consecutive failures: ${input.consecutiveFailures}`);
  if (input.pendingCount != null) lines.push(`Pending requests: ${input.pendingCount}`);
  if (input.overdueCount != null) lines.push(`Overdue requests: ${input.overdueCount}`);
  if (input.error) lines.push(`Error: ${input.error}`);
  if (input.flowUrl) lines.push(`Power Automate: ${input.flowUrl}`);
  return lines.join("\n");
}

export type FlowConfigurationState = "ready" | "disabled" | "suspended" | "dlp-violation" | "unmapped" | "unknown" | "unavailable" | "not-installed";

export interface FlowConfigurationAssessment {
  state: FlowConfigurationState;
  summary: string;
  missingConnections: string[];
}

export function assessFlowConfiguration(
  workflowState: number | undefined,
  workflowStatus: number | undefined,
  requiredConnections: string[],
  mappedConnections: Set<string>,
): FlowConfigurationAssessment {
  const missingConnections = requiredConnections.filter((name) => !mappedConnections.has(name));
  if (workflowStatus === 3) {
    return { state: "dlp-violation", summary: "Blocked by company DLP policy", missingConnections };
  }
  if (missingConnections.length) {
    return {
      state: "unmapped",
      summary: `${missingConnections.length} required ${missingConnections.length === 1 ? "connection is" : "connections are"} unmapped`,
      missingConnections,
    };
  }
  if (workflowState === 1) return { state: "ready", summary: "Activated and mapped", missingConnections };
  if (workflowState === 0) return { state: "disabled", summary: "Flow is not activated", missingConnections };
  if (workflowState === 2) return { state: "suspended", summary: "Flow is suspended", missingConnections };
  return { state: "unknown", summary: "Flow configuration state is unknown", missingConnections };
}