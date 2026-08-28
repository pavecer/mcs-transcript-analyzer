import { describe, expect, it } from "vitest";
import { resourceIdentityKey, scopedResourceIds, shouldShowResourceIdentity } from "./creditResourceIdentity";

describe("credit resource identity", () => {
  const resources = [
    { environmentId: "PVE-DEV", resourceId: "ESS IT" },
    { environmentId: "PVE-PREVIEW", resourceId: "ESS IT" },
    { environmentId: undefined, resourceId: "ESS IT" },
    { environmentId: undefined, resourceId: "Tenant-only resource" },
  ];

  it("keeps environment-scoped identities separate", () => {
    expect(resourceIdentityKey("PVE-DEV", "ESS IT")).toBe("pve-dev|ess it");
    expect(resourceIdentityKey("PVE-PREVIEW", "ESS IT")).not.toBe(resourceIdentityKey("PVE-DEV", "ESS IT"));
  });

  it("suppresses an unscoped navigator identity when scoped identities exist", () => {
    const scopedIds = scopedResourceIds(resources);

    expect(shouldShowResourceIdentity(undefined, "ESS IT", scopedIds)).toBe(false);
    expect(shouldShowResourceIdentity("PVE-DEV", "ESS IT", scopedIds)).toBe(true);
    expect(shouldShowResourceIdentity("PVE-PREVIEW", "ESS IT", scopedIds)).toBe(true);
  });

  it("keeps a genuinely tenant-level resource visible", () => {
    const scopedIds = scopedResourceIds(resources);

    expect(shouldShowResourceIdentity(undefined, "Tenant-only resource", scopedIds)).toBe(true);
  });
});