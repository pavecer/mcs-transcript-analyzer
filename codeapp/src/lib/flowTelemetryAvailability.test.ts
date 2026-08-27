import { describe, expect, it } from "vitest";
import { isFlowTelemetryAvailable } from "./flowTelemetryAvailability";
import type { SessionRow } from "./model";

const session = (environmentId: string, flowRunCount: number | undefined): SessionRow => ({
  pvci_transcriptsessionid: "session",
  pvci_name: "session",
  pvci_environmentid: environmentId,
  pvci_flowruncount: flowRunCount,
});

describe("flow telemetry availability", () => {
  it("accepts observed local zero", () => {
    expect(isFlowTelemetryAvailable(session("host", 0), "HOST")).toBe(true);
  });

  it("rejects legacy zero counters on central sessions", () => {
    expect(isFlowTelemetryAvailable(session("source", 0), "host")).toBe(false);
  });

  it("rejects null local telemetry", () => {
    expect(isFlowTelemetryAvailable(session("host", undefined), "host")).toBe(false);
  });
});