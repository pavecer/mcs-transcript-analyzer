import { describe, expect, it } from "vitest";
import type { SessionRow, TurnRow } from "./model";
import {
  EMPTY_ESS_EVIDENCE_CONTEXT,
  EMPTY_ESS_EVIDENCE_FILTERS,
  buildEssEvidencePackage,
  describeEssEvidenceCandidate,
  essEvidenceFilename,
  filterEssEvidenceCandidates,
  hasEssEvidence,
  isEssEvidenceFilterActive,
  missingNarrativeFields,
  narrativeFields,
  resolveViewAfterEssEvidenceChange,
  selectEssEvidenceSession,
  selectEssEvidenceSessions,
  type ChecklistItem,
  type EssEvidenceContext,
} from "./essEvidence";

const HOST_ENVIRONMENT = "11111111-1111-1111-1111-111111111111";

const essSession = (overrides: Partial<SessionRow> = {}): SessionRow => ({
  pvci_transcriptsessionid: "ess-session-1",
  pvci_transcriptid: "transcript-1",
  pvci_name: "ESS session",
  pvci_botname: "msdyn_copilotforemployeeselfserviceit",
  pvci_environmentid: HOST_ENVIRONMENT,
  pvci_environmentname: "PVE Dev",
  pvci_channel: "msteams",
  pvci_startdatetimeutc: "2026-09-05T09:00:00Z",
  pvci_enddatetimeutc: "2026-09-05T09:04:00Z",
  pvci_durationseconds: 240,
  pvci_sessionoutcome: "unresolved",
  pvci_correlationstatus: "exact",
  ...overrides,
});

const nonEssSession = (overrides: Partial<SessionRow> = {}): SessionRow => ({
  pvci_transcriptsessionid: "other-session-1",
  pvci_name: "Other session",
  pvci_botname: "Contoso Sales Assistant",
  pvci_environmentid: HOST_ENVIRONMENT,
  ...overrides,
});

const context = (overrides: Partial<EssEvidenceContext> = {}): EssEvidenceContext => ({
  ...EMPTY_ESS_EVIDENCE_CONTEXT,
  outcome: "non-working",
  issueTitle: "Leave balance answer cites the wrong policy",
  observedBehavior: "The agent cited the US policy.",
  expectedBehavior: "The agent should cite the UK policy.",
  referencedKnowledgeUrls: ["https://contoso.example/us-policy"],
  expectedKnowledgeUrls: ["https://contoso.example/uk-policy"],
  investigationNotes: "Reproduced twice in Teams.",
  ...overrides,
});

const buildPackage = (
  session: SessionRow,
  detail: SessionRow | null = null,
  turns: TurnRow[] = [],
  overrides: Partial<EssEvidenceContext> = {},
  hostEnvironmentId: string | undefined = HOST_ENVIRONMENT,
) => buildEssEvidencePackage({
  session,
  detail,
  turns,
  context: context(overrides),
  generatedUtc: "2026-09-05T10:00:00.000Z",
  hostEnvironmentId,
});

const checklistEntry = (result: { completeness: { checklist: ChecklistItem[] } }, id: string): ChecklistItem =>
  result.completeness.checklist.find((entry) => entry.id === id)!;

describe("ESS Evidence activation", () => {
  it("activates from collected transcript sessions classified as ESS", () => {
    const sessions = [nonEssSession(), essSession()];
    expect(hasEssEvidence(sessions)).toBe(true);
    expect(selectEssEvidenceSessions(sessions).map((session) => session.pvci_transcriptsessionid))
      .toEqual(["ess-session-1"]);
  });

  it("stays absent when only non-ESS collected sessions exist, even for inventory or credit agents", () => {
    const inventoryOnly = [
      nonEssSession(),
      // An inventory or credit row naming an ESS agent is not collected transcript evidence.
      nonEssSession({ pvci_transcriptsessionid: "other-2", pvci_botname: "Contoso Billing Bot" }),
    ];
    expect(hasEssEvidence(inventoryOnly)).toBe(false);
    expect(selectEssEvidenceSessions(inventoryOnly)).toEqual([]);
  });

  it("stays absent when no transcripts were collected", () => {
    expect(hasEssEvidence([])).toBe(false);
  });

  it("returns to Sessions when qualifying evidence disappears while the workspace is active", () => {
    expect(resolveViewAfterEssEvidenceChange("essevidence", false, "essevidence", "sessions")).toBe("sessions");
    expect(resolveViewAfterEssEvidenceChange("essevidence", true, "essevidence", "sessions")).toBe("essevidence");
    expect(resolveViewAfterEssEvidenceChange("credits", false, "essevidence", "sessions")).toBe("credits");
  });

  it("cannot select or export a non-ESS session", () => {
    const sessions = [nonEssSession(), essSession()];
    expect(selectEssEvidenceSession(sessions, "other-session-1")).toBeNull();
    expect(selectEssEvidenceSession(sessions, "ess-session-1")?.pvci_transcriptsessionid).toBe("ess-session-1");
    expect(() => buildPackage(nonEssSession())).toThrow(/Only ESS-classified/);
  });

  it("summarizes the context an analyst needs to pick the right example", () => {
    const candidate = describeEssEvidenceCandidate(essSession({ pvci_istestmode: true, pvci_usererrorcount: 0 }));
    expect(candidate).toMatchObject({
      agentName: "msdyn_copilotforemployeeselfserviceit",
      environmentLabel: "PVE Dev",
      channel: "msteams",
      testMode: true,
      outcome: "unresolved",
    });
    expect(candidate.userErrors).toEqual({ state: "observed-zero", count: 0 });
    expect(describeEssEvidenceCandidate(essSession()).userErrors).toEqual({ state: "unavailable", count: null });
  });
});

describe("ESS Evidence package", () => {
  it("produces a deterministic schema version 1 package", () => {
    const first = buildPackage(essSession());
    const second = buildPackage(essSession());
    expect(first.schemaVersion).toBe(1);
    expect(first.evidenceFamily).toBe("ess");
    expect(JSON.stringify(first)).toBe(JSON.stringify(second));
  });

  it("records complete telemetry with exact, candidate, and observed-zero states preserved", () => {
    const session = essSession({
      pvci_istestmode: true,
      pvci_toolcallcount: 2,
      pvci_toolerrorcount: 0,
      pvci_knowledgecallcount: 1,
      pvci_knowledgesourcecount: 1,
      pvci_knowledgefailurecount: 0,
      pvci_flowruncount: 3,
      pvci_flowrunfailurecount: 0,
      pvci_usererrorcount: 1,
    });
    const detail: SessionRow = {
      ...session,
      pvci_toolcallsjson: JSON.stringify([{ action_id: "a1", action_type: "connector", failed: false, output: { ticketNumber: "INC1", requester: "Alex Example" } }]),
      pvci_knowledgecallsjson: JSON.stringify([{ searched: true, cited_sources: ["kb.Policy_ab12"], failed_source_types: [], failed: false, completion_state: "Answered" }]),
      pvci_flowrunsjson: JSON.stringify([{ name: "candidate-run" }]),
      pvci_planeventsjson: JSON.stringify([
        { name: "DynamicPlanReceived", at: "2026-09-05T09:00:01Z", value: { planIdentifier: "plan-1", isFinalPlan: true } },
        { name: "DynamicPlanStepTriggered", at: "2026-09-05T09:00:02Z", value: { planIdentifier: "plan-1", stepId: "s1", taskDialogId: "P:Search", type: "KnowledgeSource" } },
      ]),
    };

    const result = buildPackage(session, detail, [
      { pvci_transcriptturnid: "t1", pvci_turnindex: 0, pvci_activitytype: "message", pvci_speaker: "user", pvci_timestamputc: "2026-09-05T09:00:00Z", pvci_turntext: "How much leave do I have?" },
    ]);

    const telemetry = result.telemetryAvailability as Record<string, { state: string; count: number | null }>;
    expect(telemetry.exactToolTraces).toMatchObject({ state: "exact", count: 2 });
    expect(telemetry.toolFailures).toMatchObject({ state: "observed-zero", count: 0 });
    expect(telemetry.candidateFlowRuns).toMatchObject({ state: "candidate", count: 3 });
    expect(telemetry.knowledgeRetrievals).toMatchObject({ state: "exact", count: 1 });
    expect(telemetry.reasoningPlanEvents).toEqual({ state: "available" });

    const evidence = result.evidence as Record<string, Record<string, unknown>>;
    expect((evidence.reasoning.plans as unknown[]).length).toBe(1);
    expect(evidence.knowledge.citedSourceIdentifierNote).toMatch(/not URLs/);
    expect((evidence.knowledge.retrievals as Array<{ citedSourceIdentifiers: string[] }>)[0].citedSourceIdentifiers)
      .toEqual(["kb.Policy_ab12"]);
    expect(evidence.tools.rawOutputExported).toBe(false);
    expect((evidence.tools.calls as Array<{ outputKeys: string[] }>)[0].outputKeys).toEqual(["ticketNumber", "requester"]);
    expect(JSON.stringify(result)).not.toContain("INC1");

    expect(checklistEntry(result, "candidate-flow-evidence").state).toBe("present");
    expect(checklistEntry(result, "error-evidence").state).toBe("present");
  });

  it("keeps sparse evidence as not-stored rather than implying absence of behavior", () => {
    const result = buildPackage(essSession());
    const evidence = result.evidence as Record<string, Record<string, unknown>>;
    expect(evidence.reasoning.payloadState).toBe("not-stored");
    expect(evidence.knowledge.payloadState).toBe("not-stored");
    expect(result.conversation).toMatchObject({ state: "not-stored", retainedTurnCount: 0 });
    expect((result.timestamps as Record<string, unknown>).activityTimestampState).toBe("unavailable");
    expect(checklistEntry(result, "conversation-replay").state).toBe("not-stored");
    expect(checklistEntry(result, "error-evidence").state).toBe("unavailable");
  });

  it("reports malformed payloads as unavailable with a bounded warning instead of omitting them", () => {
    const detail: SessionRow = { ...essSession(), pvci_knowledgecallsjson: `{"broken":${"x".repeat(900)}` };
    const result = buildPackage(essSession(), detail);
    const evidence = result.evidence as Record<string, Record<string, unknown>>;
    const integrity = result.integrity as { warnings: string[] };

    expect(evidence.knowledge.payloadState).toBe("unavailable");
    expect(integrity.warnings.some((warning) => warning.startsWith("Knowledge calls payload is stored"))).toBe(true);
    integrity.warnings.forEach((warning) => expect(warning.length).toBeLessThanOrEqual(240));
    expect(checklistEntry(result, "knowledge-evidence").state).toBe("unavailable");
  });

  it("keeps observed zero distinct from unavailable telemetry", () => {
    const zero = buildPackage(essSession({ pvci_istestmode: true, pvci_toolcallcount: 0, pvci_usererrorcount: 0 }));
    const unavailable = buildPackage(essSession());
    const zeroTelemetry = zero.telemetryAvailability as Record<string, unknown>;
    const unavailableTelemetry = unavailable.telemetryAvailability as Record<string, unknown>;

    expect(zeroTelemetry.exactToolTraces).toMatchObject({ state: "observed-zero", count: 0 });
    expect(unavailableTelemetry.exactToolTraces).toMatchObject({ state: "unavailable", count: null });
    expect(checklistEntry(zero, "error-evidence").state).toBe("observed-zero");
  });

  it("marks exact tool and candidate flow evidence unavailable for a non-host, non-test transcript", () => {
    const session = essSession({
      pvci_environmentid: "22222222-2222-2222-2222-222222222222",
      pvci_flowruncount: 4,
    });
    const result = buildPackage(session, null, []);
    const telemetry = result.telemetryAvailability as Record<string, { state: string }>;
    const evidence = result.evidence as Record<string, Record<string, unknown>>;

    expect(telemetry.exactToolTraces.state).toBe("unavailable");
    expect(telemetry.candidateFlowRuns.state).toBe("unavailable");
    expect(evidence.candidateFlows.attributionState).toBe("unavailable");
    expect(evidence.candidateFlows.runs).toEqual([]);
    expect(checklistEntry(result, "tool-evidence").state).toBe("unavailable");
    expect(checklistEntry(result, "candidate-flow-evidence").state).toBe("unavailable");
  });

  it("surfaces payload truncation prominently", () => {
    const result = buildPackage(essSession({ pvci_payloadtruncated: true }));
    const integrity = result.integrity as { payloadTruncated: boolean; warnings: string[] };
    expect(integrity.payloadTruncated).toBe(true);
    expect(integrity.warnings[0]).toMatch(/truncated/);
  });

  it("does not claim the native transcript ID is the maker Debug conversation ID", () => {
    const provenance = buildPackage(essSession()).provenance as Record<string, Record<string, unknown>>;
    const session = provenance.session as Record<string, unknown>;
    expect(session.nativeTranscriptId).toBe("transcript-1");
    expect(session.debugConversationId).toMatchObject({ state: "unverified", value: null });
    expect((session.identityCorrelation as { state: string }).state).toBe("exact");
  });

  it("keeps unknown identity correlation unknown", () => {
    const unknown = buildPackage(essSession({ pvci_correlationstatus: undefined })).provenance as Record<string, Record<string, unknown>>;
    const candidate = buildPackage(essSession({ pvci_correlationstatus: "candidate" })).provenance as Record<string, Record<string, unknown>>;
    expect((unknown.session.identityCorrelation as { state: string }).state).toBe("unknown");
    expect((candidate.session.identityCorrelation as { state: string }).state).toBe("candidate");
  });

  it("always reports the external evidence an export cannot contain", () => {
    const completeness = buildPackage(essSession()).completeness as { missingExternalEvidence: ChecklistItem[] };
    expect(completeness.missingExternalEvidence.map((entry) => entry.id)).toEqual([
      "response-screenshot",
      "referenced-source-screenshot",
      "referenced-source-document-copy",
      "expected-source-screenshot",
      "expected-source-document-copy",
      "citation-har-capture",
      "debug-conversation-id",
    ]);
    expect(completeness.missingExternalEvidence.at(-1)?.state).toBe("unverified");
  });

  it("reports missing analyst context in the completeness checklist", () => {
    const result = buildPackage(essSession(), null, [], {
      issueTitle: "  ",
      observedBehavior: "",
      referencedKnowledgeUrls: ["  "],
    });
    expect(checklistEntry(result, "issue-title").state).toBe("missing");
    expect(checklistEntry(result, "observed-behavior").state).toBe("missing");
    expect(checklistEntry(result, "referenced-knowledge-urls").state).toBe("missing");
    expect(checklistEntry(result, "expected-behavior").state).toBe("present");
    expect(checklistEntry(result, "outcome-classification").state).toBe("present");
  });
});

describe("ESS Evidence privacy", () => {
  it("masks every export by default and records the Workday HR detector policy without calling it a general ESS policy", () => {
    const session = essSession({
      pvci_botname: "msdyn_copilotforemployeeselfservicehr",
      pvci_topicid: "msdyn_copilotforemployeeselfservicehr.topic.WorkdayEmployeeID",
      pvci_userdisplayname: "Alex Example",
      pvci_userupn: "alex.example@contoso.example",
      pvci_useraadobjectid: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      pvci_tenantid: "tttttttt-tttt-tttt-tttt-tttttttttttt",
    });
    const detail: SessionRow = {
      ...session,
      pvci_activitiesjson: JSON.stringify([{ value: { workdayResponse: { EmployeeName: "Alex Example", EmployeeId: "WD-12345" } } }]),
      pvci_primaryerrormessage: "Workday lookup failed for Alex Example (WD-12345).",
    };
    const turns: TurnRow[] = [
      { pvci_transcriptturnid: "t1", pvci_turnindex: 0, pvci_activitytype: "message", pvci_timestamputc: "2026-09-05T09:00:00Z", pvci_turntext: "Alex Example (alex.example@contoso.example), employee WD-12345, asked for leave." },
    ];

    const result = buildPackage(session, detail, turns);
    const serialized = JSON.stringify(result);
    const privacy = result.privacy as Record<string, unknown>;

    expect(privacy.maskingApplied).toBe(true);
    expect(privacy.independentOfOnScreenReveal).toBe(true);
    expect(privacy.workdayHrSession).toBe(true);
    expect((privacy.detectorPolicy as { id: string; scope: string }).id).toBe("workday-hr-v1");
    expect((privacy.detectorPolicy as { scope: string }).scope).toMatch(/Workday HR/);

    expect(serialized).not.toContain("Alex Example");
    expect(serialized).not.toContain("WD-12345");
    expect(serialized).not.toContain("alex.example@contoso.example");
    expect((privacy.replacementCount as number)).toBeGreaterThan(0);
  });

  it("does not let short Workday country codes corrupt unrelated words, IDs, or structural fields", () => {
    const session = essSession({
      pvci_botname: "msdyn_copilotforemployeeselfservicehr",
      pvci_topicid: "msdyn_copilotforemployeeselfservicehr.topic.WorkdayGetPassports",
      pvci_istestmode: true,
    });
    const detail: SessionRow = {
      ...session,
      // Country references in Workday passport/visa records are three-letter codes.
      pvci_activitiesjson: JSON.stringify([{
        value: {
          workdayResponse: {
            PassportId: [{ Country_Reference: "CAN" }, { Country_Reference: "IND" }],
            EmployeeName: "Alex Example",
          },
        },
      }]),
      pvci_planeventsjson: JSON.stringify([
        { name: "DynamicPlanStepTriggered", at: "2026-09-05T09:00:02Z", value: { planIdentifier: "p1", stepId: "51cc0e90-65af-4f00-ad2f-bc57372cane2", taskDialogId: "topic.WorkdayGetPassports", type: "CustomTopic" } },
      ]),
    };
    const turns: TurnRow[] = [
      { pvci_transcriptturnid: "t1", pvci_turnindex: 0, pvci_activitytype: "event", pvci_eventname: "DynamicPlanStepBindUpdate", pvci_timestamputc: "2026-09-05T09:00:02Z" },
      { pvci_transcriptturnid: "t2", pvci_turnindex: 1, pvci_activitytype: "message", pvci_timestamputc: "2026-09-05T09:00:03Z", pvci_turntext: "I can help you find that." },
    ];

    const result = buildPackage(session, detail, turns);
    const serialized = JSON.stringify(result);
    const provenance = result.provenance as Record<string, Record<string, unknown>>;
    const evidence = result.evidence as Record<string, Record<string, unknown>>;
    const plans = evidence.reasoning.plans as Array<{ steps: Array<{ id: string }> }>;
    const replay = (result.conversation as { replay: Array<{ eventName: string | null; text: string | null }> }).replay;

    expect(provenance.agent.classificationSource).toBe("canonical ESS transcript-session classification");
    expect(evidence.candidateFlows.attributionNote).toMatch(/^Candidate flow correlation/);
    expect(plans[0].steps[0].id).toBe("51cc0e90-65af-4f00-ad2f-bc57372cane2");
    expect(replay[0].eventName).toBe("DynamicPlanStepBindUpdate");
    expect(replay[1].text).toBe("I can help you find that.");
    expect(checklistEntry(result, "candidate-flow-evidence").label).toBe("Candidate flow evidence");
    expect(serialized).not.toContain("[MASKED:WORKDAY_DATA]onical");
    expect(serialized).not.toContain("[MASKED:WORKDAY_DATA]didate");
    // The real employee name must still be masked.
    expect(serialized).not.toContain("Alex Example");
  });

  it("exports response timing and conversation volume evidence", () => {
    const session = essSession({
      pvci_istestmode: true,
      pvci_firstresponsems: 115_395,
      pvci_avgresponsems: 59_354,
      pvci_maxresponsems: 115_395,
      pvci_maxtoolms: 14_545,
      pvci_tooltotalms: 0,
      pvci_messagecount: 5,
      pvci_userturncount: 2,
      pvci_agentturncount: 3,
    });
    const responsiveness = buildPackage(session).responsiveness as Record<string, { state: string; ms: number | null }>;
    const conversation = buildPackage(session).conversation as Record<string, { state: string; count: number | null }>;

    expect(responsiveness.firstReply).toMatchObject({ state: "exact", ms: 115_395 });
    expect(responsiveness.slowestExactTool).toMatchObject({ state: "exact", ms: 14_545 });
    expect(responsiveness.totalExactToolTime).toMatchObject({ state: "observed-zero", ms: 0 });
    expect(responsiveness.averageReply).toMatchObject({ state: "exact", ms: 59_354 });
    expect(conversation.messageCount).toMatchObject({ state: "exact", count: 5 });
    expect(conversation.userTurnCount).toMatchObject({ state: "exact", count: 2 });

    const missing = buildPackage(essSession()).responsiveness as Record<string, { state: string }>;
    expect(missing.firstReply.state).toBe("unavailable");
    expect(missing.slowestExactTool.state).toBe("unavailable");
  });

  it("redacts the tenant ID from the composite transcript ID, the data-source stamp, and the session name", () => {
    const tenantId = "6936469c-696e-4fe2-a0c8-dd16f54b1b45";
    const environmentId = "aa58895e-548b-ea31-b748-4a7cc046661e";
    const session = essSession({
      pvci_tenantid: tenantId,
      pvci_environmentid: environmentId,
      pvci_transcriptid: `${tenantId}:${environmentId}:4f244907-ead4-4fa6-bbd7-0e53bad048bb`,
      pvci_datasource: `plugin_v9.x_conversationtranscripts|tenant:${tenantId}|env:${environmentId}|envName:ESS_WD_Simplification`,
      pvci_name: "Alex Example · pva-studio · 2026-09-03T09:39:52Z",
      pvci_userdisplayname: "Alex Example",
      pvci_botname: "msdyn_copilotforemployeeselfservicehr",
    });

    const result = buildPackage(session);
    const serialized = JSON.stringify(result);
    const provenance = result.provenance as Record<string, Record<string, unknown>>;
    const sessionBlock = provenance.session as Record<string, unknown>;

    expect(serialized).not.toContain(tenantId);
    expect(sessionBlock.nativeTranscriptId).toBe(`[REDACTED:TENANT]:${environmentId}:4f244907-ead4-4fa6-bbd7-0e53bad048bb`);
    expect(provenance.environment.dataSourceStamp).not.toContain(tenantId);
    // The environment segment stays exact so support can still correlate the source.
    expect(provenance.environment.dataSourceStamp).toContain(environmentId);
    expect(sessionBlock.sessionName).not.toContain("Alex Example");
  });

  it("masks the tenant ID when it appears in free text, not only in known identifier fields", () => {
    const tenantId = "6936469c-696e-4fe2-a0c8-dd16f54b1b45";
    const session = essSession({ pvci_tenantid: tenantId, pvci_botname: "msdyn_copilotforemployeeselfservicehr" });
    const detail: SessionRow = {
      ...session,
      pvci_primaryerrormessage: `Workday call failed for tenant ${tenantId}.`,
    };
    const turns: TurnRow[] = [
      { pvci_transcriptturnid: "t1", pvci_turnindex: 0, pvci_activitytype: "message", pvci_timestamputc: "2026-09-05T09:00:00Z", pvci_turntext: `Trace shows tenant ${tenantId} in the request.` },
    ];

    expect(JSON.stringify(buildPackage(session, detail, turns))).not.toContain(tenantId);
  });

  it("never exports UPNs, AAD object IDs, tenant IDs, or raw tool output", () => {    const session = essSession({
      pvci_userupn: "worker@contoso.example",
      pvci_useraadobjectid: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      pvci_tenantid: "tttttttt-tttt-tttt-tttt-tttttttttttt",
      pvci_istestmode: true,
    });
    const detail: SessionRow = {
      ...session,
      pvci_toolcallsjson: JSON.stringify([{ action_id: "a1", output: { accessToken: "secret-token-value", record: "raw-payload-value" } }]),
    };
    const serialized = JSON.stringify(buildPackage(session, detail));

    expect(serialized).not.toContain("worker@contoso.example");
    expect(serialized).not.toContain("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
    expect(serialized).not.toContain("tttttttt-tttt-tttt-tttt-tttttttttttt");
    expect(serialized).not.toContain("secret-token-value");
    expect(serialized).not.toContain("raw-payload-value");
    expect(serialized).toContain("accessToken");
  });
});

describe("ESS Evidence analyst context rules", () => {
  it("requires expected behavior only for a non-working example", () => {
    const nonWorking = narrativeFields("non-working");
    const working = narrativeFields("working");

    expect(nonWorking.map((field) => [field.key, field.required])).toEqual([
      ["issueTitle", true],
      ["observedBehavior", true],
      ["expectedBehavior", true],
    ]);
    expect(working.map((field) => [field.key, field.required])).toEqual([
      ["issueTitle", true],
      ["observedBehavior", true],
      ["expectedBehavior", false],
    ]);
    expect(working[2].optionalHint).toBe("optional for a working example");
    expect(working[0].label).toBe("Example title");
  });

  it("reports only the outstanding required fields for the current classification", () => {
    const blankWorking: EssEvidenceContext = { ...EMPTY_ESS_EVIDENCE_CONTEXT, outcome: "working" };
    const blankNonWorking: EssEvidenceContext = { ...EMPTY_ESS_EVIDENCE_CONTEXT, outcome: "non-working" };

    expect(missingNarrativeFields(blankWorking).map((field) => field.key)).toEqual(["issueTitle", "observedBehavior"]);
    expect(missingNarrativeFields(blankNonWorking).map((field) => field.key)).toEqual(["issueTitle", "observedBehavior", "expectedBehavior"]);
    expect(missingNarrativeFields({ ...blankWorking, issueTitle: "Good answer", observedBehavior: "Cited the UK policy" })).toEqual([]);
  });

  it("records expected behavior as not-applicable for a blank working example", () => {
    const working = buildPackage(essSession(), null, [], { outcome: "working", expectedBehavior: "" });
    const nonWorking = buildPackage(essSession(), null, [], { outcome: "non-working", expectedBehavior: "" });
    expect(checklistEntry(working, "expected-behavior").state).toBe("not-applicable");
    expect(checklistEntry(nonWorking, "expected-behavior").state).toBe("missing");
  });
});

describe("ESS Evidence picker filtering", () => {
  const rows = [
    describeEssEvidenceCandidate(essSession({ pvci_transcriptsessionid: "a", pvci_botname: "ESS HR", pvci_istestmode: true, pvci_usererrorcount: 2 })),
    describeEssEvidenceCandidate(essSession({ pvci_transcriptsessionid: "b", pvci_botname: "ESS IT", pvci_environmentname: "PVE Preview", pvci_usererrorcount: 0 })),
  ];

  it("returns everything when no filter is set", () => {
    expect(isEssEvidenceFilterActive(EMPTY_ESS_EVIDENCE_FILTERS)).toBe(false);
    expect(filterEssEvidenceCandidates(rows, EMPTY_ESS_EVIDENCE_FILTERS)).toHaveLength(2);
  });

  it("filters by agent, environment, mode, user errors, and free text", () => {
    const only = (filters: Partial<typeof EMPTY_ESS_EVIDENCE_FILTERS>) =>
      filterEssEvidenceCandidates(rows, { ...EMPTY_ESS_EVIDENCE_FILTERS, ...filters }).map((row) => row.sessionId);

    expect(only({ agent: "ESS IT" })).toEqual(["b"]);
    expect(only({ environment: "PVE Preview" })).toEqual(["b"]);
    expect(only({ mode: "test" })).toEqual(["a"]);
    expect(only({ mode: "production" })).toEqual(["b"]);
    expect(only({ errorsOnly: true })).toEqual(["a"]);
    expect(only({ search: "preview" })).toEqual(["b"]);
    expect(only({ search: "no-such-value" })).toEqual([]);
    expect(isEssEvidenceFilterActive({ ...EMPTY_ESS_EVIDENCE_FILTERS, search: " " })).toBe(false);
  });
});

describe("ESS Evidence filename", () => {
  it("sanitizes the analyst title and stays deterministic", () => {
    const name = essEvidenceFilename("ess-session-1", "Leave balance / wrong policy!", "2026-09-05T10:00:00.000Z");
    expect(name).toBe("ess-evidence-leave-balance-wrong-policy-ess-session-20260905100000.json");
    expect(essEvidenceFilename("ess-session-1", "Leave balance / wrong policy!", "2026-09-05T10:00:00.000Z")).toBe(name);
  });

  it("falls back safely for empty or hostile input", () => {
    expect(essEvidenceFilename("", "", "")).toBe("ess-evidence-untitled-issue-session-00000000000000.json");
    expect(essEvidenceFilename("../../etc/passwd", "../../etc/passwd", "2026-09-05T10:00:00.000Z"))
      .toBe("ess-evidence-etc-passwd-etcpasswd-20260905100000.json");
  });
});
