import { describe, expect, it } from "vitest";
import {
  isCrossEnvironmentCollectionEnabled,
  resolveEnvironmentFilter,
  scopeRowsToHost,
} from "./transcriptScope";

describe("transcript scope", () => {
  it("stays local when no remote collector is enabled", () => {
    expect(isCrossEnvironmentCollectionEnabled([], "local-id")).toBe(false);
    expect(isCrossEnvironmentCollectionEnabled(["LOCAL-ID"], "local-id")).toBe(false);
  });

  it("enables cross-environment mode for an enabled remote source", () => {
    expect(isCrossEnvironmentCollectionEnabled(["remote-id"], "local-id")).toBe(true);
  });

  it("shows only host rows until cross-environment mode is enabled", () => {
    const rows = [
      { pvci_environmentid: "local-id", name: "local" },
      { pvci_environmentid: "remote-id", name: "remote" },
    ];

    expect(scopeRowsToHost(rows, "LOCAL-ID", false)).toEqual([rows[0]]);
    expect(scopeRowsToHost(rows, "local-id", true)).toEqual(rows);
  });

  it("uses the host environment for local-only reporting filters", () => {
    expect(resolveEnvironmentFilter("*", "local-id", false)).toBe("local-id");
    expect(resolveEnvironmentFilter("remote-id", "local-id", true)).toBe("remote-id");
    expect(resolveEnvironmentFilter("*", undefined, false)).not.toBe("*");
  });
});