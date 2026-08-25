export interface EnvironmentScopedRow {
  pvci_environmentid?: string;
}

const UNAVAILABLE_LOCAL_ENVIRONMENT = "__pvci_local_environment_unavailable__";

export function isCrossEnvironmentCollectionEnabled(
  enabledEnvironmentIds: string[],
  hostEnvironmentId?: string,
) {
  const hostId = hostEnvironmentId?.toLowerCase();
  return enabledEnvironmentIds.some((environmentId) =>
    !hostId || environmentId.toLowerCase() !== hostId
  );
}

export function scopeRowsToHost<T extends EnvironmentScopedRow>(
  rows: T[],
  hostEnvironmentId: string | undefined,
  crossEnvironmentEnabled: boolean,
) {
  if (crossEnvironmentEnabled || !hostEnvironmentId) return rows;
  const hostId = hostEnvironmentId.toLowerCase();
  return rows.filter((row) => row.pvci_environmentid?.toLowerCase() === hostId);
}

export function resolveEnvironmentFilter(
  selectedEnvironmentId: string,
  hostEnvironmentId: string | undefined,
  crossEnvironmentEnabled: boolean,
) {
  if (crossEnvironmentEnabled) return selectedEnvironmentId;
  return hostEnvironmentId || UNAVAILABLE_LOCAL_ENVIRONMENT;
}