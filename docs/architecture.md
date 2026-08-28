# Architecture

## Stable solution boundaries

Version `2.1.0.0` is the stable release identity for the three-package architecture after PVE
deployment, tenant-neutral package validation, hosted UI smoke, manual target-tenant upgrade, and
exact-byte clean installation. Core and code app are `2.1.0.0`; Credits remains unchanged at
`2.0.0.5`.

| Managed solution | Boundary |
| --- | --- |
| `pvConversationInsights` | Required transcript/shared core. Owns every table, plugin, Custom API, role, the model-driven app, inventory and transcript runtime, four transcript/shared flows, and three non-licensing connection references. |
| `pvConversationInsightsCredits` | Optional credit runtime add-on. Owns only three credit flows, `pvci_licensinghttp`, `pvci_powerplatformapi`, and the required `pvci_CreditReportingTenantId` definition; it contains no table schema, plugin, API, role, or app. |
| `pvConversationInsightsCodeApp` | Optional unsupported preview. Owns only the code app and its declared dependencies. |

Keeping all schema and server-side runtime in core avoids destructive data migration. Clean
installations use core, optional credits, then optional code app. Upgrades from `1.4.0.15` install credits first,
apply the core managed upgrade second, and upgrade the code app last. The order lets the add-on
claim the existing credit workflow identities before core relinquishes solution ownership.

The code app detects the optional runtime without making licensing access a transcript-analysis
dependency. Credits remains a visible destination with `Unavailable`, `Setup required`, and
`Ready` states. The app mounts credit data services only in Ready, after add-on presence and a
successful credit-sync record are both observed.

## Components

| Component | Runs where | Purpose |
| --- | --- | --- |
| `pvci_SyncConversationTranscripts` | Dataverse sandbox plugin | Incremental sync. No token needed — reads via `IOrganizationService` |
| Scheduled cloud flow | Power Automate | Calls the Custom API hourly in a drain loop |
| `probe_transcript_sources.py` | Local / CI during phase 1 | Builds a safe per-environment Dataverse transcript access registry from admin inventory |
| `sync_transcripts.py` | Local / CI | Same logic, uncapped — bulk backfill and re-derivation |
| `fetch_flow_run_details.py` | Local / CI | Pulls per-action inputs and outputs from the Power Automate API |
| PCF `JsonViewer` | Model-driven forms | Collapsible, searchable JSON rendering |
| Code app | Browser (preview) | Replay timeline, trends, tool and flow drill-down |
| `PVCI Collect Copilot Credit Usage` | Power Automate | Daily read-only PPAC resource usage and capacity collection with seven-day overlap |
| `PVCI Collect Tenant Agent Inventory` | Power Automate | Daily environment and agent inventory independent of credit activity |
| `PVCI Collect Credit Governance` | Power Automate | Daily read-only collection of per-agent threshold and enforcement state |
| `PVCI Apply Credit Governance Requests` | Power Automate | Serial read-before-write processor for audited per-agent threshold requests |
| `pvci_ImportCreditUsageBatch` | Dataverse sandbox plugin | Tenant validation, raw-response normalization, stable-key upsert, and sync audit |
| `CreditUserDisclosure` | Dataverse sandbox plugin | Shared approval audit, user-name resolution, and revocation cleanup |
| `ThresholdChangeRequestGuard` | Dataverse synchronous plugin | Forces Pending/server time, validates request shape, and strips caller-supplied outcomes |
| `pvci_ImportCentralTranscriptBatch` | Dataverse sandbox plugin | Imports bounded source-environment transcript batches with composite tenant/environment/transcript idempotency |
| `PVCI Collect Central Transcripts` | Packaged Power Automate flow in the core solution | Iterates Environment Inventory and uses Dataverse List rows from selected environment with a dynamic source URL before sending bounded batches to the collector API |
| `PVCI Verify Transcript Source Access` | Packaged Power Automate flow in the core solution | Processes only pending Source-managed `Verify` requests, performs one ID-only selected-environment read, and projects verified or denied access without claiming exact-role proof |
| Credit reporting surfaces | Model-driven app + code app | Agent/resource contribution, source periods, capacity, freshness, and data quality |
| `PVCI Analyst` / `PVCI Privacy Approver` / `PVCI Credit Administrator` / `PVCI Source Access Processor` | Dataverse security | Read-only analysis, separately authorized name disclosure, audited request submission, collector enablement after verification, and processor-only request outcome updates |

## Data model

See [Dataverse data model](data-model.md) for the complete table, column, relationship, key,
lineage, and retention reference.

```text
pvci_transcriptsession          one row per transcript
  ├─ pvci_UserId  →  systemuser (lookup, resolved from from.aadObjectId)
  ├─ environment: Power Platform EnvironmentId · EnvironmentName · DataSource lineage stamp
  ├─ latency:   FirstResponseMs · AvgResponseMs · MaxResponseMs
  ├─ tools:     ToolCallCount · ToolErrorCount · ToolTotalMs · MaxToolMs
  ├─ flows:     FlowRunCount · FlowRunFailureCount · FlowRunMaxMs
  ├─ outcome:   SessionOutcome · OutcomeReason · IsResolvedImplied · TurnCount
  ├─ flags:     IsTestMode · MultiUserAnomaly · PayloadTruncated
  └─ payloads:  ActivitiesJson · ConversationJson · PlanEventsJson
                MetadataJson · ToolCallsJson · FlowRunsJson

pvci_transcriptturn             one row per activity
  └─ pvci_SessionId → pvci_transcriptsession
     ActivityType · Speaker · Role · EventName · TimestampUtc · TurnText
     LatencyMs (on the first agent reply) · ValueJson

pvci_transcriptidentitymap      one row per distinct end user
pvci_syncstate                  watermark, last run status, last error
pvci_flowrundetail              one row per correlated run; pending until payload enrichment

pvci_environmentinventory       one row per tenant environment, independent of activity
  └─ pvci_agentinventory        one row per tenant/environment/resource
  └─ pvci_creditusage           one row per PPAC resource/source-period fact

pvci_inventorysyncrun           one row per Admin V2/One Inventory invocation
pvci_creditcapacitysnapshot     one row per environment/entitlement/as-of date
pvci_creditsyncrun              one row per collector/import invocation
pvci_credituserusage            one row per user/source-period fact; GUID label by default
pvci_creditprivacysetting       singleton shared name-disclosure approval
pvci_agentthresholdsnapshot     daily read-only per-agent control state
pvci_governancesyncrun          threshold collector health and outcomes
pvci_thresholdchangerequest     desired/expected state, lifecycle, and before/after audit

First-class `pvci_environmentid` and `pvci_environmentname` columns drive environment display and
filtering. `pvci_datasource` also carries a lineage stamp:
`dataverse_v9.1|tenant:<id>|env:<id>|envName:<name>|org:<host>`.
```

Credit reporting has a separate truth boundary from transcripts. PPAC values are actual aggregate
billing facts. Environment/resource/date overlap with sessions can explain likely drivers, but no
reviewed source exposes a billing-event ID that joins one charge to one transcript turn. See
[Copilot Credit reporting](credit-reporting.md) for source grain and per-user handling.

Credit governance uses a split-authority design. The browser can create a validated Pending request
but cannot call the Power Platform licensing API or update processor-owned outcomes. The flow owner
re-reads current state, rejects stale requests, writes one resource threshold, and reads back. A
post-write verification failure is recorded as `AppliedUnverified` rather than pretending the PUT
did not happen. Environment allocations, TenantPool, PayGo, and per-user limits are outside this
write path.

## Sync semantics

**Additive by default.** A transcript is immutable once Copilot Studio finalises it. An
already-ingested transcript is skipped *before* parsing — no re-parse, no rewrite, no turn
churn. This keeps turn row GUIDs stable, which matters for links and `createdon` audit.

**Watermark with a deliberate overlap.** The query uses `createdon ge <watermark>`, not `gt`.
Strict `gt` would permanently skip a row sharing the boundary second. Re-examining the boundary
is cheap because upsert keys on `pvci_transcriptid`.

**Failure isolation.** Each transcript is processed in its own try/except. On failure the
watermark *freezes*, so the failed transcript is retried next run rather than being skipped
forever. Status is recorded as `success` / `partial` / `failed` with errors in
`pvci_lasterror`.

**Turn replacement is insert-then-delete.** When reprocessing, new turns are written before
stale ones are removed, so a crash never leaves a session with zero turns.

**Throttling.** The Python client retries `429` / `502` / `503` / `504` up to five times,
honouring `Retry-After` with exponential backoff.

## Parsing the transcript

`content` is a JSON string containing a Bot Framework activity array. Only four fields are
guaranteed on every activity: `from`, `timestamp`, `timestampMs`, `type`.

> `timestamp` is **Unix epoch seconds**, not ISO 8601. `timestampMs` gives millisecond
> precision and is what all latency figures use.

Derived per session:

| Value | Source |
| --- | --- |
| End user | the single distinct `from.aadObjectId` where `role == 1` |
| Channel | the single distinct `channelId` |
| Environment label | Environment Inventory `pvci_displayname` joined by exact environment ID |
| Test mode | `ConversationInfo.isDesignMode` |
| Outcome | the `SessionInfo` trace |
| Primary topic | first `DynamicPlanStepTriggered.value.taskDialogId` |
| User-facing runtime failure | `ErrorTraceData` where `value.isUserError == true` |
| Knowledge retrieval | `KnowledgeTraceData` paired with the active search DynamicPlan step |
| Reply latency | user utterance → first agent reply, via `timestampMs` |
| Tool calls | `DialogTracing` actions of type `Invoke*`, paired start/end |
| Reasoning | `DynamicPlan*` events |

## Agent reasoning visualization

The Agent Reasoning view renders recorded orchestration telemetry as grouped chronological
sequences, not as a dependency graph. Across the validated sample, every `DynamicPlanReceived`
contained one selected step, while a conversation could create several successive plans. The view
therefore groups by `planIdentifier` and links `StepTriggered`, `StepBindUpdate`, `StepFinished`,
`PlanFinished`, and Knowledge outcomes by `stepId`.

The visualization shows request text already present in debug telemetry, selected topic/action,
recorded routing rationale, argument **names**, auto-filled markers, elapsed time, completion state,
and observable output/source identifiers. It does not show argument values by default and does not
claim to expose hidden chain-of-thought. Missing finish events remain explicit; an `Answered`
Knowledge outcome can establish successful retrieval even when `DynamicPlanStepFinished` was not
retained. Raw DynamicPlan JSON remains available through progressive disclosure.

User-facing error traces are retained as transcript turns even when general trace retention is
disabled. The session stores a filterable count, primary code/message/topic, and a bounded category
(`Authentication`, `Connector`, `Topic expression`, or `Topic runtime`). The code app reconstructs
the ordered failure timeline from those retained turns and the active DynamicPlan step. Internal
error traces and ordinary `DialogTracing` noise remain excluded unless trace retention is enabled.

Knowledge retrieval is not a connector invocation and must not be inferred from `DialogTracing`
`Invoke*` actions. `KnowledgeTraceData` supplies completion state, whether search ran, cited source
identifiers, and failed source types. The parser pairs it with the active search plan step for
start time and duration. Compact call JSON deliberately excludes query arguments and retrieved
passages; those remain only in the existing access-controlled raw transcript.

"Exactly one user per transcript" is asserted, not assumed — a violation sets
`MultiUserAnomaly` rather than silently taking the first.

## Latency

Only **answered** turns count. A user turn with no reply contributes nothing rather than zero,
which would understate the agent's slowness. Unanswered turns surface separately as the
answered-vs-total ratio in Trends.

Trends charts **p95 of each session's slowest reply**, not the mean, because means hide the
outliers you are looking for.

## Flow run correlation

`flowrun.conversationid` is **null**, so there is no join key. Correlation is by time overlap
(±20s), with candidates ranked by how closely they start to the span.

Two window sources, in order of precision:

| Source | Precision | Availability |
| --- | --- | --- |
| `DialogTracing` → `InvokeFlowAction` | Exact start/end | **Design mode only** |
| `DynamicPlanStepTriggered` → `…Finished` | Coarse window | All channels |

These measurements must not be added together:

- **Step window** (`span_ms`, source `plan_step`) is elapsed time from
  `DynamicPlanStepTriggered` to `DynamicPlanStepFinished`. It includes Copilot orchestration around
  the backend call and overlaps any matched flow runs; it is not flow runtime or a sum of runs.
- **Invoke span** (`span_ms`, source `flow_action`) is the exact design-mode invocation trace span.
- **Run time** (`duration_ms`) is the Power Automate run's own start-to-end duration.
- **Start delta** (`offset_ms`) is `flow run start - step/invocation start`. It ranks correlation
  candidates. A positive value means the run started later; it is not a measured queue, network,
  backend-wait, or orchestrator-processing duration.

Production channels emit **zero** `DialogTracing` activities, so they always use the plan-step
fallback. When a step has no `Finished` event the window runs to the next step or 90s,
whichever is sooner — a cap, not a measurement. Each entry is badged with its source and a
confidence of `high` / `multiple` / `none`.

ESS-style agents call an orchestrator that invokes child flows, so several genuine runs can
overlap one step. All are kept and ranked rather than guessing one.

The Flow API addresses flows by a **different id** than Dataverse. The bridge is the Flow API's
`workflowEntityId` property, which equals the Dataverse `workflowid`; the map is built at
runtime, nothing is hardcoded.

The sync paths also materialize one pending `pvci_flowrundetail` row per matched run. This is a
durable enrichment queue: row existence means the run was correlated, while `pvci_fetchedon`
means trigger, response, action, and repetition payloads were successfully collected. Native
`flowrun` parent/error fields are retained so orchestrator-child chains remain visible before
enrichment.

Full payload collection is a separate security boundary. It needs the Flow service audience and
short-lived SAS downloads; see [Full Power Automate run detail](flow-run-detail-findings.md).

## Design decisions worth knowing

**A hand-written JSON parser in the plugin.** ~250 lines of dependency-free C# instead of
Newtonsoft. Avoids NuGet plugin-package deployment and sandbox assembly-load risk; the cost is
that the parser is ours to maintain. It is deliberately minimal — no streaming, no big numbers.

**Noise filtering on by default.** `trace` activities and `DialogTracing` events are ~79% of
volume and are skipped. `IncludeTraces` keeps them at roughly 4× the row count.

**Two UI surfaces, not one.** The model-driven app is GA and standard-licensed — the
supportable option. The code app is preview and premium, but can do things forms cannot, such
as interleaving messages and reasoning in one chronological replay.

The code app starts in local-only mode. It obtains the host environment ID from Power Apps context,
scopes Sessions, Trends, and Credits resource reporting to that environment, and hides their
environment selectors. Credit user usage and recent governance request history remain tenant-wide.
If host context is unavailable, Credits fails closed instead of falling back to all environments.
Inventory remains
the sole cross-environment configuration surface. After an administrator verifies and explicitly
enables at least one remote source, the app reveals environment filters for cross-environment
diagnostics. There is no tenant picker because one installed solution serves one tenant. New records
use the first-class environment columns; legacy source stamps remain a read fallback. Sessions,
Trends, Inventory, and Credits share one persistent top-level navigation bar so destinations do not
move between workspaces. The sidebar is contextual: Sessions and Credits use it for dense filters
and selection, while Trends and Inventory retain the full workspace width.

Central collection begins with a read-only source registry. Power Platform Admins V2 can enumerate
tenant environments, but Dataverse table access is still evaluated in each source organization.
There is no documented tenant-wide API for raw transcripts. The Copilot Studio Monitor transcript
route observed in the portal HAR is a first-party interactive endpoint; reusable
`service.powerapps.com` tokens returned `403 UnauthenticatedUser` in two test environments.

The Microsoft Dataverse selected-environment connector solves routing, not authorization. A Power
Platform service-admin identity may therefore produce a mix of readable, empty, and access-denied
sources. In the PVE tenant probe, 9 of 11 environments were readable and 2 were denied. TPM failed
for every attempted environment because the mapped connection identity had no source transcript
privilege. The registry must retain those states rather than treating access failure as no data.

The existing sync plugin remains source-local. It uses the executing organization's
`IOrganizationService` and does not receive credentials for other organizations. The central flow
uses one selected-environment Dataverse connection and imports through
`pvci_ImportCentralTranscriptBatch`. The API enforces a 25-row maximum and keys sessions by tenant,
environment, and source transcript ID; a transcript GUID alone is not the cross-organization
contract. Operators manage tenant discovery health, source readiness, and collector enablement from
the code app's dedicated Inventory Management workspace. For every enabled row, the flow first
performs a one-row ID-only transcript probe, then reads and imports the bounded content batch.
A failed probe updates and disables only that inventory row through a handled branch; collection or
import failures after a successful probe remain unhandled. Environment inventory stores probe
status, collector enablement, watermark, last batch, status, and bounded error fields used by both
apps.

Source authorization has two supported policy modes that converge on the same permanent state: a
dedicated collector identity with a custom role whose only data privilege is organization-level
`prvReadconversationtranscript`, and no retained System Administrator role. In **Source-managed**
mode, a restricted environment's owner creates or approves the role and assigns the collector
identity; PVCI only verifies the one-row read. In **Administrator bootstrap** mode, an audited
external reconciler may temporarily elevate, create or repair the role, assign the collector
identity, remove elevation, prove cleanup, and verify access. **Excluded** is an explicit policy
state rather than a failure.

All onboarding controls belong to the code app's **Inventory Management** workspace. Each
environment exposes mode, lifecycle state, probe result, role/cleanup evidence, bounded errors, and
request history. The six readiness summaries are buttons that filter the environment list and stay
synchronized with the adjacent filter menu. Source-managed mode offers setup guidance and **Verify access** through the
user-owned `pvci_transcriptaccessrequest` audit table. The packaged verifier processes only
`Pending` + `Verify`; it never consumes `Provision`, `Repair`, or `Remove`. Administrator bootstrap
is visibly unavailable until an external reconciler is configured. Excluded environments cannot
enable collection. Collector enablement remains separate and is available only when onboarding is
`Verified` and access is `readable_with_rows` or `readable_empty`.

Microsoft's tenant-admin `addAppUser` endpoint is preview and grants System Administrator initially;
the GA `pac admin assign-user --application-user` route requires an external worker rather than a
solution-only cloud flow. Therefore, source-managed verification is the baseline for restricted
organizations and administrator bootstrap is an optional capability, never a prerequisite.

The required core solution is tenant-neutral and packages the importer, schema, model-driven app,
single Dataverse connection reference, and generic central flow. Environment identity and
enablement remain Dataverse rows, not solution metadata. In the `2.0.0.5` release, core derives
inventory tenant scope from current-organization metadata and has no dependency on the credit tenant
variable. The optional credit add-on contains its required variable definition, three flows, and two
licensing references, while the third managed solution contains only the preview code app and its
declared dependencies.

**Payload size guards.** Memo columns cap at 1,048,576 characters; writes are capped at 900,000
with pretty-print falling back to compact and then truncation, flagged by `PayloadTruncated`.
The largest observed activity payload was ~140 KB.

**Agent names are enriched.** Transcript metadata `BotName` is the Copilot Studio schema name
(`msdyn_...`), not display text. Both sync paths resolve it through `bot.schemaname` and store
`bot.name` in `pvci_botname`, falling back to the schema name only when bot metadata is unavailable.
The UI filters by stable `pvci_botid` while displaying the enriched name.
