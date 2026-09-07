import { isFlowTelemetryAvailable } from "./flowTelemetryAvailability";
import {
  isEssSession,
  safeParse,
  sourceEnvironmentLabel,
  type KnowledgeCall,
  type SessionRow,
  type ToolCall,
  type TurnRow,
} from "./model";
import { buildReasoningPlans, type PlanEvent } from "./reasoning";
import {
  TRANSCRIPT_PRIVACY_POLICY_VERSION,
  isWorkdayHrSession,
  maskTranscriptData,
} from "./transcriptPrivacy";

/**
 * Support-evidence packaging for a single agent family. `ess` is the only family exposed today;
 * the family discriminator exists so another family can get its own workspace without changing
 * the package schema contract.
 */
export const ESS_EVIDENCE_FAMILY = "ess";
export const ESS_EVIDENCE_SCHEMA_VERSION = 1;
export const ESS_EVIDENCE_PRODUCER = "pvConversationInsightsCodeApp/ess-evidence";

const WARNING_MAX_LENGTH = 240;
const MAX_REPLAY_TURNS = 400;
const MAX_TEXT_LENGTH = 4_000;

/** Distinct attribution strengths. Never collapse these into a boolean. */
export type EvidenceState =
  | "exact"
  | "correlated"
  | "candidate"
  | "observed-zero"
  | "unknown"
  | "unavailable";

/** `not-stored` means nothing was captured; `unavailable` means something was captured but unreadable. */
export type PayloadState = "available" | "not-stored" | "unavailable";

export type EssEvidenceOutcome = "working" | "non-working";

export interface EvidenceCount {
  state: EvidenceState;
  count: number | null;
  note?: string;
}

export interface PayloadRead<T> {
  state: PayloadState;
  value: T | null;
  warning?: string;
}

export interface ChecklistItem {
  id: string;
  label: string;
  state: string;
}

export interface ExternalEvidenceItem extends ChecklistItem {
  detail: string;
}

export interface EssEvidenceContext {
  outcome: EssEvidenceOutcome;
  issueTitle: string;
  observedBehavior: string;
  expectedBehavior: string;
  referencedKnowledgeUrls: string[];
  expectedKnowledgeUrls: string[];
  investigationNotes: string;
}

export interface EssEvidenceCandidate {
  sessionId: string;
  agentName: string;
  environmentLabel: string;
  channel: string;
  startedUtc?: string;
  endedUtc?: string;
  testMode: boolean;
  outcome: string;
  outcomeReason?: string;
  userErrors: EvidenceCount;
  payloadTruncated: boolean;
  workdayHrPolicyApplies: boolean;
}

export type EssEvidencePackage = {
  schemaVersion: number;
  evidenceFamily: string;
  generation: { generatedUtc: string; producer: string; packageKind: string };
  integrity: { payloadTruncated: boolean; replayTruncatedByExport: boolean; warnings: string[] };
  analystContext: Record<string, unknown>;
  provenance: Record<string, unknown>;
  timestamps: Record<string, unknown>;
  conversation: Record<string, unknown>;
  evidence: Record<string, unknown>;
  telemetryAvailability: Record<string, unknown>;
  completeness: { checklist: ChecklistItem[]; missingExternalEvidence: ExternalEvidenceItem[] };
  privacy: {
    maskingApplied: boolean;
    maskedByDefault: boolean;
    independentOfOnScreenReveal: boolean;
    detectorPolicy: { id: string; scope: string };
    workdayHrSession: boolean;
    replacementCount: number;
    categoryCounts: Record<string, number>;
    excludedFields: string[];
  };
};

type EssEvidenceDraft = Omit<EssEvidencePackage, "privacy">;

export interface EssEvidencePackageInput {
  session: SessionRow;
  detail: SessionRow | null;
  turns: TurnRow[];
  context: EssEvidenceContext;
  generatedUtc: string;
  hostEnvironmentId?: string;
}

export const EMPTY_ESS_EVIDENCE_CONTEXT: EssEvidenceContext = {
  outcome: "non-working",
  issueTitle: "",
  observedBehavior: "",
  expectedBehavior: "",
  referencedKnowledgeUrls: [],
  expectedKnowledgeUrls: [],
  investigationNotes: "",
};

export type NarrativeFieldKey = "issueTitle" | "observedBehavior" | "expectedBehavior";

export interface NarrativeField {
  key: NarrativeFieldKey;
  label: string;
  optionalHint?: string;
  placeholder: string;
  help: string;
  required: boolean;
  multiline: boolean;
}

/** A working example has no problem statement, so expected behavior stops being required. */
export function narrativeFields(outcome: EssEvidenceOutcome): NarrativeField[] {
  const working = outcome === "working";
  return [
    {
      key: "issueTitle",
      label: working ? "Example title" : "Issue title",
      placeholder: working ? "Short summary of what went well" : "Short summary of the problem",
      help: "Add a one-line summary so support can identify this example.",
      required: true,
      multiline: false,
    },
    {
      key: "observedBehavior",
      label: working ? "Behavior observed" : "Observed behavior",
      placeholder: working ? "What the agent did correctly" : "What the agent actually did",
      help: working
        ? "Describe what the agent did correctly in this session."
        : "Describe what the agent actually did in this session.",
      required: true,
      multiline: true,
    },
    {
      key: "expectedBehavior",
      label: "Expected behavior",
      optionalHint: working ? "optional for a working example" : undefined,
      placeholder: working ? "Only if the ideal answer still differs in some detail" : "What the agent should have done",
      help: "Describe what the agent should have done instead.",
      required: !working,
      multiline: true,
    },
  ];
}

export function missingNarrativeFields(context: EssEvidenceContext): NarrativeField[] {
  return narrativeFields(context.outcome).filter((field) => field.required && !context[field.key].trim());
}

/**
 * Evidence the app cannot produce. It is always reported so a support package never implies the
 * absence of a screenshot or HAR means the artefact was checked and found clean.
 */
const EXTERNAL_EVIDENCE_ITEMS: ExternalEvidenceItem[] = [
  {
    id: "response-screenshot",
    label: "Response screenshot",
    state: "missing-external",
    detail: "Not capturable from stored transcript data. Attach a screenshot of the agent response separately.",
  },
  {
    id: "referenced-source-screenshot",
    label: "Referenced source screenshot",
    state: "missing-external",
    detail: "Not capturable from stored transcript data. Attach a screenshot of the source the agent cited.",
  },
  {
    id: "referenced-source-document-copy",
    label: "Referenced source document copy",
    state: "missing-external",
    detail: "Not capturable from stored transcript data. Attach the document the agent cited.",
  },
  {
    id: "expected-source-screenshot",
    label: "Expected source screenshot",
    state: "missing-external",
    detail: "Not capturable from stored transcript data. Attach a screenshot of the source that should have been cited.",
  },
  {
    id: "expected-source-document-copy",
    label: "Expected source document copy",
    state: "missing-external",
    detail: "Not capturable from stored transcript data. Attach the document that should have been cited.",
  },
  {
    id: "citation-har-capture",
    label: "HAR capture for citation issues",
    state: "missing-external",
    detail: "Not capturable from stored transcript data. Record a browser HAR while reproducing the citation issue.",
  },
  {
    id: "debug-conversation-id",
    label: "Exact Debug conversation ID",
    state: "unverified",
    detail: "The stored native transcript ID is not proven to be the maker Debug conversation ID. Confirm the Debug ID in Copilot Studio and attach it.",
  },
];

export function isEssEvidenceSession(session: SessionRow): boolean {
  return isEssSession(session);
}

export function selectEssEvidenceSessions(sessions: SessionRow[]): SessionRow[] {
  return sessions.filter(isEssEvidenceSession);
}

/** Activation depends on collected transcript sessions only, never on inventory or credit evidence. */
export function hasEssEvidence(sessions: SessionRow[]): boolean {
  return sessions.some(isEssEvidenceSession);
}

/** Returns the session only when it still qualifies, so a non-ESS row can never become selected. */
export function selectEssEvidenceSession(sessions: SessionRow[], sessionId: string | null): SessionRow | null {
  if (!sessionId) return null;
  return selectEssEvidenceSessions(sessions)
    .find((session) => session.pvci_transcriptsessionid === sessionId) ?? null;
}

/** Closes the workspace safely when qualifying evidence disappears after a refresh or scope change. */
export function resolveViewAfterEssEvidenceChange<TView extends string>(
  current: TView,
  available: boolean,
  essView: TView,
  fallbackView: TView,
): TView {
  return current === essView && !available ? fallbackView : current;
}

export function describeEssEvidenceCandidate(session: SessionRow): EssEvidenceCandidate {
  return {
    sessionId: session.pvci_transcriptsessionid,
    agentName: session.pvci_botname?.trim() || "Unknown ESS agent",
    environmentLabel: sourceEnvironmentLabel(session),
    channel: session.pvci_channel?.trim() || "Unknown channel",
    startedUtc: session.pvci_startdatetimeutc,
    endedUtc: session.pvci_enddatetimeutc,
    testMode: Boolean(session.pvci_istestmode),
    outcome: session.pvci_sessionoutcome?.trim() || "Outcome unavailable",
    outcomeReason: session.pvci_outcomereason,
    userErrors: countEvidence(session.pvci_usererrorcount, "exact"),
    payloadTruncated: Boolean(session.pvci_payloadtruncated),
    workdayHrPolicyApplies: isWorkdayHrSession(session),
  };
}

export interface EssEvidenceFilters {
  search: string;
  agent: string;
  environment: string;
  mode: "*" | "test" | "production";
  errorsOnly: boolean;
}

export const EMPTY_ESS_EVIDENCE_FILTERS: EssEvidenceFilters = {
  search: "",
  agent: "*",
  environment: "*",
  mode: "*",
  errorsOnly: false,
};

export function isEssEvidenceFilterActive(filters: EssEvidenceFilters): boolean {
  return Boolean(filters.search.trim())
    || filters.agent !== "*"
    || filters.environment !== "*"
    || filters.mode !== "*"
    || filters.errorsOnly;
}

export function filterEssEvidenceCandidates(
  candidates: EssEvidenceCandidate[],
  filters: EssEvidenceFilters,
): EssEvidenceCandidate[] {
  const query = filters.search.trim().toLowerCase();
  return candidates.filter((row) => {
    if (filters.agent !== "*" && row.agentName !== filters.agent) return false;
    if (filters.environment !== "*" && row.environmentLabel !== filters.environment) return false;
    if (filters.mode === "test" && !row.testMode) return false;
    if (filters.mode === "production" && row.testMode) return false;
    if (filters.errorsOnly && !(row.userErrors.count && row.userErrors.count > 0)) return false;
    if (!query) return true;
    // Deliberately excludes conversation text so the picker cannot surface transcript content.
    return [row.agentName, row.environmentLabel, row.channel, row.outcome, row.outcomeReason, row.startedUtc, row.sessionId]
      .some((value) => (value ?? "").toLowerCase().includes(query));
  });
}

export function essEvidenceFilename(sessionId: string, issueTitle: string, generatedUtc: string): string {  const slug = slugify(issueTitle) || "untitled-issue";
  const safeSessionId = sessionId.replace(/[^a-z0-9-]/gi, "").slice(0, 12).replace(/^-+|-+$/g, "") || "session";
  const stamp = generatedUtc.replace(/[^0-9]/g, "").slice(0, 14) || "00000000000000";
  return `ess-evidence-${slug}-${safeSessionId}-${stamp}.json`;
}

export function buildEssEvidencePackage(input: EssEvidencePackageInput): EssEvidencePackage {
  const { session, detail, turns, context, generatedUtc, hostEnvironmentId } = input;
  if (!isEssEvidenceSession(session)) {
    throw new Error("Only ESS-classified transcript sessions can be packaged as ESS evidence.");
  }

  const merged: SessionRow = detail ? { ...session, ...detail } : session;
  const warnings: string[] = [];

  if (merged.pvci_payloadtruncated) {
    warnings.push("The stored transcript payload is truncated. Evidence in this package may be incomplete.");
  }

  const planEvents = readPayload<PlanEvent[]>(merged.pvci_planeventsjson, "Plan events");
  const knowledge = readPayload<KnowledgeCall[]>(merged.pvci_knowledgecallsjson, "Knowledge calls");
  const tools = readPayload<ToolCall[]>(merged.pvci_toolcallsjson, "Tool calls");
  const flows = readPayload<Array<Record<string, unknown>>>(merged.pvci_flowrunsjson, "Candidate flow runs");
  const conversationPayload = readPayload<unknown>(merged.pvci_conversationjson, "Conversation JSON");
  const activitiesPayload = readPayload<unknown>(merged.pvci_activitiesjson, "Activities JSON");

  [planEvents, knowledge, tools, flows, conversationPayload, activitiesPayload]
    .forEach((payload) => { if (payload.warning) warnings.push(payload.warning); });

  const knowledgeCalls = asArray(knowledge.value);
  const toolCalls = asArray(tools.value);
  const flowRuns = asArray(flows.value);
  const flowTelemetryAvailable = isFlowTelemetryAvailable(session, hostEnvironmentId);
  const exactToolTelemetry = Boolean(session.pvci_istestmode);

  const replayTurns = turns.slice(0, MAX_REPLAY_TURNS);
  const replayTruncated = turns.length > replayTurns.length;
  if (replayTruncated) {
    warnings.push(`Conversation replay was limited to the first ${MAX_REPLAY_TURNS} of ${turns.length} retained turns.`);
  }

  const activityTimestamps = turns
    .map((turn) => turn.pvci_timestamputc)
    .filter((value): value is string => Boolean(value))
    .sort();

  const plans = planEvents.state === "available"
    ? buildReasoningPlans(asArray(planEvents.value), knowledgeCalls)
    : [];

  const draft: EssEvidenceDraft = {
    schemaVersion: ESS_EVIDENCE_SCHEMA_VERSION,
    evidenceFamily: ESS_EVIDENCE_FAMILY,
    generation: {
      generatedUtc,
      producer: ESS_EVIDENCE_PRODUCER,
      packageKind: "ess-support-evidence",
    },
    integrity: {
      payloadTruncated: Boolean(merged.pvci_payloadtruncated),
      replayTruncatedByExport: replayTruncated,
      warnings,
    },
    analystContext: {
      outcome: context.outcome,
      issueTitle: context.issueTitle.trim(),
      observedBehavior: context.observedBehavior.trim(),
      expectedBehavior: context.expectedBehavior.trim(),
      referencedKnowledgeUrls: normalizeUrlList(context.referencedKnowledgeUrls),
      expectedKnowledgeUrls: normalizeUrlList(context.expectedKnowledgeUrls),
      investigationNotes: context.investigationNotes.trim(),
    },
    provenance: {
      agent: {
        agentName: session.pvci_botname ?? null,
        agentId: session.pvci_botid ?? null,
        classification: "ess",
        classificationSource: "canonical ESS transcript-session classification",
      },
      environment: {
        environmentId: session.pvci_environmentid ?? null,
        environmentName: sourceEnvironmentLabel(session),
        isHostEnvironment: Boolean(
          hostEnvironmentId
          && session.pvci_environmentid
          && session.pvci_environmentid.toLowerCase() === hostEnvironmentId.toLowerCase(),
        ),
        dataSourceStamp: session.pvci_datasource ?? null,
      },
      channel: session.pvci_channel ?? null,
      execution: {
        testMode: Boolean(session.pvci_istestmode),
        topicName: session.pvci_topicname ?? null,
        topicId: session.pvci_topicid ?? null,
      },
      session: {
        sessionId: session.pvci_transcriptsessionid,
        sessionName: session.pvci_name ?? null,
        nativeTranscriptId: session.pvci_transcriptid ?? null,
        nativeTranscriptIdState: session.pvci_transcriptid ? "exact" : "unavailable",
        debugConversationId: {
          state: "unverified",
          value: null,
          note: "The native transcript ID is not proven to be the maker Debug conversation ID. Do not treat them as equivalent.",
        },
        identityCorrelation: {
          state: correlationEvidenceState(session.pvci_correlationstatus),
          reported: session.pvci_correlationstatus ?? null,
        },
        multiUserAnomaly: Boolean(session.pvci_multiuseranomaly),
      },
    },
    timestamps: {
      sessionStartUtc: session.pvci_startdatetimeutc ?? null,
      sessionEndUtc: session.pvci_enddatetimeutc ?? null,
      durationSeconds: session.pvci_durationseconds ?? null,
      firstActivityUtc: activityTimestamps[0] ?? null,
      lastActivityUtc: activityTimestamps[activityTimestamps.length - 1] ?? null,
      activityTimestampState: activityTimestamps.length ? "exact" : "unavailable",
    },
    conversation: {
      state: turns.length ? "available" : "not-stored",
      retainedTurnCount: turns.length,
      exportedTurnCount: replayTurns.length,
      storedConversationPayloadState: conversationPayload.state,
      storedActivitiesPayloadState: activitiesPayload.state,
      replay: replayTurns.map((turn, index) => ({
        index: turn.pvci_turnindex ?? index,
        timestampUtc: turn.pvci_timestamputc ?? null,
        speaker: turn.pvci_speaker ?? null,
        activityType: turn.pvci_activitytype ?? null,
        eventName: turn.pvci_eventname ?? null,
        latencyMs: turn.pvci_latencyms ?? null,
        text: bounded(turn.pvci_turntext, MAX_TEXT_LENGTH),
      })),
    },
    evidence: {
      reasoning: {
        payloadState: planEvents.state,
        planCount: plans.length,
        plans: plans.map((plan) => ({
          id: plan.id,
          request: plan.request ?? null,
          summary: plan.summary ?? null,
          isFinal: plan.isFinal,
          finished: plan.finished,
          startedAt: plan.startedAt ?? null,
          steps: plan.steps.map((step) => ({
            id: step.id,
            task: step.task ?? null,
            type: step.type ?? null,
            rationale: bounded(step.rationale, MAX_TEXT_LENGTH),
            startedAt: step.startedAt ?? null,
            state: step.state ?? "unknown",
            executionMs: step.executionMs ?? null,
            argumentNames: step.argumentNames,
            autoFilledArguments: step.autoFilledArguments,
            observationKeys: step.observationKeys,
            planFinished: step.planFinished,
          })),
        })),
      },
      knowledge: {
        payloadState: knowledge.state,
        citedSourceIdentifierNote: "Cited source values are agent knowledge-source identifiers. They are not URLs and must not be presented as links.",
        retrievals: knowledgeCalls.map((call, index) => ({
          index,
          stepId: call.step_id ?? null,
          task: call.task ?? null,
          correlation: call.correlation ?? "unknown",
          startedUtc: call.started_utc ?? null,
          durationMs: call.duration_ms ?? null,
          completionState: call.completion_state ?? "unknown",
          searched: Boolean(call.searched),
          failed: Boolean(call.failed),
          citedSourceIdentifiers: Array.isArray(call.cited_sources) ? call.cited_sources : [],
          failedSourceTypes: Array.isArray(call.failed_source_types) ? call.failed_source_types : [],
        })),
      },
      tools: {
        payloadState: tools.state,
        attributionState: exactToolTelemetry ? "exact" : "unavailable",
        attributionNote: exactToolTelemetry
          ? "Exact connector/tool traces are retained for this transcript."
          : "Exact connector/tool traces are unavailable for this transcript source.",
        rawOutputExported: false,
        rawOutputNote: "Raw tool outputs are intentionally excluded. Only output key names are exported.",
        calls: toolCalls.map((call, index) => ({
          index,
          actionId: call.action_id ?? null,
          actionType: call.action_type ?? null,
          topic: call.topic ?? null,
          startedUtc: call.started_utc ?? null,
          durationMs: call.duration_ms ?? null,
          failed: Boolean(call.failed),
          completionObserved: call.completion_observed ?? null,
          exception: bounded(call.exception, WARNING_MAX_LENGTH),
          outputKeys: objectKeys(call.output),
        })),
      },
      candidateFlows: {
        payloadState: flows.state,
        attributionState: flowTelemetryAvailable ? "candidate" : "unavailable",
        attributionNote: flowTelemetryAvailable
          ? "Flow runs are time-window candidate matches, not exact executions attributed to this conversation."
          : "Candidate flow correlation is unavailable for this transcript source.",
        runs: flowTelemetryAvailable ? flowRuns : [],
      },
      errors: {
        userErrorCount: countEvidence(session.pvci_usererrorcount, "exact"),
        primaryErrorCode: session.pvci_primaryerrorcode ?? null,
        primaryErrorTopic: session.pvci_primaryerrortopic ?? null,
        primaryErrorMessage: bounded(merged.pvci_primaryerrormessage, MAX_TEXT_LENGTH),
        errorCategory: session.pvci_errorcategory ?? null,
        sessionOutcome: session.pvci_sessionoutcome ?? null,
        outcomeReason: session.pvci_outcomereason ?? null,
        impliedResolved: session.pvci_isresolvedimplied ?? "unknown",
      },
    },
    telemetryAvailability: {
      transcriptTurns: countEvidence(turns.length, "exact"),
      exactToolTraces: exactToolTelemetry
        ? countEvidence(session.pvci_toolcallcount, "exact")
        : { state: "unavailable", count: null, note: "Exact tool telemetry is not retained for this transcript source." },
      toolFailures: exactToolTelemetry
        ? countEvidence(session.pvci_toolerrorcount, "exact")
        : { state: "unavailable", count: null },
      knowledgeRetrievals: countEvidence(session.pvci_knowledgecallcount, "exact"),
      citedSourceIdentifiers: countEvidence(session.pvci_knowledgesourcecount, "exact"),
      knowledgeFailures: countEvidence(session.pvci_knowledgefailurecount, "exact"),
      candidateFlowRuns: flowTelemetryAvailable
        ? countEvidence(session.pvci_flowruncount, "candidate")
        : { state: "unavailable", count: null, note: "Candidate flow correlation is unavailable for this transcript source." },
      candidateFlowFailures: flowTelemetryAvailable
        ? countEvidence(session.pvci_flowrunfailurecount, "candidate")
        : { state: "unavailable", count: null },
      reasoningPlanEvents: { state: planEvents.state },
    },
    completeness: {
      checklist: buildChecklist({
        context,
        turns: turns.length,
        planEvents: planEvents.state,
        knowledge: knowledge.state,
        knowledgeCalls: knowledgeCalls.length,
        tools: tools.state,
        toolCalls: toolCalls.length,
        exactToolTelemetry,
        flowTelemetryAvailable,
        flowRuns: flowRuns.length,
        userErrorCount: session.pvci_usererrorcount,
      }),
      missingExternalEvidence: EXTERNAL_EVIDENCE_ITEMS,
    },
  };

  const masked = maskTranscriptData(draft, [merged, turns]);

  return {
    ...masked.value,
    privacy: {
      maskingApplied: true,
      maskedByDefault: true,
      independentOfOnScreenReveal: true,
      detectorPolicy: {
        id: TRANSCRIPT_PRIVACY_POLICY_VERSION,
        scope: "Workday HR field and pattern detectors applied to every ESS evidence export",
      },
      workdayHrSession: isWorkdayHrSession(session),
      replacementCount: masked.replacementCount,
      categoryCounts: masked.categoryCounts,
      excludedFields: ["userPrincipalName", "userDisplayName", "userAadObjectId", "tenantId", "credentials", "tokens", "rawToolOutputs"],
    },
  };
}

interface ChecklistInput {
  context: EssEvidenceContext;
  turns: number;
  planEvents: PayloadState;
  knowledge: PayloadState;
  knowledgeCalls: number;
  tools: PayloadState;
  toolCalls: number;
  exactToolTelemetry: boolean;
  flowTelemetryAvailable: boolean;
  flowRuns: number;
  userErrorCount?: number | null;
}

function buildChecklist(input: ChecklistInput): ChecklistItem[] {
  const text = (value: string) => value.trim().length > 0;
  return [
    item("issue-title", "Issue title", text(input.context.issueTitle) ? "present" : "missing"),
    item("observed-behavior", "Observed behavior", text(input.context.observedBehavior) ? "present" : "missing"),
    item(
      "expected-behavior",
      "Expected behavior",
      text(input.context.expectedBehavior)
        ? "present"
        : input.context.outcome === "working" ? "not-applicable" : "missing",
    ),
    item("outcome-classification", "Working / non-working classification", "present"),
    item("referenced-knowledge-urls", "Referenced knowledge URLs", input.context.referencedKnowledgeUrls.some(text) ? "present" : "missing"),
    item("expected-knowledge-urls", "Expected knowledge URLs", input.context.expectedKnowledgeUrls.some(text) ? "present" : "missing"),
    item("investigation-notes", "Investigation notes", text(input.context.investigationNotes) ? "present" : "missing"),
    item("conversation-replay", "Conversation replay", input.turns > 0 ? "present" : "not-stored"),
    item("reasoning-evidence", "Agent reasoning evidence", payloadChecklistState(input.planEvents)),
    item(
      "knowledge-evidence",
      "Knowledge retrieval evidence",
      input.knowledge === "available" ? (input.knowledgeCalls > 0 ? "present" : "observed-zero") : payloadChecklistState(input.knowledge),
    ),
    item(
      "tool-evidence",
      "Exact tool evidence",
      input.exactToolTelemetry
        ? (input.tools === "available" ? (input.toolCalls > 0 ? "present" : "observed-zero") : payloadChecklistState(input.tools))
        : "unavailable",
    ),
    item(
      "candidate-flow-evidence",
      "Candidate flow evidence",
      input.flowTelemetryAvailable ? (input.flowRuns > 0 ? "present" : "observed-zero") : "unavailable",
    ),
    item(
      "error-evidence",
      "User-facing error evidence",
      input.userErrorCount == null ? "unavailable" : input.userErrorCount > 0 ? "present" : "observed-zero",
    ),
  ];
}

function item(id: string, label: string, state: string): ChecklistItem {
  return { id, label, state };
}

function payloadChecklistState(state: PayloadState): string {
  if (state === "available") return "present";
  if (state === "not-stored") return "not-stored";
  return "unavailable";
}

function countEvidence(value: number | null | undefined, presentState: EvidenceState, note?: string): EvidenceCount {
  if (value == null) return { state: "unavailable", count: null, ...(note ? { note } : {}) };
  const state: EvidenceState = value === 0 ? "observed-zero" : presentState;
  return { state, count: value, ...(note ? { note } : {}) };
}

function readPayload<T>(text: string | undefined, label: string): PayloadRead<T> {
  if (text == null || text.trim() === "") return { state: "not-stored", value: null };
  const parsed = safeParse(text);
  if (parsed === undefined) {
    return {
      state: "unavailable",
      value: null,
      warning: boundedWarning(`${label} payload is stored (${text.length} chars) but is not valid JSON, so its evidence is unavailable.`),
    };
  }
  return { state: "available", value: parsed as T };
}

function asArray<T>(value: T[] | null): T[] {
  return Array.isArray(value) ? value : [];
}

function boundedWarning(value: string): string {
  return value.length <= WARNING_MAX_LENGTH ? value : `${value.slice(0, WARNING_MAX_LENGTH - 1)}…`;
}

function bounded(value: string | undefined | null, limit: number): string | null {
  if (value == null || value === "") return null;
  return value.length <= limit ? value : `${value.slice(0, limit - 1)}…`;
}

function objectKeys(value: unknown): string[] {
  return value && typeof value === "object" && !Array.isArray(value) ? Object.keys(value) : [];
}

function correlationEvidenceState(status?: string): EvidenceState {
  const normalized = status?.trim().toLowerCase();
  if (!normalized) return "unknown";
  if (normalized === "exact") return "exact";
  if (normalized === "correlated") return "correlated";
  if (normalized === "candidate") return "candidate";
  if (normalized === "unavailable") return "unavailable";
  return "unknown";
}

function normalizeUrlList(values: string[]): string[] {
  return values.map((value) => value.trim()).filter(Boolean);
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48)
    .replace(/-+$/g, "");
}
