import { describe, expect, it } from "vitest";
import { buildSessionAlerts } from "./sessionAlerts";

describe("session selector alerts", () => {
  it("puts explicit user, tool, and candidate-flow failures in the selector", () => {
    expect(buildSessionAlerts({
      userErrorCount: 2,
      errorCategory: "Topic expression",
      toolErrorCount: 1,
      candidateFlowFailureCount: 1,
    })).toEqual([
      { kind: "error", text: "2 user errors · Topic expression" },
      { kind: "error", text: "1 tool failure" },
      { kind: "error", text: "1 candidate flow failure" },
    ]);
  });

  it("does not invent failures from unavailable counters", () => {
    expect(buildSessionAlerts({
      userErrorCount: null,
      toolErrorCount: undefined,
      candidateFlowFailureCount: null,
    })).toEqual([]);
  });

  it("surfaces truncated evidence as a warning", () => {
    expect(buildSessionAlerts({ payloadTruncated: true }))
      .toEqual([{ kind: "warning", text: "Capture truncated" }]);
  });
});