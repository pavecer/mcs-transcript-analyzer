import { describe, expect, it } from "vitest";
import {
  agentCollectionState,
  buildAgentInventoryPresentations,
  classifyAgentAuthorship,
  classifyAgentDeployment,
  type AgentEnvironmentEvidence,
  type AgentInventoryEvidence,
  type AgentSessionEvidence,
} from "./agentInventoryPresentation";

const userManagedEvidence = JSON.stringify({ properties: { createdBy: "creator-id", isManaged: true } });

const environment = (overrides: Partial<AgentEnvironmentEvidence> = {}): AgentEnvironmentEvidence => ({
  id: "inventory-1",
  tenantId: "tenant",
  environmentId: "environment",
  displayName: "Operations",
  collectorEnabled: true,
  accessStatus: "readable_with_rows",
  onboardingStatus: "Verified",
  ...overrides,
});

const agent = (overrides: Partial<AgentInventoryEvidence> = {}): AgentInventoryEvidence => ({
  id: "agent-1",
  tenantId: "tenant",
  environmentId: "environment",
  botId: "inventory-bot",
  displayName: "Service Desk",
  evidenceJson: userManagedEvidence,
  ...overrides,
});

const session = (overrides: Partial<AgentSessionEvidence> = {}): AgentSessionEvidence => ({
  id: "session-1",
  tenantId: "tenant",
  environmentId: "environment",
  botId: "transcript-bot",
  botName: "Service Desk",
  ...overrides,
});

describe("agent inventory presentation", () => {
  it("keeps user-created authorship independent from managed deployment", () => {
    expect(classifyAgentAuthorship(userManagedEvidence, "pve_ServiceDesk", "Service Desk")).toEqual({
      kind: "user-created",
      label: "User-created · creator recorded",
    });
    expect(classifyAgentDeployment(userManagedEvidence)).toEqual({
      kind: "managed",
      label: "Managed deployment",
    });
  });

  it("keeps missing creator and deployment evidence unknown", () => {
    expect(classifyAgentAuthorship("{}").kind).toBe("unknown");
    expect(classifyAgentDeployment("not-json").kind).toBe("unknown");
  });

  it("does not label Microsoft-reserved agents user-created when creator evidence exists", () => {
    expect(classifyAgentAuthorship(userManagedEvidence, "msdyn_copilotforemployeeselfserviceit", "Employee Self-Service IT"))
      .toEqual({ kind: "microsoft-provided", label: "Microsoft-provided · reserved marker" });
    expect(classifyAgentAuthorship(userManagedEvidence, "pve_Internal", "[Internal] Parser"))
      .toEqual({ kind: "microsoft-provided", label: "Microsoft-provided · reserved marker" });
  });

  it("matches exact IDs case-insensitively within tenant and environment", () => {
    const rows = buildAgentInventoryPresentations(
      [agent({ botId: "BOT-ID" })],
      [environment()],
      [session({ botId: "bot-id", botName: "Other" })],
      "host",
    );
    expect(rows[0].sessionMatch).toBe("exact");
    expect(rows[0].exactSessions).toHaveLength(1);
  });

  it("requires tenant identity for an exact session match", () => {
    const missingAgentTenant = buildAgentInventoryPresentations(
      [agent({ tenantId: undefined, botId: "bot-id", displayName: "Other" })],
      [environment({ tenantId: undefined })],
      [session({ botId: "bot-id", botName: "Different" })],
      "host",
    );
    const missingSessionTenant = buildAgentInventoryPresentations(
      [agent({ botId: "bot-id", displayName: "Other" })],
      [environment()],
      [session({ tenantId: undefined, botId: "bot-id", botName: "Different" })],
      "host",
    );
    expect(missingAgentTenant[0].sessionMatch).toBe("none");
    expect(missingSessionTenant[0].sessionMatch).toBe("none");
  });

  it("never treats an environment-scoped name match as exact", () => {
    const rows = buildAgentInventoryPresentations([agent()], [environment()], [session()], "host");
    expect(rows[0].sessionMatch).toBe("candidate");
    expect(rows[0].exactSessions).toHaveLength(0);
    expect(rows[0].candidateSessions).toHaveLength(1);
  });

  it("marks duplicate names in one environment as ambiguous", () => {
    const rows = buildAgentInventoryPresentations(
      [agent(), agent({ id: "agent-2", botId: "other-inventory-bot" })],
      [environment()],
      [session()],
      "host",
    );
    expect(rows.every((row) => row.sessionMatch === "ambiguous")).toBe(true);
  });

  it("does not match the same name across environments", () => {
    const rows = buildAgentInventoryPresentations(
      [agent()],
      [environment()],
      [session({ environmentId: "other-environment" })],
      "host",
    );
    expect(rows[0].sessionMatch).toBe("none");
  });

  it("withholds session details when remote collection is off", () => {
    const rows = buildAgentInventoryPresentations(
      [agent()],
      [environment({ collectorEnabled: false })],
      [session()],
      "host",
    );
    expect(rows[0].collection.available).toBe(false);
    expect(rows[0].sessionMatch).toBe("unavailable");
    expect(rows[0].sessionLabel).toBe("Session details unavailable");
  });

  it("allows local host collection independently of remote onboarding fields", () => {
    expect(agentCollectionState(environment({ collectorEnabled: false, accessStatus: undefined, onboardingStatus: undefined }), "ENVIRONMENT"))
      .toMatchObject({ available: true, label: "Local automatic" });
  });

  it("keeps a failed session query distinct from no matching sessions", () => {
    const rows = buildAgentInventoryPresentations([agent()], [environment()], [], "host", "unavailable");
    expect(rows[0].sessionMatch).toBe("unavailable");
    expect(rows[0].sessionLabel).toBe("Session evidence unavailable");
  });

  it("keeps session loading distinct from observed no match", () => {
    const rows = buildAgentInventoryPresentations([agent()], [environment()], [], "host", "loading");
    expect(rows[0].sessionMatch).toBe("loading");
    expect(rows[0].sessionLabel).toBe("Loading session evidence");
  });
});
