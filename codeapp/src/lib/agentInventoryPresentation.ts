export type AgentAuthorship = "user-created" | "microsoft-provided" | "unknown";
export type AgentDeployment = "managed" | "unmanaged" | "unknown";
export type AgentSessionMatch = "exact" | "candidate" | "ambiguous" | "none" | "loading" | "unavailable";
export type SessionEvidenceState = "loading" | "available" | "unavailable";

export interface AgentInventoryEvidence {
  id: string;
  tenantId?: string;
  environmentId?: string;
  botId?: string;
  resourceId?: string;
  displayName?: string;
  schemaName?: string;
  authoringOrigin?: string;
  published?: boolean;
  status?: string;
  lastSyncedOn?: string;
  evidenceJson?: string;
}

export interface AgentEnvironmentEvidence {
  id: string;
  tenantId?: string;
  environmentId?: string;
  displayName?: string;
  collectorEnabled?: boolean;
  accessStatus?: string;
  onboardingStatus?: string;
}

export interface AgentSessionEvidence {
  id: string;
  tenantId?: string;
  environmentId?: string;
  botId?: string;
  botName?: string;
  startedOn?: string;
  channel?: string;
  outcome?: string;
  initialMessage?: string;
  userErrorCount?: number;
}

export interface AgentCollectionState {
  available: boolean;
  label: string;
  reason: string;
}

export interface AgentInventoryPresentation {
  agent: AgentInventoryEvidence;
  environment?: AgentEnvironmentEvidence;
  environmentLabel: string;
  authorship: AgentAuthorship;
  authorshipLabel: string;
  deployment: AgentDeployment;
  deploymentLabel: string;
  collection: AgentCollectionState;
  exactSessions: AgentSessionEvidence[];
  candidateSessions: AgentSessionEvidence[];
  sessionMatch: AgentSessionMatch;
  sessionLabel: string;
}

interface InventoryProperties {
  createdBy?: unknown;
  isManaged?: unknown;
}

function normalize(value?: string) {
  return value?.trim().toLowerCase() ?? "";
}

function inventoryProperties(evidenceJson?: string): InventoryProperties {
  if (!evidenceJson) return {};
  try {
    const evidence = JSON.parse(evidenceJson) as { properties?: InventoryProperties };
    return evidence.properties ?? {};
  } catch {
    return {};
  }
}

function sameScope(
  left: { tenantId?: string; environmentId?: string },
  right: { tenantId?: string; environmentId?: string },
) {
  if (!normalize(left.environmentId) || normalize(left.environmentId) !== normalize(right.environmentId)) return false;
  const leftTenant = normalize(left.tenantId);
  const rightTenant = normalize(right.tenantId);
  return !leftTenant || !rightTenant || leftTenant === rightTenant;
}

function sameExactScope(
  left: { tenantId?: string; environmentId?: string },
  right: { tenantId?: string; environmentId?: string },
) {
  return Boolean(
    normalize(left.tenantId)
    && normalize(right.tenantId)
    && normalize(left.environmentId)
    && normalize(right.environmentId)
    && normalize(left.tenantId) === normalize(right.tenantId)
    && normalize(left.environmentId) === normalize(right.environmentId)
  );
}

export function classifyAgentAuthorship(
  evidenceJson?: string,
  schemaName?: string,
  displayName?: string,
): { kind: AgentAuthorship; label: string } {
  const normalizedSchema = normalize(schemaName);
  const microsoftReserved = normalizedSchema.startsWith("msdyn_")
    || normalizedSchema.startsWith("microsoft_")
    || normalize(displayName).startsWith("[internal]");
  if (microsoftReserved) {
    return { kind: "microsoft-provided", label: "Microsoft-provided · reserved marker" };
  }
  const createdBy = inventoryProperties(evidenceJson).createdBy;
  if (typeof createdBy === "string" ? Boolean(createdBy.trim()) : createdBy != null) {
    return { kind: "user-created", label: "User-created · creator recorded" };
  }
  return { kind: "unknown", label: "Authorship unknown" };
}

export function classifyAgentDeployment(evidenceJson?: string): { kind: AgentDeployment; label: string } {
  const isManaged = inventoryProperties(evidenceJson).isManaged;
  if (isManaged === true) return { kind: "managed", label: "Managed deployment" };
  if (isManaged === false) return { kind: "unmanaged", label: "Unmanaged deployment" };
  return { kind: "unknown", label: "Deployment unknown" };
}

export function agentCollectionState(
  environment: AgentEnvironmentEvidence | undefined,
  hostEnvironmentId?: string,
): AgentCollectionState {
  if (!environment) return { available: false, label: "Unavailable", reason: "Environment inventory is unavailable." };
  if (normalize(environment.environmentId) === normalize(hostEnvironmentId)) {
    return { available: true, label: "Local automatic", reason: "Sessions are collected in the host environment." };
  }
  const readable = environment.accessStatus === "readable_with_rows" || environment.accessStatus === "readable_empty";
  if (environment.collectorEnabled && readable && environment.onboardingStatus === "Verified") {
    return { available: true, label: "Remote enabled", reason: "The source is verified, readable, and enabled for collection." };
  }
  if (!readable) return { available: false, label: "Unavailable", reason: "Transcript access is not currently readable." };
  if (environment.onboardingStatus !== "Verified") return { available: false, label: "Unavailable", reason: "Source onboarding is not verified." };
  return { available: false, label: "Collection off", reason: "Transcript collection is not enabled for this source." };
}

export function buildAgentInventoryPresentations(
  agents: AgentInventoryEvidence[],
  environments: AgentEnvironmentEvidence[],
  sessions: AgentSessionEvidence[],
  hostEnvironmentId?: string,
  sessionEvidenceState: SessionEvidenceState = "available",
): AgentInventoryPresentation[] {
  const scopedNameCounts = new Map<string, number>();
  agents.forEach((agent) => {
    const key = `${normalize(agent.tenantId)}|${normalize(agent.environmentId)}|${normalize(agent.displayName)}`;
    if (normalize(agent.displayName)) scopedNameCounts.set(key, (scopedNameCounts.get(key) ?? 0) + 1);
  });

  return agents.map((agent) => {
    const environment = environments.find((candidate) => sameScope(agent, candidate));
    const collection = agentCollectionState(environment, hostEnvironmentId);
    const scopedSessions = sessions.filter((session) => sameScope(agent, session));
    const exactSessions = normalize(agent.botId)
      ? scopedSessions.filter((session) =>
          sameExactScope(agent, session)
          && normalize(session.botId) === normalize(agent.botId))
      : [];
    const candidateSessions = normalize(agent.displayName)
      ? scopedSessions.filter((session) =>
          normalize(session.botName) === normalize(agent.displayName)
          && !exactSessions.some((exact) => exact.id === session.id))
      : [];
    const nameKey = `${normalize(agent.tenantId)}|${normalize(agent.environmentId)}|${normalize(agent.displayName)}`;
    const ambiguous = (scopedNameCounts.get(nameKey) ?? 0) > 1;
    const authorship = classifyAgentAuthorship(agent.evidenceJson, agent.schemaName, agent.displayName);
    const deployment = classifyAgentDeployment(agent.evidenceJson);

    let sessionMatch: AgentSessionMatch = "none";
    let sessionLabel = "No name-matched sessions";
    if (!collection.available) {
      sessionMatch = "unavailable";
      sessionLabel = "Session details unavailable";
    } else if (sessionEvidenceState === "loading") {
      sessionMatch = "loading";
      sessionLabel = "Loading session evidence";
    } else if (sessionEvidenceState === "unavailable") {
      sessionMatch = "unavailable";
      sessionLabel = "Session evidence unavailable";
    } else if (exactSessions.length) {
      sessionMatch = "exact";
      sessionLabel = `${exactSessions.length} exact ${exactSessions.length === 1 ? "session" : "sessions"}`;
    } else if (candidateSessions.length) {
      sessionMatch = ambiguous ? "ambiguous" : "candidate";
      sessionLabel = `${candidateSessions.length} ${ambiguous ? "ambiguous" : "candidate"} ${candidateSessions.length === 1 ? "session" : "sessions"}`;
    }

    return {
      agent,
      environment,
      environmentLabel: environment?.displayName ?? agent.environmentId ?? "Unknown environment",
      authorship: authorship.kind,
      authorshipLabel: authorship.label,
      deployment: deployment.kind,
      deploymentLabel: deployment.label,
      collection,
      exactSessions,
      candidateSessions,
      sessionMatch,
      sessionLabel,
    };
  });
}
