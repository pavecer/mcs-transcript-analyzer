import { describe, expect, it } from "vitest";
import { loadAllPages } from "./paging";

describe("loadAllPages", () => {
  it("accumulates rows until the service omits the skip token", async () => {
    const calls: Array<string | undefined> = [];
    const rows = await loadAllPages(async (skipToken, pageSize) => {
      calls.push(skipToken);
      expect(pageSize).toBe(2);
      return skipToken
        ? { success: true, data: [3], skipToken: undefined }
        : { success: true, data: [1, 2], skipToken: "next" };
    }, 2);

    expect(rows).toEqual([1, 2, 3]);
    expect(calls).toEqual([undefined, "next"]);
  });

  it("propagates a failed page result", async () => {
    const failure = new Error("request failed");
    await expect(loadAllPages(async () => ({ success: false, error: failure }))).rejects.toBe(failure);
  });

  it("rejects a repeated skip token", async () => {
    await expect(loadAllPages(async () => ({ data: [1], skipToken: "same" }))).rejects.toThrow(
      "repeated paging token",
    );
  });

  it("fails instead of silently truncating at the reporting limit", async () => {
    let page = 0;
    await expect(loadAllPages(async () => ({ data: [page], skipToken: `page-${page += 1}` }), 1, 2)).rejects.toThrow(
      "exceeded the 2 row reporting limit",
    );
  });
});