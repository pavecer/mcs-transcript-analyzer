import { describe, expect, it } from "vitest";
import type { SessionRow, TurnRow } from "./model";
import { groupSessionRows, mergeSessionDetails, mergeTurnRows } from "./sessionPresentation";

const session = (id: string, start: string, end: string, overrides: Partial<SessionRow> = {}): SessionRow => ({
  pvci_transcriptsessionid: id,
  pvci_transcriptid: `transcript-${id}`,
  pvci_name: id,
  pvci_useraadobjectid: "user-1",
  pvci_botid: "bot-1",
  pvci_channel: "msteams",
  pvci_environmentid: "environment-1",
  pvci_startdatetimeutc: start,
  pvci_enddatetimeutc: end,
  pvci_messagecount: 2,
  ...overrides,
});

describe("session presentation", () => {
  it("groups matching source transcripts separated by a short handoff", () => {
    const groups = groupSessionRows([
      session("later", "2026-09-09T07:43:32Z", "2026-09-09T07:44:55Z", { pvci_messagecount: 5 }),
      session("earlier", "2026-09-09T07:43:03Z", "2026-09-09T07:43:28Z"),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0]).toMatchObject({
      sessionIds: ["later", "earlier"],
      start: "2026-09-09T07:43:03Z",
      end: "2026-09-09T07:44:55Z",
      messageCount: 7,
      sourceSessionCount: 2,
    });
    expect(groups[0].primary.pvci_durationseconds).toBe(112);
  });

  it("does not group nearby records with a different bot, user, channel, or environment", () => {
    const anchor = session("anchor", "2026-09-09T07:43:32Z", "2026-09-09T07:44:00Z");
    const groups = groupSessionRows([
      anchor,
      session("other-bot", "2026-09-09T07:43:00Z", "2026-09-09T07:43:28Z", { pvci_botid: "bot-2" }),
      session("other-user", "2026-09-09T07:43:00Z", "2026-09-09T07:43:28Z", { pvci_useraadobjectid: "user-2" }),
      session("other-channel", "2026-09-09T07:43:00Z", "2026-09-09T07:43:28Z", { pvci_channel: "web" }),
      session("other-environment", "2026-09-09T07:43:00Z", "2026-09-09T07:43:28Z", { pvci_environmentid: "environment-2" }),
    ]);

    expect(groups).toHaveLength(5);
  });

  it("does not group matching records separated by more than 30 seconds", () => {
    const groups = groupSessionRows([
      session("later", "2026-09-09T07:44:00Z", "2026-09-09T07:44:20Z"),
      session("earlier", "2026-09-09T07:43:00Z", "2026-09-09T07:43:29Z"),
    ]);

    expect(groups).toHaveLength(2);
  });

  it("merges turns from multiple source sessions into a continuous sequence", () => {
    const earlierTurns: TurnRow[] = [
      { pvci_transcriptturnid: "t1", pvci_turnindex: 1, pvci_timestamputc: "2026-09-09T07:43:03Z", pvci_turntext: "Can you bring me latest 3 large Jira issues?" },
      { pvci_transcriptturnid: "t2", pvci_turnindex: 2, pvci_timestamputc: "2026-09-09T07:43:10Z", pvci_turntext: "Here is JIRA-123" },
    ];
    const laterTurns: TurnRow[] = [
      { pvci_transcriptturnid: "t3", pvci_turnindex: 1, pvci_timestamputc: "2026-09-09T07:43:32Z", pvci_turntext: "Yes please extract the next one" },
      { pvci_transcriptturnid: "t4", pvci_turnindex: 2, pvci_timestamputc: "2026-09-09T07:43:40Z", pvci_turntext: "Here is JIRA-124" },
    ];

    const merged = mergeTurnRows([laterTurns, earlierTurns]);
    expect(merged.map((t) => ({ index: t.pvci_turnindex, text: t.pvci_turntext }))).toEqual([
      { index: 1, text: "Can you bring me latest 3 large Jira issues?" },
      { index: 2, text: "Here is JIRA-123" },
      { index: 3, text: "Yes please extract the next one" },
      { index: 4, text: "Here is JIRA-124" },
    ]);
  });

  it("merges detailed session payloads across multiple source transcripts", () => {
    const primary = session("earlier", "2026-09-09T07:43:03Z", "2026-09-09T07:44:55Z");
    const detail1: SessionRow = {
      ...primary,
      pvci_conversationjson: JSON.stringify([
        { n: 1, speaker: "user", at: "2026-09-09T07:43:03Z", text: "Issue 1?" },
        { n: 2, speaker: "agent", at: "2026-09-09T07:43:10Z", text: "Got it" },
      ]),
      pvci_planeventsjson: JSON.stringify([
        { name: "DynamicPlanReceived", at: 1788793600, value: { step: 1 } },
      ]),
    };
    const detail2: SessionRow = {
      ...primary,
      pvci_conversationjson: JSON.stringify([
        { n: 1, speaker: "user", at: "2026-09-09T07:43:32Z", text: "Next one" },
      ]),
      pvci_planeventsjson: JSON.stringify([
        { name: "DynamicPlanFinished", at: 1788793650, value: { step: 2 } },
      ]),
    };

    const merged = mergeSessionDetails([detail1, detail2], primary);
    const conv = JSON.parse(merged.pvci_conversationjson ?? "[]");
    const plan = JSON.parse(merged.pvci_planeventsjson ?? "[]");

    expect(conv).toHaveLength(3);
    expect(conv[0].n).toBe(1);
    expect(conv[1].n).toBe(2);
    expect(conv[2].n).toBe(3);
    expect(conv[2].text).toBe("Next one");
    expect(plan).toHaveLength(2);
  });
});
