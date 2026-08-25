export type TranscriptOnboardingMode = "SourceManaged" | "AdministratorBootstrap" | "Excluded";
export type InventoryFilter = "all" | "ready" | "enabled" | "readable" | "denied" | "not-ready";

type InventoryFilterRow = {
  pvci_hasdataverse?: boolean;
  pvci_environmenturl?: string;
  pvci_transcriptcollectorenabled?: boolean;
  pvci_transcriptaccessstatus?: string;
};

export function isReadableTranscriptAccess(status?: string) {
  return status === "readable_with_rows" || status === "readable_empty";
}

export function matchesInventoryFilter(row: InventoryFilterRow, filter: InventoryFilter) {
  const dataverseReady = Boolean(row.pvci_hasdataverse && row.pvci_environmenturl);
  switch (filter) {
    case "ready": return dataverseReady;
    case "enabled": return Boolean(row.pvci_transcriptcollectorenabled);
    case "readable": return isReadableTranscriptAccess(row.pvci_transcriptaccessstatus);
    case "denied": return row.pvci_transcriptaccessstatus === "access_denied";
    case "not-ready": return !dataverseReady;
    default: return true;
  }
}

export function canEnableTranscriptCollector(
  onboardingStatus?: string,
  accessStatus?: string,
) {
  return onboardingStatus === "Verified" && isReadableTranscriptAccess(accessStatus);
}

export function isActiveTranscriptAccessRequest(status?: string) {
  return status === "Pending" || status === "Processing";
}

export function transcriptOnboardingStatusLabel(status?: string) {
  switch (status) {
    case "AwaitingSourceOwner": return "Awaiting source owner";
    case "Pending": return "Verification queued";
    case "Processing": return "Verifying";
    case "Verified": return "Verified";
    case "Failed": return "Verification failed";
    case "Drifted": return "Access drifted";
    case "Excluded": return "Excluded";
    default: return "Not configured";
  }
}