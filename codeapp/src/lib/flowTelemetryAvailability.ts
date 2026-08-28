import type { SessionRow } from "./model";

export function isFlowTelemetryAvailable(session: SessionRow, hostEnvironmentId?: string): boolean {
  if (hostEnvironmentId && session.pvci_environmentid) {
    return session.pvci_environmentid.toLowerCase() === hostEnvironmentId.toLowerCase()
      && session.pvci_flowruncount != null;
  }
  return session.pvci_flowruncount != null;
}