import type { SessionRow, TurnRow } from "./model";

const CONTINUITY_GAP_MS = 30_000;

export interface PresentedSessionGroup {
  primary: SessionRow;
  sourceSessions: SessionRow[];
  sessionIds: string[];
  start?: string;
  end?: string;
  messageCount?: number;
  sourceSessionCount: number;
}

function sameConversationScope(left: SessionRow, right: SessionRow): boolean {
  const fields = ["pvci_useraadobjectid", "pvci_botid", "pvci_channel", "pvci_environmentid"] as const;
  return fields.every((field) => Boolean(left[field]) && left[field] === right[field]);
}

function parsedTime(value?: string): number | undefined {
  if (!value) return undefined;
  const time = Date.parse(value);
  return Number.isNaN(time) ? undefined : time;
}

function canContinue(group: PresentedSessionGroup, candidate: SessionRow): boolean {
  if (!sameConversationScope(group.primary, candidate)) return false;
  const groupStart = parsedTime(group.start);
  const groupEnd = parsedTime(group.end);
  const candidateStart = parsedTime(candidate.pvci_startdatetimeutc);
  const candidateEnd = parsedTime(candidate.pvci_enddatetimeutc);
  if (groupStart === undefined || groupEnd === undefined || candidateStart === undefined || candidateEnd === undefined) return false;
  return candidateEnd + CONTINUITY_GAP_MS >= groupStart && candidateStart - CONTINUITY_GAP_MS <= groupEnd;
}

function sumOrNull(...values: Array<number | null | undefined>): number | undefined {
  const numbers = values.filter((v): v is number => typeof v === "number");
  if (!numbers.length) return undefined;
  return numbers.reduce((acc, n) => acc + n, 0);
}

function maxOrNull(...values: Array<number | null | undefined>): number | undefined {
  const numbers = values.filter((v): v is number => typeof v === "number");
  if (!numbers.length) return undefined;
  return Math.max(...numbers);
}

function buildMergedPrimary(sessions: SessionRow[], start?: string, end?: string): SessionRow {
  const sorted = [...sessions].sort((a, b) => (parsedTime(a.pvci_startdatetimeutc) ?? 0) - (parsedTime(b.pvci_startdatetimeutc) ?? 0));
  const earliest = sorted[0];
  const latest = sorted[sorted.length - 1];

  const startTime = parsedTime(start);
  const endTime = parsedTime(end);
  const durationSeconds = startTime !== undefined && endTime !== undefined
    ? Math.max(0, Math.round((endTime - startTime) / 1000))
    : sumOrNull(...sessions.map((s) => s.pvci_durationseconds));

  const firstUserMsg = sorted.find((s) => s.pvci_initialusermessage)?.pvci_initialusermessage;
  const lastAgentMsg = [...sorted].reverse().find((s) => s.pvci_lastagentmessage)?.pvci_lastagentmessage;
  const firstReply = sorted.find((s) => s.pvci_firstresponsems != null)?.pvci_firstresponsems;

  const errorSession = sorted.find((s) => (s.pvci_usererrorcount ?? 0) > 0 || (s.pvci_toolerrorcount ?? 0) > 0);
  const activeError = errorSession ?? latest;

  return {
    ...latest,
    pvci_transcriptsessionid: earliest.pvci_transcriptsessionid,
    pvci_transcriptid: earliest.pvci_transcriptid,
    pvci_startdatetimeutc: start,
    pvci_enddatetimeutc: end,
    pvci_durationseconds: durationSeconds,
    pvci_messagecount: sumOrNull(...sessions.map((s) => s.pvci_messagecount)),
    pvci_activitycount: sumOrNull(...sessions.map((s) => s.pvci_activitycount)),
    pvci_eventcount: sumOrNull(...sessions.map((s) => s.pvci_eventcount)),
    pvci_userturncount: sumOrNull(...sessions.map((s) => s.pvci_userturncount)),
    pvci_agentturncount: sumOrNull(...sessions.map((s) => s.pvci_agentturncount)),
    pvci_turncount: sumOrNull(...sessions.map((s) => s.pvci_turncount)),
    pvci_toolcallcount: sumOrNull(...sessions.map((s) => s.pvci_toolcallcount)),
    pvci_toolerrorcount: sumOrNull(...sessions.map((s) => s.pvci_toolerrorcount)),
    pvci_tooltotalms: sumOrNull(...sessions.map((s) => s.pvci_tooltotalms)),
    pvci_maxtoolms: maxOrNull(...sessions.map((s) => s.pvci_maxtoolms)),
    pvci_knowledgecallcount: sumOrNull(...sessions.map((s) => s.pvci_knowledgecallcount)),
    pvci_knowledgesourcecount: sumOrNull(...sessions.map((s) => s.pvci_knowledgesourcecount)),
    pvci_knowledgefailurecount: sumOrNull(...sessions.map((s) => s.pvci_knowledgefailurecount)),
    pvci_flowruncount: sumOrNull(...sessions.map((s) => s.pvci_flowruncount)),
    pvci_flowrunfailurecount: sumOrNull(...sessions.map((s) => s.pvci_flowrunfailurecount)),
    pvci_flowrunmaxms: maxOrNull(...sessions.map((s) => s.pvci_flowrunmaxms)),
    pvci_usererrorcount: sumOrNull(...sessions.map((s) => s.pvci_usererrorcount)),
    pvci_maxresponsems: maxOrNull(...sessions.map((s) => s.pvci_maxresponsems)),
    pvci_firstresponsems: firstReply,
    pvci_initialusermessage: firstUserMsg,
    pvci_lastagentmessage: lastAgentMsg,
    pvci_istestmode: sessions.some((s) => s.pvci_istestmode),
    pvci_multiuseranomaly: sessions.some((s) => s.pvci_multiuseranomaly),
    pvci_payloadtruncated: sessions.some((s) => s.pvci_payloadtruncated),
    pvci_sessionoutcome: activeError.pvci_sessionoutcome ?? latest.pvci_sessionoutcome,
    pvci_outcomereason: activeError.pvci_outcomereason ?? latest.pvci_outcomereason,
    pvci_primaryerrorcode: activeError.pvci_primaryerrorcode,
    pvci_primaryerrormessage: activeError.pvci_primaryerrormessage,
    pvci_primaryerrortopic: activeError.pvci_primaryerrortopic,
    pvci_errorcategory: activeError.pvci_errorcategory,
  };
}

function addToGroup(group: PresentedSessionGroup, candidate: SessionRow): PresentedSessionGroup {
  const groupStart = parsedTime(group.start)!;
  const groupEnd = parsedTime(group.end)!;
  const candidateStart = parsedTime(candidate.pvci_startdatetimeutc)!;
  const candidateEnd = parsedTime(candidate.pvci_enddatetimeutc)!;

  const newStart = candidateStart < groupStart ? candidate.pvci_startdatetimeutc : group.start;
  const newEnd = candidateEnd > groupEnd ? candidate.pvci_enddatetimeutc : group.end;
  const allSessions = [...group.sourceSessions, candidate];

  return {
    primary: buildMergedPrimary(allSessions, newStart, newEnd),
    sourceSessions: allSessions,
    sessionIds: [...group.sessionIds, candidate.pvci_transcriptsessionid],
    start: newStart,
    end: newEnd,
    messageCount: sumOrNull(...allSessions.map((s) => s.pvci_messagecount)),
    sourceSessionCount: group.sourceSessionCount + 1,
  };
}

export function groupSessionRows(rows: SessionRow[]): PresentedSessionGroup[] {
  const groups: PresentedSessionGroup[] = [];

  for (const row of rows) {
    const group = groups.find((candidate) => canContinue(candidate, row));
    if (group) {
      const index = groups.indexOf(group);
      groups[index] = addToGroup(group, row);
      continue;
    }
    groups.push({
      primary: row,
      sourceSessions: [row],
      sessionIds: [row.pvci_transcriptsessionid],
      start: row.pvci_startdatetimeutc,
      end: row.pvci_enddatetimeutc,
      messageCount: row.pvci_messagecount,
      sourceSessionCount: 1,
    });
  }

  return groups;
}

export function mergeTurnRows(turnsList: TurnRow[][]): TurnRow[] {
  const allTurns = turnsList.flat();
  if (allTurns.length <= 1) return allTurns;

  const sorted = [...allTurns].sort((a, b) => {
    const timeA = parsedTime(a.pvci_timestamputc) ?? 0;
    const timeB = parsedTime(b.pvci_timestamputc) ?? 0;
    if (timeA !== timeB) return timeA - timeB;
    return (a.pvci_turnindex ?? 0) - (b.pvci_turnindex ?? 0);
  });

  return sorted.map((turn, index) => ({
    ...turn,
    pvci_turnindex: index + 1,
  }));
}

function tryParseArray(json?: string): unknown[] {
  if (!json) return [];
  try {
    const parsed = JSON.parse(json);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function mergeSessionDetails(details: Array<SessionRow | null>, primarySession: SessionRow): SessionRow {
  const valid = details.filter((d): d is SessionRow => d !== null);
  if (!valid.length) return primarySession;
  if (valid.length === 1) return { ...primarySession, ...valid[0] };

  // 1. Activities JSON
  const activities = valid.flatMap((d) => tryParseArray(d.pvci_activitiesjson));
  activities.sort((a, b) => {
    const tsA = typeof a === "object" && a !== null ? ((a as Record<string, unknown>).timestamp as number | undefined) ?? 0 : 0;
    const tsB = typeof b === "object" && b !== null ? ((b as Record<string, unknown>).timestamp as number | undefined) ?? 0 : 0;
    return tsA - tsB;
  });

  // 2. Conversation JSON: { n, speaker, at, text }
  const conversation = valid.flatMap((d) => tryParseArray(d.pvci_conversationjson) as Array<Record<string, unknown>>);
  conversation.sort((a, b) => (parsedTime(a.at as string) ?? 0) - (parsedTime(b.at as string) ?? 0));
  const reindexedConv = conversation.map((c, i) => ({ ...c, n: i + 1 }));

  // 3. Plan Events JSON: { name, at, value }
  const planEvents = valid.flatMap((d) => tryParseArray(d.pvci_planeventsjson) as Array<Record<string, unknown>>);
  planEvents.sort((a, b) => (parsedTime(a.at as string) ?? 0) - (parsedTime(b.at as string) ?? 0));

  // 4. Tool Calls JSON
  const toolCalls = valid.flatMap((d) => tryParseArray(d.pvci_toolcallsjson) as Array<Record<string, unknown>>);
  toolCalls.sort((a, b) => (parsedTime(a.started_utc as string) ?? 0) - (parsedTime(b.started_utc as string) ?? 0));

  // 5. Knowledge Calls JSON
  const knowledgeCalls = valid.flatMap((d) => tryParseArray(d.pvci_knowledgecallsjson) as Array<Record<string, unknown>>);
  knowledgeCalls.sort((a, b) => (parsedTime(a.started_utc as string) ?? 0) - (parsedTime(b.started_utc as string) ?? 0));

  // 6. Flow Runs JSON
  const flowRuns = valid.flatMap((d) => tryParseArray(d.pvci_flowrunsjson));

  return {
    ...primarySession,
    pvci_activitiesjson: activities.length ? JSON.stringify(activities) : undefined,
    pvci_conversationjson: reindexedConv.length ? JSON.stringify(reindexedConv) : undefined,
    pvci_planeventsjson: planEvents.length ? JSON.stringify(planEvents) : undefined,
    pvci_toolcallsjson: toolCalls.length ? JSON.stringify(toolCalls) : undefined,
    pvci_knowledgecallsjson: knowledgeCalls.length ? JSON.stringify(knowledgeCalls) : undefined,
    pvci_flowrunsjson: flowRuns.length ? JSON.stringify(flowRuns) : undefined,
    pvci_metadatajson: valid[0]?.pvci_metadatajson ?? valid[valid.length - 1]?.pvci_metadatajson,
    pvci_primaryerrormessage: valid.find((d) => d.pvci_primaryerrormessage)?.pvci_primaryerrormessage,
  };
}
