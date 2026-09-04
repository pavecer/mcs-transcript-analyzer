import { describe, expect, it } from "vitest";
import type { SessionRow } from "./model";
import {
  buildMaskedTranscriptExport,
  hasTranscriptRevealRole,
  isWorkdayHrSession,
  maskedTranscriptFilename,
  maskTranscriptData,
} from "./transcriptPrivacy";

const session = (overrides: Partial<SessionRow> = {}): SessionRow => ({
  pvci_transcriptsessionid: "session-1",
  pvci_name: "Session",
  pvci_botname: "msdyn_copilotforemployeeselfservicehr",
  pvci_topicid: "msdyn_copilotforemployeeselfservicehr.topic.WorkdayEmployeeID",
  ...overrides,
});

describe("transcript privacy", () => {
  it("targets the exact ESS HR agent and Workday topic identity without tenant hardcoding", () => {
    expect(isWorkdayHrSession(session())).toBe(true);
    expect(isWorkdayHrSession(session({ pvci_botname: "Renamed", pvci_topicid: "msdyn_copilotforemployeeselfservicehr.topic.WorkdayGetVisas" }))).toBe(true);
    expect(isWorkdayHrSession(session({ pvci_botname: "Employee Self-Service IT", pvci_topicid: "topic.WorkdayEmployeeID" }))).toBe(false);
    expect(isWorkdayHrSession(session({ pvci_botname: "Custom HR", pvci_topicid: "topic.HR" }))).toBe(false);
  });

  it("masks observed Workday structures and repeated values across transcript surfaces", () => {
    const source = {
      activities: [
        {
          type: "event",
          timestamp: "2026-09-03T09:39:52Z",
          value: {
            taskDialogId: "Workday.GetWorker",
            workdayResponse: JSON.stringify({
              EmployeeName: "Alex Example",
              EmployeeId: "WD-12345",
              EmploymentData: [{ Salary: 123456, Department: "Sensitive Department" }],
              EmergencyContacts: [{ Personal_Data: { Contact_Data: { Address_Data: [{ Postal_Code: "SW1A 1AA" }], Phone_Data: { Phone_Number: "+44 7700 900123" } } } }],
              PassportId: [{ Country_Reference: { "@Descriptor": "United Kingdom" } }],
              VisaId: [{ Country_Reference: { "@Descriptor": "United Kingdom" } }],
            }),
          },
        },
        {
          type: "message",
          text: "Alex Example (alex.example@example.test), employee WD-12345, is in Sensitive Department.",
          value: {
            parsedWorkdayResponse: { EmployeeName: "Alex Example", EmployeeId: "WD-12345" },
            observation: { finalizedData: { EmployeeName: "Alex Example", CompanyCode: "PRIVATE-CO" } },
          },
        },
      ],
      toolCalls: [{ output: { workdayResponse: "not-json-workday-output" } }],
    };
    const original = JSON.stringify(source);

    const result = maskTranscriptData(source);
    const masked = JSON.stringify(result.value);

    expect(JSON.stringify(source)).toBe(original);
    expect(masked).not.toContain("Alex Example");
    expect(masked).not.toContain("WD-12345");
    expect(masked).not.toContain("Sensitive Department");
    expect(masked).not.toContain("alex.example@example.test");
    expect(masked).not.toContain("+44 7700 900123");
    expect(masked).not.toContain("SW1A 1AA");
    expect(masked).not.toContain("PRIVATE-CO");
    expect(result.value.activities[0].type).toBe("event");
    expect(result.value.activities[0].timestamp).toBe("2026-09-03T09:39:52Z");
    expect(result.value.activities[0].value.taskDialogId).toBe("Workday.GetWorker");
    expect(result.value.toolCalls[0].output.workdayResponse).toBe("[MASKED:WORKDAY_DATA]");
    expect(result.replacementCount).toBeGreaterThan(10);
    expect(result.categoryCounts.WORKDAY_DATA).toBeGreaterThan(0);
  });

  it("preserves nulls, arrays, ordinary operational data, and malformed non-sensitive strings", () => {
    const source = {
      statusCode: 200,
      completionState: "Completed",
      records: [],
      optional: null,
      malformed: "{not-json",
      nested: [{ employeeId: "WD-999" }],
    };

    const result = maskTranscriptData(source);

    expect(result.value).toEqual({
      statusCode: 200,
      completionState: "Completed",
      records: [],
      optional: null,
      malformed: "{not-json",
      nested: [{ employeeId: "[MASKED:IDENTIFIER]" }],
    });
  });

  it("builds a masked download contract without source identities or unsafe filenames", () => {
    const bundle = {
      session: {
        pvci_transcriptsessionid: "ABCDEF12-3456-7890-ABCD-EF1234567890",
        pvci_userdisplayname: "Alex Example",
        pvci_userupn: "alex.example@example.test",
      },
      turns: [{ pvci_turntext: "Alex Example requested employee WD-12345", pvci_valuejson: "{\"employeeId\":\"WD-12345\"}" }],
    };

    const result = buildMaskedTranscriptExport(bundle, "2026-09-03T12:00:00.000Z");
    const json = JSON.stringify(result);

    expect(result.schemaVersion).toBe(1);
    expect(result.maskingPolicy).toBe("workday-hr-v1");
    expect(result.generatedUtc).toBe("2026-09-03T12:00:00.000Z");
    expect(json).not.toContain("Alex Example");
    expect(json).not.toContain("alex.example@example.test");
    expect(json).not.toContain("WD-12345");
    expect(JSON.parse(json)).toEqual(result);
    expect(maskedTranscriptFilename("ABCDEF12-3456-7890-ABCD-EF1234567890")).toBe("transcript-ABCDEF12-345-masked.json");
    expect(maskedTranscriptFilename("../../unsafe")).toBe("transcript-unsafe-masked.json");
  });

  it("allows reveal only for an exact direct Privacy Approver role assignment", () => {
    const assignments = [
      { systemuserid: "USER-1", roleid: "ANALYST" },
      { systemuserid: "USER-2", roleid: "PRIVACY-ROLE" },
      { systemuserid: "USER-1", roleid: "privacy-role" },
    ];

    expect(hasTranscriptRevealRole("user-1", ["PRIVACY-ROLE", "OTHER-BU-COPY"], assignments)).toBe(true);
    expect(hasTranscriptRevealRole("user-2", ["OTHER-BU-COPY"], assignments)).toBe(false);
    expect(hasTranscriptRevealRole(undefined, ["PRIVACY-ROLE"], assignments)).toBe(false);
    expect(hasTranscriptRevealRole("user-1", [], assignments)).toBe(false);
  });
});