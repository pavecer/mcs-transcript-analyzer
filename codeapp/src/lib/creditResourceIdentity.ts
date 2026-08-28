export interface CreditResourceIdentity {
  environmentId?: string | null;
  resourceId?: string | null;
}

export function resourceIdentityKey(environmentId: string | null | undefined, resourceId: string): string {
  return `${environmentId?.toLowerCase() ?? ""}|${resourceId.toLowerCase()}`;
}

export function scopedResourceIds(rows: CreditResourceIdentity[]): Set<string> {
  return new Set(
    rows
      .filter((row) => Boolean(row.environmentId && row.resourceId))
      .map((row) => row.resourceId!.toLowerCase()),
  );
}

export function shouldShowResourceIdentity(
  environmentId: string | null | undefined,
  resourceId: string,
  scopedIds: ReadonlySet<string>,
): boolean {
  return Boolean(environmentId) || !scopedIds.has(resourceId.toLowerCase());
}