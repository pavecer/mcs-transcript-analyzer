import type { SessionRow } from "./model";

export const TRANSCRIPT_PRIVACY_POLICY_VERSION = "workday-hr-v1";

export interface TranscriptMaskingResult<T> {
  value: T;
  replacementCount: number;
  categoryCounts: Record<string, number>;
}

export interface MaskedTranscriptExport {
  schemaVersion: 1;
  maskingPolicy: string;
  generatedUtc: string;
  masking: {
    replacementCount: number;
    categoryCounts: Record<string, number>;
  };
  transcript: unknown;
}

export interface TranscriptRoleAssignment {
  systemuserid?: string;
  roleid?: string;
}

const WORKDAY_HR_AGENT = "msdyn_copilotforemployeeselfservicehr";

const WHOLE_SUBTREE_FIELDS = new Set([
  "workdayresponse",
  "parsedworkdayresponse",
  "workdayresult",
  "workdayoutput",
  "workdaydata",
  "finalizedresponsetabledata",
  "finalizedemergencycontactdata",
  "finalizeddata",
]);

const CATEGORY_FIELDS: Array<[string, Set<string>]> = [
  ["PERSON", new Set(["firstname", "middlename", "lastname", "fullname", "displayname", "userdisplayname", "preferredname", "legalname", "workerdescriptor", "descriptor", "employeename", "contactname"])],
  ["IDENTIFIER", new Set(["employeeid", "employeenumber", "workerid", "personid", "personnumber", "workdayid", "wid", "aadobjectid", "useraadobjectid", "userid", "upn", "userupn", "nationalid", "nationalidentifier", "passportid", "passportnumber", "visaid", "taxid", "addressid"])],
  ["CONTACT", new Set(["email", "emailaddress", "businessemail", "personalemail", "primarycontactemail", "phone", "phonenumber", "mobile", "mobilephone", "telephone", "primarycontactphone"])],
  ["ADDRESS", new Set(["address", "addressline1", "addressline2", "addressline3", "street", "city", "postalcode", "postcode", "zipcode", "homeaddress", "workaddress", "contactaddress", "formattedaddress", "countryofresidence"])],
  ["DATE_OF_BIRTH", new Set(["dateofbirth", "birthdate", "dob"])],
  ["FINANCIAL", new Set(["bankaccount", "bankaccountnumber", "iban", "swift", "sortcode", "routingnumber", "salary", "compensation", "payrate", "basepay", "bonus", "amount", "currency"] )],
  ["HR_DATA", new Set(["gender", "maritalstatus", "ethnicity", "religion", "disability", "medical", "absencereason", "leavebalance", "managername", "managerid", "relationshiptoemployee", "emergencycontacts", "employmentdata", "languageinfo", "visainformation", "passportinformation"])],
  ["SECRET", new Set(["accesstoken", "refreshtoken", "authorization", "clientsecret", "password", "secret"])],
];

const TEXT_PATTERNS: Array<[string, RegExp]> = [
  ["EMAIL", /(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])/gi],
  ["UK_NINO", /(?<![A-Z0-9])[A-CEGHJ-PR-TW-Z]{2}\s?\d{6}\s?[A-D](?![A-Z0-9])/gi],
  ["US_SSN", /(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)/g],
  ["IBAN", /(?<![A-Z0-9])[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){11,30}(?![A-Z0-9])/gi],
  ["PHONE", /(?<![\w\d])(?:\+\d{1,3}(?:[ .-]?\d){7,14}|\(?0\d{2,4}\)?[ .-]\d(?:[ .-]?\d){5,10})(?![\w\d])/g],
  ["UK_POSTCODE", /(?<![A-Z0-9])[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}(?![A-Z0-9])/gi],
  ["IP_ADDRESS", /(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])/g],
];

interface MaskingState {
  harvested: Map<string, string>;
  replacementCount: number;
  categoryCounts: Record<string, number>;
}

function normalizeField(name: string): string {
  return name.replace(/[^a-z0-9]/gi, "").toLowerCase();
}

function fieldCategory(name: string): string | undefined {
  const normalized = normalizeField(name);
  const logicalName = normalized.startsWith("pvci") ? normalized.slice(4) : normalized;
  if (WHOLE_SUBTREE_FIELDS.has(normalized)) return "WORKDAY_DATA";
  for (const [category, fields] of CATEGORY_FIELDS) {
    if (fields.has(normalized) || fields.has(logicalName)) return category;
  }
  return undefined;
}

function tryParseEmbeddedJson(value: string): unknown | undefined {
  const trimmed = value.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return undefined;
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return undefined;
  }
}

function harvest(node: unknown, state: MaskingState, forcedCategory?: string): void {
  if (node === null || node === undefined) return;
  if (typeof node === "string") {
    const embedded = tryParseEmbeddedJson(node);
    if (embedded !== undefined) {
      harvest(embedded, state, forcedCategory);
    } else if (forcedCategory && node.trim().length >= 3) {
      state.harvested.set(node.trim().toLowerCase(), forcedCategory);
    }
    return;
  }
  if (Array.isArray(node)) {
    node.forEach((item) => harvest(item, state, forcedCategory));
    return;
  }
  if (typeof node === "object") {
    Object.entries(node).forEach(([key, value]) => {
      harvest(value, state, forcedCategory ?? fieldCategory(key));
    });
  }
}

function recordReplacement(state: MaskingState, category: string, count = 1): string {
  state.replacementCount += count;
  state.categoryCounts[category] = (state.categoryCounts[category] ?? 0) + count;
  return `[MASKED:${category}]`;
}

function replaceText(value: string, state: MaskingState): string {
  let result = value;
  const harvested = [...state.harvested.entries()].sort(([left], [right]) => right.length - left.length);
  for (const [source, category] of harvested) {
    const expression = new RegExp(source.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    const matches = result.match(expression);
    if (matches?.length) {
      result = result.replace(expression, recordReplacement(state, category, matches.length));
    }
  }
  for (const [category, expression] of TEXT_PATTERNS) {
    expression.lastIndex = 0;
    const matches = result.match(expression);
    if (matches?.length) {
      result = result.replace(expression, recordReplacement(state, category, matches.length));
    }
  }
  return result;
}

function maskNode(node: unknown, state: MaskingState, forcedCategory?: string): unknown {
  if (node === null || node === undefined) return node;
  if (typeof node === "string") {
    const embedded = tryParseEmbeddedJson(node);
    if (embedded !== undefined) {
      return JSON.stringify(maskNode(embedded, state, forcedCategory));
    }
    if (forcedCategory) return recordReplacement(state, forcedCategory);
    return replaceText(node, state);
  }
  if (typeof node === "number" || typeof node === "boolean") {
    return forcedCategory ? recordReplacement(state, forcedCategory) : node;
  }
  if (Array.isArray(node)) return node.map((item) => maskNode(item, state, forcedCategory));
  if (typeof node === "object") {
    return Object.fromEntries(
      Object.entries(node).map(([key, value]) => [
        key,
        maskNode(value, state, forcedCategory ?? fieldCategory(key)),
      ]),
    );
  }
  return node;
}

export function isWorkdayHrSession(session: SessionRow): boolean {
  const botName = session.pvci_botname?.trim().toLowerCase();
  const topicId = session.pvci_topicid?.trim().toLowerCase();
  return botName === WORKDAY_HR_AGENT
    || Boolean(topicId?.startsWith(`${WORKDAY_HR_AGENT}.topic.workday`));
}

export function maskTranscriptData<T>(value: T): TranscriptMaskingResult<T> {
  const state: MaskingState = { harvested: new Map(), replacementCount: 0, categoryCounts: {} };
  harvest(value, state);
  return {
    value: maskNode(value, state) as T,
    replacementCount: state.replacementCount,
    categoryCounts: state.categoryCounts,
  };
}

export function buildMaskedTranscriptExport(value: unknown, generatedUtc: string): MaskedTranscriptExport {
  const masked = maskTranscriptData(value);
  return {
    schemaVersion: 1,
    maskingPolicy: TRANSCRIPT_PRIVACY_POLICY_VERSION,
    generatedUtc,
    masking: {
      replacementCount: masked.replacementCount,
      categoryCounts: masked.categoryCounts,
    },
    transcript: masked.value,
  };
}

export function maskedTranscriptFilename(sessionId: string): string {
  const safeId = sessionId.replace(/[^a-z0-9-]/gi, "").slice(0, 12) || "session";
  return `transcript-${safeId}-masked.json`;
}

export function hasTranscriptRevealRole(
  systemUserId: string | undefined,
  privacyRoleIds: string[],
  assignments: TranscriptRoleAssignment[],
): boolean {
  if (!systemUserId || privacyRoleIds.length === 0) return false;
  const normalizedUserId = systemUserId.toLowerCase();
  const normalizedRoleIds = new Set(privacyRoleIds.map((roleId) => roleId.toLowerCase()));
  return assignments.some((assignment) =>
    assignment.systemuserid?.toLowerCase() === normalizedUserId
    && Boolean(assignment.roleid && normalizedRoleIds.has(assignment.roleid.toLowerCase()))
  );
}