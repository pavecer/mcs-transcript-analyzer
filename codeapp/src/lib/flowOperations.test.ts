import { describe, expect, it } from "vitest";
import {
  assessCentralCollection,
  assessFlowConfiguration,
  assessRequestProcessor,
  assessScheduledRun,
  buildFlowDetailsUrl,
  buildFlowDiagnosticText,
  notInstalledAssessment,
  summarizeRunHistory,
  summarizeRequestQueue,
  unavailableAssessment,
} from "./flowOperations";

const NOW = Date.parse("2026-09-01T12:00:00Z");
const HOUR = 60 * 60 * 1000;

describe("flow operations evidence", () => {
  it("keeps an observed zero distinct from an unavailable count", () => {
    expect(assessScheduledRun({ status: "success", completedOn: "2026-09-01T11:30:00Z", processedCount: 0 }, NOW, HOUR).summary)
      .toBe("0 records");
    expect(assessScheduledRun({ status: "success", completedOn: "2026-09-01T11:30:00Z" }, NOW, HOUR).summary)
      .toBe("count unavailable");
  });

  it("prioritizes a failed result over freshness", () => {
    expect(assessScheduledRun({ status: "failed", completedOn: "2026-09-01T11:59:00Z", rejectedCount: 2, error: "Import rejected" }, NOW, HOUR))
      .toEqual({ state: "failed", latestOn: "2026-09-01T11:59:00Z", summary: "2 rejected records", error: "Import rejected" });
  });

  it("marks an old successful scheduled run as stale", () => {
    expect(assessScheduledRun({ status: "succeeded", completedOn: "2026-09-01T09:00:00Z", processedCount: 4 }, NOW, HOUR).state)
      .toBe("stale");
  });

  it("surfaces failed central sources before overdue sources", () => {
    expect(assessCentralCollection([
      { enabled: true, status: "failed", completedOn: "2026-09-01T11:50:00Z", error: "Access denied" },
      { enabled: true, status: "success", completedOn: "2026-08-31T08:00:00Z", batchCount: 0 },
    ], NOW, HOUR)).toMatchObject({ state: "failed", summary: "1 of 2 enabled sources failed", error: "Access denied" });
  });

  it("does not call a request processor healthy without execution evidence", () => {
    expect(assessRequestProcessor([], NOW, 10 * 60 * 1000)).toEqual({
      state: "unknown",
      summary: "No request execution evidence",
    });
  });

  it("marks pending requests overdue without claiming they failed", () => {
    expect(assessRequestProcessor([
      { status: "Pending", requestedOn: "2026-09-01T11:30:00Z" },
    ], NOW, 10 * 60 * 1000)).toMatchObject({ state: "stale", summary: "1 pending request is overdue" });
  });

  it("represents the optional add-on as not installed", () => {
    expect(notInstalledAssessment().state).toBe("not-installed");
  });

  it("keeps a read failure distinct from missing evidence", () => {
    expect(unavailableAssessment("Access denied")).toEqual({
      state: "unavailable",
      summary: "Operational evidence could not be read",
      error: "Access denied",
    });
  });

  it("builds a target-environment Power Automate flow details link", () => {
    expect(buildFlowDetailsUrl("environment-id", "flow-id")).toBe(
      "https://make.powerautomate.com/environments/environment-id/flows/flow-id/details",
    );
    expect(buildFlowDetailsUrl(undefined, "flow-id")).toBeUndefined();
  });

  it("summarizes the last attempt, last success, and leading failure streak", () => {
    expect(summarizeRunHistory([
      { status: "failed", completedOn: "2026-09-01T11:00:00Z", durationMs: 4000 },
      { status: "failed", completedOn: "2026-09-01T10:00:00Z", durationMs: 3000 },
      { status: "success", completedOn: "2026-09-01T09:00:00Z", durationMs: 1000 },
    ])).toMatchObject({
      lastAttemptOn: "2026-09-01T11:00:00Z",
      lastSuccessOn: "2026-09-01T09:00:00Z",
      consecutiveFailures: 2,
      latestDurationMs: 4000,
    });
  });

  it("compares the latest duration with prior successful runs only", () => {
    expect(summarizeRunHistory([
      { status: "success", completedOn: "2026-09-01T11:00:00Z", durationMs: 3000 },
      { status: "success", completedOn: "2026-09-01T10:00:00Z", durationMs: 1000 },
      { status: "failed", completedOn: "2026-09-01T09:00:00Z", durationMs: 9000 },
      { status: "success", completedOn: "2026-09-01T08:00:00Z", durationMs: 1000 },
    ])).toMatchObject({
      successfulDurationBaselineMs: 1000,
      durationRegressionRatio: 3,
    });
  });

  it("counts active and overdue processor requests", () => {
    expect(summarizeRequestQueue([
      { status: "Pending", requestedOn: "2026-09-01T11:30:00Z" },
      { status: "Processing", requestedOn: "2026-09-01T11:55:00Z" },
      { status: "Verified", requestedOn: "2026-09-01T11:00:00Z" },
    ], NOW, 10 * 60 * 1000)).toEqual({ pendingCount: 2, overdueCount: 1 });
  });

  it("builds a payload-free diagnostic bundle", () => {
    const diagnostic = buildFlowDiagnosticText({
      generatedOn: "2026-09-01T12:00:00Z",
      flowName: "Collect Tenant Agent Inventory",
      flowId: "flow-id",
      environmentId: "environment-id",
      solution: "Core",
      cadence: "Daily",
      state: "failed",
      summary: "2 rejected records",
      configurationState: "unmapped",
      configurationSummary: "1 required connection is unmapped",
      missingConnections: ["pvci_powerplatformapi"],
      lastAttemptOn: "2026-09-01T11:00:00Z",
      lastSuccessOn: "2026-08-31T11:00:00Z",
      consecutiveFailures: 2,
      error: "Import rejected",
      flowUrl: "https://make.powerautomate.com/environments/environment-id/flows/flow-id/details",
    });

    expect(diagnostic).toContain("Consecutive failures: 2");
    expect(diagnostic).toContain("Missing connections: pvci_powerplatformapi");
    expect(diagnostic).toContain("Error: Import rejected");
    expect(diagnostic).toContain("Power Automate: https://make.powerautomate.com/");
    expect(diagnostic).not.toContain("payload");
  });

  it("classifies flow activation and connection readiness", () => {
    expect(assessFlowConfiguration(1, 2, ["pvci_dataversesync"], new Set(["pvci_dataversesync"]))).toMatchObject({
      state: "ready",
      summary: "Activated and mapped",
    });
    expect(assessFlowConfiguration(1, 2, ["pvci_dataversesync", "pvci_powerplatformapi"], new Set(["pvci_dataversesync"]))).toMatchObject({
      state: "unmapped",
      missingConnections: ["pvci_powerplatformapi"],
    });
    expect(assessFlowConfiguration(0, 1, [], new Set()).state).toBe("disabled");
    expect(assessFlowConfiguration(1, 3, [], new Set()).state).toBe("dlp-violation");
  });
});