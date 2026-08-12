import { describe, expect, it } from "vitest";
import { isActiveThresholdRequest, thresholdRequestStatusLabel } from "./thresholdRequestState";

describe("threshold request state", () => {
  it("blocks duplicate changes only while a request is active", () => {
    expect(isActiveThresholdRequest("Pending")).toBe(true);
    expect(isActiveThresholdRequest("Processing")).toBe(true);
    expect(isActiveThresholdRequest("Succeeded")).toBe(false);
    expect(isActiveThresholdRequest("Stale")).toBe(false);
  });

  it("uses operator-facing lifecycle labels", () => {
    expect(thresholdRequestStatusLabel("Pending")).toBe("Requested");
    expect(thresholdRequestStatusLabel("Succeeded")).toBe("Applied");
    expect(thresholdRequestStatusLabel("Stale")).toBe("Review needed");
    expect(thresholdRequestStatusLabel("AppliedUnverified")).toBe("Verify applied");
  });
});