# Architecture

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
| Credit reporting surfaces | Model-driven app + code app | Agent/resource contribution, source periods, capacity, freshness, and data quality |
| `PVCI Analyst` / `PVCI Privacy Approver` / `PVCI Credit Administrator` | Dataverse security | Read-only analysis, separately authorized name disclosure, and audited threshold request submission |

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
| Test mode | `ConversationInfo.isDesignMode` |
| Outcome | the `SessionInfo` trace |
| Reply latency | user utterance → first agent reply, via `timestampMs` |
| Tool calls | `DialogTracing` actions of type `Invoke*`, paired start/end |
| Reasoning | `DynamicPlan*` events |

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

The code app supports ESS-scoped cross-environment diagnostics through an environment filter.
There is no tenant picker because one installed solution serves one tenant. New records use the
first-class environment columns; legacy source stamps remain a read fallback.

Central collection begins with a read-only source registry. Power Platform Admins V2 can
enumerate tenant environments, but Dataverse table access is still evaluated in each source
organization. A Power Platform service-admin identity may therefore produce a mix of readable,
empty, and access-denied sources. The registry must retain those states rather than treating an
access failure as an environment with no transcripts.

The existing sync plugin remains source-local. It uses the executing organization's
`IOrganizationService` and does not receive credentials for other organizations. The central flow
reads approved sources through source-specific Power Automate connections and imports through
`pvci_ImportCentralTranscriptBatch`. The API enforces a 25-row maximum and keys sessions by tenant,
environment, and source transcript ID; a transcript GUID alone is not the cross-organization
contract. Environment inventory stores probe status, collector enablement, watermark, last batch,
status, and bounded error fields used by both apps.

The public core solution is tenant-neutral and packages the importer, schema, model-driven app,
single Dataverse connection reference, and generic central flow. Environment identity and
enablement remain Dataverse rows, not solution metadata. The second managed solution contains only
the preview code app and its declared dependencies.

**Payload size guards.** Memo columns cap at 1,048,576 characters; writes are capped at 900,000
with pretty-print falling back to compact and then truncation, flagged by `PayloadTruncated`.
The largest observed activity payload was ~140 KB.

**Agent names are enriched.** Transcript metadata `BotName` is the Copilot Studio schema name
(`msdyn_...`), not display text. Both sync paths resolve it through `bot.schemaname` and store
`bot.name` in `pvci_botname`, falling back to the schema name only when bot metadata is unavailable.
The UI filters by stable `pvci_botid` while displaying the enriched name.
