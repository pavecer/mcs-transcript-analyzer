import { describe, expect, it } from "vitest";
import {
  canEnableTranscriptCollector,
  isActiveTranscriptAccessRequest,
  matchesInventoryFilter,
  transcriptOnboardingStatusLabel,
} from "./transcriptAccessState";

describe("transcript access state", () => {
  it("enables collection only after a readable verified result", () => {
    expect(canEnableTranscriptCollector("Verified", "readable_empty")).toBe(true);
    expect(canEnableTranscriptCollector("Verified", "readable_with_rows")).toBe(true);
    expect(canEnableTranscriptCollector("Pending", "readable_with_rows")).toBe(false);
    expect(canEnableTranscriptCollector("Verified", "access_denied")).toBe(false);
  });

  it("polls only requests that can still change", () => {
    expect(isActiveTranscriptAccessRequest("Pending")).toBe(true);
    expect(isActiveTranscriptAccessRequest("Processing")).toBe(true);
    expect(isActiveTranscriptAccessRequest("Verified")).toBe(false);
  });

  it("maps inventory summary filters to their visible row sets", () => {
    const ready = { pvci_hasdataverse: true, pvci_environmenturl: "https://source.example", pvci_transcriptaccessstatus: "readable_empty" };
    const denied = { pvci_hasdataverse: true, pvci_environmenturl: "https://denied.example", pvci_transcriptaccessstatus: "access_denied" };
    const unavailable = { pvci_hasdataverse: false };

    expect(matchesInventoryFilter(ready, "all")).toBe(true);
    expect(matchesInventoryFilter(ready, "ready")).toBe(true);
    expect(matchesInventoryFilter(ready, "readable")).toBe(true);
    expect(matchesInventoryFilter(denied, "denied")).toBe(true);
    expect(matchesInventoryFilter(unavailable, "not-ready")).toBe(true);
    expect(matchesInventoryFilter(unavailable, "ready")).toBe(false);
  });

  it("uses operator-facing labels", () => {
    expect(transcriptOnboardingStatusLabel("AwaitingSourceOwner")).toBe("Awaiting source owner");
    expect(transcriptOnboardingStatusLabel()).toBe("Not configured");
  });
});