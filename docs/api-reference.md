# Dataverse `conversationtranscripts` API Reference

## Scope

Copilot Studio conversation transcripts via the Dataverse Web API.

| | |
| --- | --- |
| Status | Verified against a live environment |
| Validated | 2026-07-31 |
| Environment | `PVE Dev` — `006cf8b9-27f8-e2f7-8a14-9be3642d8552` |
| Org URL | `https://org760734c4.crm4.dynamics.com` |
| Tenant | `1938ee32-a258-454c-b8db-3a928341bd69` |
| Sample size | 8 transcripts · 457 activities · 3 channels · 2 users |

---

## 1. Why this endpoint

Copilot Studio surfaces transcripts in two different places, and they are **not** the same data.

| | Monitor / Analytics export | `conversationtranscripts` (this doc) |
| --- | --- | --- |
| Transport | `GET /api/botmanagement/v1/transcript` on the regional gateway | Dataverse Web API |
| Format | CSV, one row per session | JSON, full Bot Framework activity stream |
| End-user identity | ✗ not present | ✅ `from.aadObjectId` |
| Orchestration / reasoning events | ✗ dropped | ✅ full `DynamicPlan*` + `DialogTracing` |
| Callable with a normal token | ✗ rejects non-first-party tokens (`403 UnauthenticatedUser`) | ✅ standard Dataverse auth |
| Usable from a plugin / flow | ✗ | ✅ |

For any programmatic use — sync, analytics, forensics — **use `conversationtranscripts`**. It is both the accessible path and the richer one.

> **Note on the "empty table" symptom.** A common report is that this table "looks empty". In practice the causes are: (a) querying before the conversation has been finalised and flushed, (b) the signed-in user lacking read privilege on the table, or (c) transcript capture being disabled on the agent. The table is populated asynchronously after a session ends — it is not written turn-by-turn in real time.

---

## 2. Endpoints

### 2.1 List transcripts

```http
GET {orgUrl}/api/data/v9.1/conversationtranscripts
      ?$select=conversationtranscriptid,createdon,modifiedon
      &$orderby=createdon desc
      &$top=50
```

```http
Authorization: Bearer {token}      # audience = {orgUrl}
Accept: application/json
OData-MaxVersion: 4.0
OData-Version: 4.0
```

**`200 OK`**

```json
{
  "@odata.context": "…/$metadata#conversationtranscripts(…)",
  "value": [
    { "conversationtranscriptid": "1580540b-1503-4e1c-8d6d-4bfb90608200",
      "createdon": "2026-07-30T11:36:36Z",
      "modifiedon": "2026-07-30T11:36:36Z" }
  ]
}
```

### 2.2 Retrieve one transcript with payload

```http
GET {orgUrl}/api/data/v9.1/conversationtranscripts({id})
      ?$select=conversationtranscriptid,metadata,content,createdon,modifiedon
```

Returns the same fields plus the two payload columns described below. `content` is large — roughly **12–100 KB** per transcript in the sample. Do **not** `$select` it when listing.

### 2.3 Incremental sync (recommended)

```http
GET {orgUrl}/api/data/v9.1/conversationtranscripts
      ?$select=conversationtranscriptid,metadata,content,createdon
      &$filter=createdon gt 2026-07-30T00:00:00Z
      &$orderby=createdon asc
```

`v9.1` and `v9.2` both work. Standard OData paging applies via `@odata.nextLink`; use the `Prefer: odata.maxpagesize=N` header to control page size.

---

## 3. Payload columns

Both are **strings containing JSON** — you must parse them a second time.

### 3.1 `metadata`

Small (~160 chars). Identifies the agent. All four keys were present on 8 of 8 transcripts.

```json
{
  "BotId":       "2db5b951-04fb-6b65-7504-e6c289d3aa5d",
  "AADTenantId": "1938ee32-a258-454c-b8db-3a928341bd69",
  "BotName":     "msdyn_copilotforemployeeselfserviceit",
  "BatchId":     0
}
```

| Key | Notes |
| --- | --- |
| `BotId` | Agent id. **Not** the same as the `botId` in maker-portal URLs |
| `AADTenantId` | Entra tenant |
| `BotName` | Agent schema name |
| `BatchId` | Ingestion batching artifact; `0` throughout the sample |

### 3.2 `content`

Exactly one top-level key on 8 of 8 transcripts:

```json
{ "activities": [ … ] }
```

---

## 4. The activity object

An ordered Bot Framework activity stream. **457 activities across 8 transcripts** (range 8–132, median ~35).

### 4.1 Guaranteed vs. optional fields

Only these four appear on **every** activity:

```text
from · timestamp · timestampMs · type
```

Every other field is conditional. **A parser must treat all of the following as optional:**

```text
attachments · channelData · channelId · id · name
replyToId · text · textFormat · value · valueType
```

### 4.2 Field reference

| Field | Type | Notes |
| --- | --- | --- |
| `type` | string | See §4.3 |
| `timestamp` | **integer** | ⚠️ **Unix epoch seconds** — not ISO 8601 |
| `timestampMs` | integer | Same instant in milliseconds |
| `from.role` | integer | `0` = agent · `1` = end user |
| `from.id` | string | Channel-scoped participant id, not an Entra id |
| `from.aadObjectId` | string (GUID) | **Entra object id of the end user.** Present only when `role = 1` |
| `channelId` | string | `msteams` · `m365copilot` · `pva-studio` |
| `text` | string | Utterance body (on `message`) |
| `id` | string | Activity id, prefixed form e.g. `f:a2b1ec97-…` |
| `replyToId` | string | Threading pointer to a prior activity |
| `name` | string | Event name (on `event`) |
| `value` / `valueType` | any / string | Typed payload for events and traces |
| `attachments` | array | Adaptive Cards etc. |
| `channelData` | object | See §4.4 |

> ⚠️ **The single most common parsing bug.** `timestamp` is an integer epoch, so naive ISO date
> parsing fails silently or throws. Convert explicitly:

```python
datetime.fromtimestamp(int(a["timestamp"]), tz=timezone.utc)
```

### 4.3 Activity types observed

| `type` | Count | Meaning |
| --- | --- | --- |
| `event` | 215 | Orchestration + dialog telemetry (§4.5) |
| `trace` | 180 | Internal diagnostics |
| `message` | 51 | **Human-readable turns** |
| `invoke` | 3 | Client-invoked operation |
| `invokeResponse` | 3 | Its result |
| `installationUpdate` | 3 | App install lifecycle |
| `conversationUpdate` | 2 | Membership change |

Only **~11%** of activities are `message`. To reconstruct the readable conversation, filter to `type == "message"` **and** require non-empty `text` — several messages carry only `attachments`.

Role distribution across all activities: `role 0` (agent) = 422, `role 1` (user) = 35.

### 4.4 `channelData`

Keys observed, with frequency:

```text
feedbackLoop 29 · tenant 19 · source 10 · legacy 4
enableDiagnostics 4 · testMode 4 · clientActivityID 4
settings 3 · postBack 3 · attachmentSizes 1
```

Sample:

```json
{
  "settings": { "selectedChannel": {
      "id": "19:0833bba9-…_69e92b1d-…@unq.gbl.spaces" } },
  "tenant":   { "id": "1938ee32-a258-454c-b8db-3a928341bd69" },
  "source":   { "name": "message" }
}
```

`feedbackLoop` is the hook for thumbs-up/down signals. `testMode` distinguishes maker-portal test chats from real traffic.

### 4.5 Event names — the reasoning trace

| `name` | Count | Meaning |
| --- | --- | --- |
| `DialogTracing` | 180 | Fine-grained dialog step telemetry |
| `DynamicPlanReceived` | 6 | Generative orchestrator produced a plan |
| `DynamicPlanReceivedDebug` | 6 | Debug variant with fuller detail |
| `DynamicPlanStepTriggered` | 6 | A plan step began |
| `DynamicPlanStepBindUpdate` | 6 | Step input/output binding |
| `DynamicPlanStepFinished` | 3 | Step completed |
| `DynamicPlanFinished` | 3 | Plan completed |
| `pvaSetContext` | 3 | Context injected at session start |
| `startConversation` | 2 | Session opened |

**This is the highest-value content in the payload and it exists in no other export.** The `DynamicPlan*` family reconstructs *why* the agent did what it did — which tool or topic it selected, what it bound, and whether the step completed. Use it for root-causing wrong-answer and wrong-topic complaints.

---

## 5. Correlating a transcript to an end user

This is the question the CSV export cannot answer. Here it is deterministic.

**Verified across all 8 transcripts: each transcript contains exactly one distinct `aadObjectId` and exactly one distinct `channelId`.**

```text
1580540b  users=1 [0833bba9]  chans={msteams}
64b02c27  users=1 [0833bba9]  chans={msteams}
a3979f8a  users=1 [0833bba9]  chans={m365copilot}
25c87ad2  users=1 [0833bba9]  chans={m365copilot}
c4f11590  users=1 [4992e828]  chans={m365copilot}
b95b2a6e  users=1 [4992e828]  chans={msteams}
50fc72a1  users=1 [0833bba9]  chans={pva-studio}
28c79c3d  users=1 [0833bba9]  chans={pva-studio}
```

### 5.1 Derivation rules

```text
user_aad_object_id = the single distinct from.aadObjectId where role == 1
channel            = the single distinct channelId
session_start_utc  = min(timestamp)   → epoch seconds
session_end_utc    = max(timestamp)   → epoch seconds
agent              = metadata.BotName / metadata.BotId
tenant             = metadata.AADTenantId
```

Treat "exactly one user" as an **assertion, not an assumption** — if a transcript ever yields more than one, flag it rather than silently taking the first.

### 5.2 Resolving to a Dataverse user

`from.aadObjectId` maps to `systemuser.azureactivedirectoryobjectid`:

```http
GET {orgUrl}/api/data/v9.1/systemusers
      ?$select=systemuserid,fullname,domainname,internalemailaddress
      &$filter=azureactivedirectoryobjectid eq {aadObjectId}
```

That yields UPN and display name — the full pairing from transcript to named employee.

### 5.3 There is no conversation id

`activity.conversation` was **`null`** on every activity inspected, and no `conversationId` key appears anywhere in `channelData`. **Do not build joins on a conversation id.**

Consequences:

- The `conversationtranscriptid` GUID is the only stable primary key. Use it.
- A `/debug` conversation id obtained from a live chat will **not** match `conversationtranscriptid`. This is the root cause of the "lookup by conversation id returns 404" symptom.
- To locate the transcript for a known incident, filter by `aadObjectId` + `createdon` window + channel instead.

For Teams specifically, `channelData.settings.selectedChannel.id` has the form `19:{aadObjectId}_{guid}@unq.gbl.spaces` and embeds the user id — a useful secondary signal, but channel-specific and not a general key.

---

## 6. Reference: reconstructing a readable conversation

```python
import json
from datetime import datetime, timezone

def parse(row):
    meta = json.loads(row["metadata"]) if row.get("metadata") else {}
    acts = json.loads(row["content"])["activities"] if row.get("content") else []

    users = {a.get("from", {}).get("aadObjectId")
             for a in acts if a.get("from", {}).get("aadObjectId")}
    chans = {a["channelId"] for a in acts if a.get("channelId")}
    stamps = [int(a["timestamp"]) for a in acts if a.get("timestamp")]

    def utc(ts):
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    turns = [
        {
            "index": i,
            "speaker": "user" if (a.get("from") or {}).get("role") == 1 else "agent",
            "text": a.get("text") or "",
            "at": utc(int(a["timestamp"])),
        }
        for i, a in enumerate(acts)
        if a.get("type") == "message" and (a.get("text") or "").strip()
    ]

    return {
        "transcript_id": row["conversationtranscriptid"],
        "bot_name": meta.get("BotName"),
        "tenant_id": meta.get("AADTenantId"),
        "user_aad_object_id": next(iter(users), None),
        "multi_user_anomaly": len(users) > 1,
        "channel": next(iter(chans), None),
        "started_utc": utc(min(stamps)) if stamps else None,
        "ended_utc": utc(max(stamps)) if stamps else None,
        "activity_count": len(acts),
        "message_count": len(turns),
        "turns": turns,
    }
```

---

## 7. Access requirements

- **Token audience must be the org URL** (`https://{org}.crm4.dynamics.com/.default`), not `service.powerapps.com`.
- The caller needs **Read** privilege on the `Conversation Transcript` entity. Absent it, queries return an empty set rather than `403` — which reads exactly like "the table is empty".
- A Dataverse **plugin or custom API needs no token at all** — it reads the table through `IOrganizationService` in-process, which sidesteps the auth question entirely.

---

## 8. Practical caveats

1. `content` is undeclared and version-free. Parse defensively; assume only the four guaranteed fields.
2. Payloads reach ~100 KB. Avoid `$select`ing `content` in list queries.
3. Transcripts appear **after** a session finalises, not during. Allow lag before concluding data is missing.
4. Retention is governed by environment settings — sync out anything you intend to keep long-term.
5. Transcript bodies contain user-authored text and must be treated as personal data: restrict table privileges, apply retention, and audit access.
6. `channelData.testMode` marks maker-portal test chats — exclude them before reporting on production volumes.

---

## 9. Copilot Credit source routes

The scheduled collector uses **HTTP with Microsoft Entra ID (preauthorized)** against
`https://licensing.powerplatform.microsoft.com/`. These observed routes are read-only reporting
dependencies and are not published as a conventional stable REST contract. Persist source/schema
versions and retain bounded raw lineage.

| Projection | Request | Grain and use |
| --- | --- | --- |
| Resource usage | `GET /v2.0/tenants/{tenantId}/entitlements/MCSMessages/resources?fromDate={date}&toDate={date}&pageNumber={n}&pageSize=100&includeFields=users` | Aggregate resource/agent source-period billed and non-billed usage |
| Environment capacity | `GET /v2.0/tenants/{tenantId}/environments/entitlementConsumptions/MCSMessages` | Environment allocation, consumption, available quantity, PAYG, and policy snapshot |
| Tenant daily trend | `GET /v1.0/tenants/{tenantId}/capacityTypes/MCSMessages/trends?interval=daily` | Tenant-level capacity trend; not per-agent billing |
| User usage | `GET /v2.0/tenants/{tenantId}/entitlements/MCSMessages/users?fromDate={date}&toDate={date}` | Separate user/source-period projection, stored GUID-first behind shared name approval |

Resource rows observed in the test tenant contain `resourceId`, optional `environmentId`,
`asOfDate`, `consumed`, `unit`, and metadata including `ResourceName`, `NonBillableQuantity`, and
optional `Users`. The users response contains nested rows with `userId`, `asOfDate`, `consumed`,
`unit`, `metadata.NonBillableQuantity`, and `metadata.Resources`.

Resource and user projections are alternative views of consumption. Never sum them together.
Neither supplies a shared billing-event ID for an exact transcript/action join. See
[Copilot Credit reporting](credit-reporting.md) for source-period behavior and privacy controls.

### Agent threshold governance

Threshold governance uses a separate HTTP with Microsoft Entra ID connection and audience:
`https://api.powerplatform.com/`. It must not reuse the licensing reporting connection.

```http
GET /licensing/entitlements/MCSMessages/resourceThresholds?api-version=2024-10-01
```

The response is tenant-wide and keyed by `environmentId` plus `resourceId`. PVCI preserves limit,
resource consumption, notification percentage/flag, stop-at-limit, explicit stop, source time, and
raw lineage in daily `pvci_agentthresholdsnapshot` rows.

An authorized processor applies one resource request through:

```http
PUT /licensing/environments/{environmentId}/entitlements/MCSMessages/
  resources/{resourceId}/threshold?api-version=2024-10-01
```

The body carries `limit`, `notificationThreshold`, `notifyIfOverCapacity`,
`stopIfOverCapacity`, `stopResource`, and the current `resourceConsumption`. The browser does not
call this route. It creates `pvci_thresholdchangerequest`; a synchronous plug-in forces Pending and
strips outcome fields, and the flow compares every expected value with a fresh GET before PUT.
After PUT it reads back and stores before/after JSON. A post-PUT verification failure is
`AppliedUnverified`. The processor contains no environment allocation, TenantPool, or PayGo route.

---

## 10. `pvci_ImportCreditUsageBatch`

Unbound Dataverse Custom API implemented by `PvciTranscripts.ImportCreditUsageBatch`:

```http
POST {dataverseUrl}/api/data/v9.1/pvci_ImportCreditUsageBatch
Content-Type: application/json
Authorization: Bearer {dataverse-token}
```

Request envelope:

```json
{
  "PayloadJson": "{\"tenantId\":\"...\",\"agents\":[],\"usage\":[],\"capacity\":[],\"syncRun\":{...}}",
  "SourceSchemaVersion": "ppac-v2-resource-aggregate-v1",
  "DryRun": false
}
```

`PayloadJson` accepts either normalized `agents`, `usage`, and `capacity` arrays or raw
`ppacResourcePages` and `ppacCapacity` responses from the scheduled collector. Raw responses are
normalized inside the plug-in so the flow does not duplicate source mapping logic.

Response:

```json
{
  "Created": 0,
  "Updated": 12,
  "Skipped": 0,
  "Rejected": 0,
  "Status": "success",
  "Errors": ""
}
```

Behavior and limits:

- validates `tenantId` against the Dataverse organization tenant when that value is available;
- computes stable SHA-256 source keys and upserts idempotently;
- preserves unknown harnesses, features, and unresolved resources rather than guessing;
- caps `PayloadJson` at 900,000 characters and each array at 2,000 records;
- caps stored text/raw JSON and returned errors;
- `DryRun: true` performs validation and reports would-create/would-update counts without writes;
- one malformed record is rejected without discarding valid records in the same bounded batch;
- the plug-in performs no outbound HTTP and holds no licensing-service credential.

For raw `ppacUsers`, the importer stores source IDs and billing facts in `pvci_credituserusage`.
It resolves names only when the singleton `pvci_creditprivacysetting.pvci_revealusernames` is true.
Changing that field invokes `PvciTranscripts.CreditUserDisclosure` synchronously: approval records
the initiating user/time and resolves names; revocation clears display name, UPN, system-user ID,
and restores the source GUID as the primary label.
