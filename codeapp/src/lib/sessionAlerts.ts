export interface SessionAlertSource {
  userErrorCount?: number | null;
  errorCategory?: string | null;
  primaryErrorCode?: string | null;
  toolErrorCount?: number | null;
  candidateFlowFailureCount?: number | null;
  payloadTruncated?: boolean | null;
}

export interface SessionAlert {
  kind: "error" | "warning";
  text: string;
}

export function buildSessionAlerts(source: SessionAlertSource): SessionAlert[] {
  const alerts: SessionAlert[] = [];

  if ((source.userErrorCount ?? 0) > 0) {
    const count = source.userErrorCount!;
    const category = source.errorCategory ?? source.primaryErrorCode ?? "User-facing error";
    alerts.push({ kind: "error", text: `${count} user ${count === 1 ? "error" : "errors"} · ${category}` });
  }
  if ((source.toolErrorCount ?? 0) > 0) {
    const count = source.toolErrorCount!;
    alerts.push({ kind: "error", text: `${count} tool ${count === 1 ? "failure" : "failures"}` });
  }
  if ((source.candidateFlowFailureCount ?? 0) > 0) {
    const count = source.candidateFlowFailureCount!;
    alerts.push({ kind: "error", text: `${count} candidate flow ${count === 1 ? "failure" : "failures"}` });
  }
  if (source.payloadTruncated) {
    alerts.push({ kind: "warning", text: "Capture truncated" });
  }

  return alerts;
}