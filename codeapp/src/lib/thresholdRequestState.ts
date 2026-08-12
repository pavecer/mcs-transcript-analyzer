export function isActiveThresholdRequest(status?: string): boolean {
  return status === "Pending" || status === "Processing";
}

export function thresholdRequestStatusLabel(status?: string): string {
  switch (status) {
    case "Pending": return "Requested";
    case "Processing": return "Processing";
    case "Succeeded": return "Applied";
    case "Stale": return "Review needed";
    case "Failed": return "Failed";
    case "AppliedUnverified": return "Verify applied";
    default: return status ?? "No request";
  }
}