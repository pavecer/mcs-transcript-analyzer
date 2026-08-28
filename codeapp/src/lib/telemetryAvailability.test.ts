import { describe, expect, it } from "vitest";
import { formatObservedMetric, formatObservedPair } from "./telemetryAvailability";

const RETRIEVALS = { singular: "retrieval", plural: "retrievals" };
const SOURCES = { singular: "source ID", plural: "source IDs" };

describe("telemetry availability formatting", () => {
  it("keeps an observed zero distinct from unavailable telemetry", () => {
    expect(formatObservedMetric(0, RETRIEVALS)).toBe("0 retrievals");
    expect(formatObservedMetric(undefined, RETRIEVALS)).toBe("retrievals unavailable");
  });

  it("uses singular labels for one observed event", () => {
    expect(formatObservedMetric(1, RETRIEVALS)).toBe("1 retrieval");
  });

  it("reports a fully unavailable pair without inventing zeroes", () => {
    expect(formatObservedPair(undefined, RETRIEVALS, null, SOURCES))
      .toBe("Unavailable in this transcript");
  });

  it("preserves partial availability", () => {
    expect(formatObservedPair(1, RETRIEVALS, undefined, SOURCES))
      .toBe("1 retrieval / source IDs unavailable");
  });
});
