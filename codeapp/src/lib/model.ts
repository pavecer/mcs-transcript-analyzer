export interface SessionRow {
  pvci_transcriptsessionid: string;
  pvci_transcriptid?: string;
  pvci_name: string;
  pvci_userdisplayname?: string;
  pvci_userupn?: string;
  pvci_useraadobjectid?: string;
  pvci_channel?: string;
  pvci_botid?: string;
  pvci_botname?: string;
  pvci_tenantid?: string;
  pvci_topicname?: string;
  pvci_topicid?: string;
  pvci_datasource?: string;
  pvci_startdatetimeutc?: string;
  pvci_enddatetimeutc?: string;
  pvci_durationseconds?: number;
  pvci_messagecount?: number;
  pvci_activitycount?: number;
  pvci_eventcount?: number;
  pvci_userturncount?: number;
  pvci_agentturncount?: number;
  pvci_istestmode?: boolean;
  pvci_multiuseranomaly?: boolean;
  pvci_payloadtruncated?: boolean;
  pvci_correlationstatus?: string;
  pvci_initialusermessage?: string;
  pvci_firstresponsems?: number;
  pvci_avgresponsems?: number;
  pvci_maxresponsems?: number;
  pvci_toolcallcount?: number;
  pvci_toolerrorcount?: number;
  pvci_tooltotalms?: number;
  pvci_maxtoolms?: number;
  pvci_toolcallsjson?: string;
  pvci_flowrunsjson?: string;
  pvci_flowruncount?: number;
  pvci_flowrunfailurecount?: number;
  pvci_flowrunmaxms?: number;
  pvci_sessionoutcome?: string;
  pvci_outcomereason?: string;
  pvci_isresolvedimplied?: string;
  pvci_turncount?: number;
  pvci_activitiesjson?: string;
  pvci_conversationjson?: string;
  pvci_planeventsjson?: string;
  pvci_metadatajson?: string;
}

export interface TurnRow {
  pvci_transcriptturnid: string;
  pvci_transcriptid?: string;
  pvci_turnindex?: number;
  pvci_activitytype?: string;
  pvci_speaker?: string;
  pvci_role?: number;
  pvci_eventname?: string;
  pvci_channelid?: string;
  pvci_timestamputc?: string;
  pvci_turntext?: string;
  pvci_valuejson?: string;
  pvci_latencyms?: number;
}

export interface ToolCall {
  action_id?: string;
  action_type?: string;
  topic?: string;
  started_utc?: string;
  duration_ms?: number | null;
  failed?: boolean;
  exception?: string;
  output?: unknown;
}

export interface SourceStamp {
  raw: string;
  kind: string;
  tenantId?: string;
  environmentId?: string;
  environmentName?: string;
  org?: string;
}

export function fmtMs(ms?: number | null): string {
  if (ms === undefined || ms === null) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** Traffic-light banding for user-perceived reply latency. */
export function latencyBand(ms?: number | null): "good" | "warn" | "bad" | "none" {
  if (ms === undefined || ms === null) return "none";
  if (ms < 3000) return "good";
  if (ms < 10000) return "warn";
  return "bad";
}

export type Json = null | boolean | number | string | Json[] | { [k: string]: Json };

export type TurnKind = "message" | "reasoning" | "other";

export function turnKind(t: TurnRow): TurnKind {
  if (t.pvci_activitytype === "message" && (t.pvci_turntext ?? "").trim()) return "message";
  if ((t.pvci_eventname ?? "").startsWith("DynamicPlan")) return "reasoning";
  return "other";
}

export function safeParse(text: string | undefined): Json | undefined {
  if (!text) return undefined;
  try {
    return JSON.parse(text) as Json;
  } catch {
    return undefined;
  }
}

export function fmtTime(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toISOString().replace("T", " ").slice(0, 19);
}

export function fmtClock(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toISOString().slice(11, 19);
}

export function fmtDuration(seconds?: number): string {
  if (seconds === undefined || seconds === null) return "—";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  return `${m}m ${seconds % 60}s`;
}

/** Parse source stamps like: dataverse_v9.1|tenant:...|env:...|envName:...|org:... */
export function parseSourceStamp(raw?: string): SourceStamp | null {
  if (!raw) return null;
  const parts = raw.split("|").map((p) => p.trim()).filter(Boolean);
  if (!parts.length) return null;
  const out: SourceStamp = { raw, kind: parts[0] };
  for (const part of parts.slice(1)) {
    const idx = part.indexOf(":");
    if (idx <= 0) continue;
    const key = part.slice(0, idx).trim();
    const value = part.slice(idx + 1).trim();
    if (!value) continue;
    if (key === "tenant") out.tenantId = value;
    if (key === "env") out.environmentId = value;
    if (key === "envName") out.environmentName = value;
    if (key === "org") out.org = value;
  }
  return out;
}

export function sourceEnvironmentLabel(s: SessionRow): string {
  const stamp = parseSourceStamp(s.pvci_datasource);
  if (!stamp) return "unknown";
  return stamp.environmentName ?? stamp.environmentId ?? stamp.org ?? "unknown";
}

export function isEssSession(s: SessionRow): boolean {
  const tag = `${s.pvci_botname ?? ""} ${s.pvci_botid ?? ""} ${s.pvci_topicname ?? ""}`.toLowerCase();
  return tag.includes("employee self-service") || tag.includes("copilotforemployeeselfservice") || tag.includes("ess");
}

/** Topic/tool names out of a DynamicPlan payload, e.g. "...topic.ServiceNowITSMGetUserTickets". */
export function planSteps(value: Json | undefined): string[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  const steps = (value as Record<string, Json>).steps;
  if (!Array.isArray(steps)) return [];
  return steps.filter((s): s is string => typeof s === "string").map((s) => s.split(".").pop() ?? s);
}
