import { describe, expect, it } from "vitest";
import { classifyCreditCapability, withTimeout } from "./creditCapability";

describe("credit capability", () => {
  it("keeps credit services unavailable without the optional add-on", () => {
    expect(classifyCreditCapability(false, false)).toBe("unavailable");
    expect(classifyCreditCapability(false, true)).toBe("unavailable");
  });

  it("requires setup until the add-on records its first sync run", () => {
    expect(classifyCreditCapability(true, false)).toBe("setup-required");
    expect(classifyCreditCapability(true, true)).toBe("ready");
  });

  it("bounds a capability query that never settles", async () => {
    await expect(withTimeout(new Promise(() => undefined), 1)).rejects.toThrow(
      "Credit capability check timed out",
    );
  });
});