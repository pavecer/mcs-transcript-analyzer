# Operations

## Configuration

Copy the sample and fill it in — environment-specific configs are gitignored.

```bash
cp config/transcript_solution_config.sample.json config/transcript_solution_config.dev.json
```

| Key | Notes |
| --- | --- |
| `tenantId` | Entra tenant GUID |
| `environmentId` | Required Power Platform environment GUID from the maker portal URL; stored in `pvci_environmentid` |
| `environmentName` | Optional friendly-name override; sync otherwise reads `organization.friendlyname` |
| `dataverseUrl` | `https://<org>.crm<N>.dynamics.com` — no trailing slash |
| `oauth.dataverseScope` | `<dataverseUrl>/.default` |
| `botId` | Copilot Studio agent id — only used by the Monitor probe scripts |

## Authentication

`dv_token.py` resolves tokens silently, in order:

1. **Azure CLI** — `az account get-access-token`. Silent after one `az login`.
2. **MSAL disk cache** — `.msal_token_cache.json`, chmod 600, gitignored.
3. **Device code** — prints a code rather than opening a browser.

If tokens expire: `az login --tenant <tenantId>`.

## Managed 2.0.0.5 stable installation and upgrade

The three published `2.0.0.5` managed ZIPs passed PVE validation for all solution versions, exact flow
and connection-reference ownership, seven unique active flows, five mapped references, and
tenant-neutral managed exports. The authenticated hosted PVE UI smoke passed across Sessions,
Trends, and Credits in the persisted cross-environment consent state. The user-performed manual
Contoso TPM import and upgrade test passed.

For any fresh environment that will receive the optional code app, set **Power Apps Code Apps >
Enable code apps** to **On**, save, and independently reload it before importing any package. See
the authoritative [clean-install validation runbook](clean-install.md) for the policy matrix,
target-generated app resolution, live validator, browser criteria, and cleanup workflow.

For a clean installation:

1. Import `pvConversationInsights-managed-2.0.0.5.zip`. Core does not prompt for a credit tenant ID.
2. Optionally import `pvConversationInsightsCredits-managed-2.0.0.5.zip` and supply the required
    `pvci_CreditReportingTenantId` current value in the import wizard.
3. Optionally import `pvConversationInsightsCodeApp-managed-2.0.0.5.zip` last.

For an upgrade from `1.4.0.15`, order is part of the migration contract:

1. Import `pvConversationInsightsCredits-managed-2.0.0.5.zip` first. This additively takes
    solution ownership of the three existing credit workflow identities and two licensing
    references, owns the required tenant variable definition, and preserves its target current value.
2. Apply `pvConversationInsights-managed-2.0.0.5.zip` as a managed upgrade second. Core retains all
    tables, data, plugins, Custom APIs, roles, the model-driven app, four transcript/shared flows,
    and three non-licensing references.
3. Upgrade `pvConversationInsightsCodeApp-managed-2.0.0.5.zip` last when the preview app is used.

Do not delete the old core credit components before installing the add-on, and do not use a clean
core-first order for this upgrade. In TPM, perform every import, connection mapping, publish, and
flow activation manually.

A transcript-only installation stops after core. It does not create or require
`pvci_licensinghttp`, `pvci_powerplatformapi`, or licensing-administrator access. When the optional
credit add-on is installed, create and map both licensing references, then run the credit usage
collector. Credits remains **Setup required** until a successful `pvci_creditsyncrun` exists and
becomes **Ready** only after that evidence is present; before Ready, the code app does not mount
credit data services.

## First-time deployment

```bash
CFG=config/transcript_solution_config.dev.json

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# 1. Schema — idempotent, safe to re-run after editing solution-definition.json
python3 scripts/transcript_insights/provision_dataverse_solution_webapi.py \
        --config $CFG --definition solution/pvConversationInsights/solution-definition.json

# 2. Views and app
python3 scripts/transcript_insights/create_app_views.py        --config $CFG
python3 scripts/transcript_insights/create_model_driven_app.py --config $CFG

# 3. PCF control, then forms (forms bind to the control, so order matters)
cd pcf/JsonViewer && npm install && npm run build && pac pcf push --publisher-prefix pvci && cd ../..
python3 scripts/transcript_insights/create_forms.py --config $CFG
python3 scripts/transcript_insights/create_credit_forms.py --config $CFG

# 4. Plugin + Custom API
cd plugin && dotnet build -c Release && cd ..
python3 scripts/transcript_insights/register_plugin.py --config $CFG
python3 scripts/transcript_insights/register_credit_plugin.py --config $CFG

# 5. Schedule
python3 scripts/transcript_insights/create_sync_flow.py --config $CFG --frequency Hour --interval 1 --activate

# 6. Initial load
python3 scripts/transcript_insights/sync_transcripts.py --config $CFG --full
```

`pac pcf push` prefixes the publisher, registering the control as
`pvci_PvciControls.JsonViewer`. `create_forms.py` resolves that name at runtime, so it works in
any environment.

## Copilot Credit collector

Read [Permissions and tenant inventory](permissions-and-inventory.md) before binding the collector
connections. Version `1.3.0.0` packages **PVCI Analyst**, **PVCI Privacy Approver**, and **PVCI Credit Administrator** roles plus
standalone inventory/governance collectors and the audited threshold processor; tenant roles and
physical connections remain target-local.

Create an **HTTP with Microsoft Entra ID (preauthorized)** connection before creating the flow. In
commercial cloud, set both connection fields to:

```text
Base Resource URL:             https://licensing.powerplatform.microsoft.com/
Microsoft Entra ID Resource URI: https://licensing.powerplatform.microsoft.com/
```

During managed-solution import, an entry showing `Invalid connection` and a blank
`BaseResourceUrl` is an incomplete physical connection, not a usable default. Choose **Add new
connection** from the import row, create the preauthorized HTTP connection with both values above,
return to the wizard, and map it to both **PVCI Licensing API** (`pvci_licensinghttp`) and **PVCI
Power Platform API** (`pvci_powerplatformapi`) when one licensing-administrator identity owns both
flows. Despite its display name, the latter is the licensing-governance reference and uses the same
`licensing.powerplatform.microsoft.com` audience. See the
[first-import connection wizard](permissions-and-inventory.md#first-import-connection-wizard) for
the complete five-row mapping and recovery steps.

The connection owner needs the Power Platform administrative access required by the licensing
service. DLP/ACP must allow this premium connector and Microsoft Dataverse in the collector
environment. Install the optional credit add-on first so `pvci_CreditReportingTenantId` exists. On the
first source deployment, bind the physical connection to the solution-aware flow:

```bash
python3 scripts/transcript_insights/create_credit_sync_flow.py \
    --config $CFG \
    --http-connection-id shared-webcontents-00000000
```

The script stores the tenant ID as an environment-variable current value outside the solution. On
later updates, omit `--http-connection-id` to reuse the target environment's existing
`pvci_licensinghttp` binding. The solution contains neither the current tenant value nor a physical
connection ID.

The script creates the flow stopped. Authenticate/save its solution connection references, run one
manual smoke test, and verify a successful `pvci_creditsyncrun` before activation. The flow runs
daily, re-reads seven days, requests pages of 100 up to a hard cap of 20, captures current capacity,
splits the unpaged user projection into bounded 250-row imports, and invokes
`pvci_ImportCreditUsageBatch`. Re-reading is intentional because PPAC can revise recent facts and
the importer is idempotent.

Health query:

```http
GET {dataverseUrl}/api/data/v9.1/pvci_creditsyncruns
        ?$select=pvci_name,pvci_source,pvci_status,pvci_completedon,pvci_pagecount,
                         pvci_sourcecount,pvci_createdcount,pvci_updatedcount,pvci_rejectedcount,pvci_error
        &$orderby=pvci_completedon desc&$top=10
```

`success` with a recent completion time and zero rejected rows is healthy. A source count of zero
can be valid when PPAC has no reportable usage, but should be compared with PPAC and previous runs.
Created, updated, and rejected counts combine all user chunks with the final resource/capacity
batch. A row rejection or transport-level user-chunk failure makes the persisted run `partial`;
failed chunks are recorded even when they return no row-level outcome. Do not activate a flow whose
physical licensing connection targets a different Base Resource URL.

Per-user usage is collected into `pvci_credituserusage`, separately from resource totals. The PPAC
user projection has no environment ID, so its totals remain tenant-wide when resource reporting is
environment-filtered. The default display is the source GUID. To approve name disclosure in the
code app, use **Reveal user names** and confirm the dialog. In the model-driven app, open **Privacy
Approval**, read the shared statement, set **Reveal User Names** to Yes, and save. Approval is global
and audited. Revocation and unresolved re-imports clear all resolved names, UPNs, and system-user
IDs. Restrict update access on
`pvci_creditprivacysetting` to authorized approvers and define retention/export policy before
enabling names outside the test tenant.

## Tenant environment and agent inventory

Create a **Power Platform for Admins V2** connection owned by a Power Platform Administrator. DLP
and ACP must allow the connector. Bind and create the standalone flow in Stopped state:

```bash
python3 scripts/transcript_insights/create_inventory_sync_flow.py \
    --config $CFG \
    --admin-connection-id shared-powerplatform-00000000
```

The daily flow pages Power Platform Admin V2 environments and `microsoft.copilotstudio/agents`
from `PowerPlatformResources`, imports each page immediately through the bounded Custom API, and
writes a separate `pvci_inventorysyncrun`. Run it manually before adding `--activate`.

Inventory is independent of credit activity. Zero-usage agents remain in `pvci_agentinventory`,
and `pvci_environmentinventory` drives environment navigation even when capacity and usage are
empty. Exact tenant/environment/resource identity enriches existing billing rows; unknown or
billing-only resources remain visible.

If activation reports `ApiPolicyApiGroupViolation`, add
`/providers/Microsoft.PowerApps/apis/shared_powerplatformadminv2` to the effective ACP allowlist.
For an environment-group policy, save and publish the group rules. A runtime HTTP `442` whose
`Last refresh` predates the policy update is propagation lag; leave the flow stopped and retry only
after the runtime cache refreshes.

## Credit governance collection and changes

Create a dedicated **HTTP with Microsoft Entra ID (preauthorized)** connection for the governance
read. Set both connection fields to `https://licensing.powerplatform.microsoft.com/`. Bind and
create the flow stopped:

```bash
python3 scripts/transcript_insights/create_credit_governance_flow.py \
    --config $CFG \
    --http-connection-id shared-webcontents-00000000
```

Run it manually, then verify the newest `pvci_governancesyncrun` reports the expected threshold
count and zero rejects before adding `--activate`. The workflow definition contains one Power
Platform API `GET` and one Dataverse Custom API import. It contains no licensing PUT/PATCH action.

Threshold rows are matched to Agent Inventory by normalized tenant/environment/resource identity.
Unlinked controls are retained and shown in both apps. A limit of zero or an absent match must not
be interpreted as permission to delete or change the platform control.

Create the processor stopped with the same bound connections:

```bash
python3 scripts/transcript_insights/create_credit_governance_processor_flow.py \
    --config $CFG
```

Run it with an empty queue, then submit a no-op request whose desired state equals the current
threshold. Verify `Succeeded`, a processed timestamp, and identical audited before/after control
fields before activation. It handles at most 20 pending requests per serial run and rejects stale
or invalid requests without changing the platform.

Activate only after the no-op test succeeds:

```bash
python3 scripts/transcript_insights/create_credit_governance_processor_flow.py \
    --config $CFG --activate
```

In the code app, the affected agent row shows Requested, Processing, Applied, Review needed,
Failed, or Verify applied. Requested and Processing rows refresh every five seconds and disable a
duplicate Change action. `AppliedUnverified` / **Verify applied** means the processor attempted the
PUT but could not complete read-back or audit persistence; inspect the current Power Platform
threshold before retrying. This workflow does not implement a separate approval stage: the Credit
Administrator role is the submission authorization boundary.

## Routine operation

Once the transcript sync flow is active, it calls the Custom API hourly and loops until a batch
returns fewer records than `MaxRecords`, so a transcript backlog clears in one run. Each correlated
flow run also creates a pending `pvci_flowrundetail` row.

Full run bodies are a separate operation because the Power Automate API needs a different token
audience than Dataverse, so a sandbox plugin cannot fetch them:

```bash
python3 scripts/transcript_insights/fetch_flow_run_details.py --config $CFG
```

The fetcher enriches pending placeholders and skips only rows with `pvci_fetchedon`. Schedule it
separately (cron, CI, or an Azure Function). Flow runs age out of Power Automate independently of
Dataverse, so late fetches return nothing.

The Flow Runs tab presents enriched records as a process map. It hides skipped branches initially,
centers the first likely root failure, and keeps raw inputs/outputs behind the selected action's
inspector. Use **Show skipped branches** when you need to compare the path taken with an alternate
branch. Selecting **Analyze** opens the map in a dedicated full-width workspace below the run list.
Successful runs keep the inspector closed so the map receives the whole pane; selecting a node opens
the inspector, and its close button restores the full canvas. Failed runs open directly on the root
failure and its explanation.

Timing labels in the correlation card are deliberately separate: **step window** is the Copilot
plan-step envelope, **run time** is the Power Automate execution duration, and **start delta** is
only the difference between their start timestamps used for matching. Do not add these values or
treat start delta as measured backend waiting time.

To reproduce one run:

```bash
python3 scripts/transcript_insights/fetch_flow_run_details.py --config $CFG \
    --run-name <flow-run-name> --refresh
```

PVE Dev's group-inherited ACP now allows `HTTP with Microsoft Entra ID (preauthorized)` and the
environment's synced policy copy contains the rule. Runtime enforcement is still using an older
policy cache and returns HTTP `442`; processor packaging continues after that cache refreshes. See
[Full Power Automate run detail](flow-run-detail-findings.md) for the evidence and deployment
choices.

## VS Code Power Platform admin skill

The installed Power Platform plugins provide product-specific flow and Dataverse administration,
but no general governance skill. A personal cross-workspace skill is installed at:

```text
~/.copilot/skills/power-platform-admin/SKILL.md
```

It is user-invocable as `/power-platform-admin` and can also be discovered automatically for PPAC,
environment groups, managed environments, ACP, DLP, connector policies, HTTP `442`, and policy
propagation requests. Its governance reference documents the PAC and Power Platform REST workflow,
including the requirement to evaluate classic DLP and ACP together and to publish group rules.

The skill is personal rather than a solution component; it is available to future VS Code agent
sessions on this machine but is not exported in the Power Platform solution ZIP.

## Manual sync

```bash
python3 scripts/transcript_insights/sync_transcripts.py --config $CFG            # incremental
python3 scripts/transcript_insights/sync_transcripts.py --config $CFG --full     # rescan, still additive
python3 scripts/transcript_insights/sync_transcripts.py --config $CFG --full --reprocess   # re-derive
```

Tenant-wide multi-environment run:

```bash
.venv/bin/python scripts/transcript_insights/sync_multi_environment.py \
    --configs config/transcript_solution_config.dev.json config/transcript_solution_config.sandbox.json
```

Each synced session stores `pvci_environmentid` and `pvci_environmentname`, and also carries a
lineage stamp in `pvci_datasource`:
`dataverse_v9.1|tenant:<id>|env:<id>|envName:<name>|org:<host>`.

### Backfill environment names after upgrading

After importing a version that adds the environment columns, run one full scan. Existing sessions
are patched with Power Platform environment ID, friendly name, and lineage only; turns and transcript payloads are
not rewritten, so `Reprocess` must remain false.

```bash
python3 scripts/transcript_insights/sync_transcripts.py --config $CFG --full
```

For the in-platform path, invoke `pvci_SyncConversationTranscripts` with `FullSync: true`,
`Reprocess: false`, and a batch size large enough for the current session count. The scheduled
incremental flow then labels new sessions automatically.

Use `--reprocess` after changing parser logic. It rewrites sessions and replaces their turns,
which issues new turn GUIDs.

## Central transcript source discovery

Phase 1 can classify all tenant environments without installing PVCI into each source environment.
The probe consumes the read-only environment inventory returned by the Power Platform admin
connection, requests a Dataverse-scoped token for each organization, and performs a one-row
`conversationtranscripts` read. It writes only source metadata and access status; it never stores
transcript content or identifiers.

```powershell
pac admin list --json > output/test-tenant-admin-environments.json
python scripts/transcript_insights/probe_transcript_sources.py `
    --config config/transcript_solution_config.dev.json `
    --inventory output/test-tenant-admin-environments.json `
    --output output/transcript-source-registry.json
```

The registry reports `readable_with_rows`, `readable_empty`, `access_denied`, `unavailable`, and
authentication or transport errors separately. Only readable sources are candidates for the
central collector. A `readable_empty` result means the identity can query the table but
the one-row sample returned no records; it does not prove transcript capture is enabled.

The source-local `pvci_SyncConversationTranscripts` plugin remains unchanged. The first central
worker implementation is available as a bounded local/CI proof of concept:

```powershell
python scripts/transcript_insights/collect_central_transcripts.py `
    --config config/transcript_solution_config.dev.json `
    --registry output/transcript-source-registry.json `
    --limit 1 --dry-run
```

It reads each enabled source with that organization's Dataverse audience, parses the transcript,
and writes only to the configured collector Dataverse when `--dry-run` is omitted. It uses one
watermark name per source (`central:<environmentId>`) and a composite transcript key containing
tenant, environment, and source transcript ID.

The packaged Power Automate flow is created in the core solution by the source generator. The
generator is for core development and package maintenance, not post-import tenant setup:

```powershell
python scripts/transcript_insights/create_central_transcript_flow.py `
    --output output/central-transcript-flow.json `
    --deploy
```

`pvci_ImportCentralTranscriptBatch` is registered in the collector solution and enforces a
25-row maximum. A PVE Preview to PVE Dev smoke import created one session and two turns; replaying
the same source row skipped it through the composite key. During import, map the packaged
`pvci_centralcollector` connection reference to one Microsoft Dataverse connection whose identity
has read access in supported sources. The packaged flow dynamically supplies each inventory row's
`pvci_environmenturl` to `ListRecordsWithOrganization`; no per-source connection is required.
Keep `pvci_transcriptcollectorenabled` false until a source is reviewed. Run **Tenant Agent
Inventory** first. In the code app's **Inventory Management** page, open the source, select
**Source-managed**, assign the least-privilege source role to the `pvci_centralcollector` identity,
and choose **Verify access**. Use the readiness summary buttons or the synchronized filter menu to
limit the environment list to ready, enabled, readable, denied, or not-ready sources. `PVCI Verify Transcript Source Access (scheduled)` processes only
pending `Verify` requests and writes the ID-only probe result to the request and Environment
Inventory. It does not claim that a successful data read proves the exact assigned role. Only a
source with onboarding `Verified` and readable access can be enabled. Enabling requires an explicit
administrator confirmation that transcript data will move from that remote source and be retained
in the Dataverse environment where PVCI is installed. Discovery, a readable probe, and `Verified`
status never imply this consent. Disabling a source stops future imports but does not remove sessions
or turns already copied; use the organization's approved Dataverse retention process when deletion
is required. Until at least one remote source is enabled, the code app scopes Sessions, Trends, and
Credits resource reporting to the host environment and hides their controls for selecting other
environments. Credit user usage and recent governance request history remain tenant-wide. The central collector still
probes before each content read; a later failed or timed-out probe records `access_denied`, disables
that source, and continues with other sources. After repairing source access, submit a new
verification request before enabling collection again.

Create or update the verification processor during core development, initially stopped:

```powershell
python scripts/transcript_insights/create_transcript_access_verification_flow.py `
    --output output/transcript-access-verification-flow.json `
    --deploy
```

Map `pvci_centralcollector`, assign **PVCI Source Access Processor** to the flow owner, activate the
flow, and use the smoke utility to queue and inspect one audited request:

```powershell
python scripts/transcript_insights/smoke_test_transcript_access_verification.py
python scripts/transcript_insights/smoke_test_transcript_access_verification.py `
    --request-key <request-key>
```

Expected success is request and inventory status `Verified`, access `readable_with_rows` or
`readable_empty`, collector still disabled, and role/cleanup flags false unless an external
reconciler supplied independent evidence. Administrator bootstrap remains unavailable until that
reconciler can provision access and prove removal of temporary elevation.

If **Read source transcripts** fails with `ThrowCrmSecurityException` and
`prvReadconversationtranscript`, the user behind `pvci_centralcollector` has no applicable security
role in that source environment. In TPM, correct this manually: identify the connection owner, add
that user to the source environment, and assign a least-privilege role with organization-level Read
on **Conversation Transcript** (or System Administrator for a temporary test). Reauthenticate the
connection if its token predates the assignment, then re-enable the source. Import or
collector-side failures after a successful probe remain visible as failed runs; they are not
classified as source permission denials.

Or invoke the Custom API directly:

```http
POST {dataverseUrl}/api/data/v9.1/pvci_SyncConversationTranscripts
{ "FullSync": false, "MaxRecords": 50, "Reprocess": false, "IncludeTraces": false }
```

After installing the structured runtime-diagnostics update, reprocess existing sessions to derive
topic and error summaries and to retain user-facing `ErrorTraceData` turns. Incremental sync applies
the contract automatically only to newly encountered transcripts. Use a bounded maintenance run
with `Reprocess: true`; verify `pvci_usererrorcount`, `pvci_primaryerrorcode`, and the model-driven
session form before expanding the batch. Generic trace retention can remain disabled.

Candidate `1.4.0.3` was backend-smoke-tested in PVE Dev against transcript
`cc605963-e8f2-47cf-bcb6-0eb3b65846b0`. Exact-row reprocessing produced one
`ContentValidationError`, category `Topic expression`, the full
`ESS_UserContext_TimeZoneOffset`/`DateAdd` message, and a retained `ErrorTraceData` turn. The source
contained no `DynamicPlanStepTriggered`, so the error topic correctly remained unknown. During
this smoke, the Custom API did not honor `SinceOverride`; exact-row maintenance used the local
sync parser directly without changing `pvci_syncstate`. Treat `SinceOverride` as unverified until
its Custom API binding is corrected, and do not use it as the only safety boundary for a bulk
reprocess.

On 2026-08-26, the preview code app was deployed to PVE Dev and passed a signed-in
`apps.powerapps.com` smoke in the shared VS Code browser. At desktop analyst width, Sessions put its
assessment before timelines, Trends retained its completeness and latency summary, Inventory put
selected-source remediation before the environment table, and Credits put attribution warnings
before charts while identifying duplicate resource names by environment. The same deployment had no
viewport overlap at narrow width. Live sessions preserved observed zero versus unavailable errors,
knowledge, and exact tool telemetry. This proves the hosted shell and decision hierarchy; the full
representative knowledge, expression-failure, connector-failure, no-flow, and multiple-candidate
scenario matrix remains a separate exit gate.

Knowledge retrieval diagnostics require reprocessing because older sessions have no
`pvci_knowledge*` summaries. A successful knowledge smoke should show a nonzero Knowledge call
count, completion state, duration, and cited source identifier even when Tool calls is zero. This
is expected: Universal Search emits `KnowledgeTraceData`, not a `DialogTracing` `Invoke*` action.
The compact summary must not contain search query arguments or retrieved document passages.
Candidate `1.4.0.4` was backend-smoke-tested against central session
`1938ee32-a258-454c-b8db-3a928341bd69:67203dc9-8a11-e6ef-9970-81e05021161c:5cb848eb-378c-4b2b-81ea-96a4e9b80649`.
It reported one 13.3-second Universal Search retrieval, completion state `Answered`, one cited
ServiceNow KB source, and zero failures. `Answered` is a successful completion state. The summary
JSON contained neither `search_query` nor `search_keywords`.

## Reading conversation telemetry

Use these interpretation rules when investigating a session:

- `0` means the relevant telemetry was available and no event was observed. **Unavailable** means
    the transcript cannot prove zero; exact `DialogTracing` tool telemetry is normally test-only.
    The code-app Overview and ESS KPI cards preserve this distinction for turns, errors, knowledge,
    exact tool traces, and candidate flow matches instead of defaulting absent counters to zero.
- Reply wait, plan-step elapsed, knowledge-step elapsed, exact invoke span, and Power Automate run
    duration are separate clocks. Do not add them together.
- Flow matches are time-based **candidates**, not proven attribution. **Closest start** identifies
    ranking by start-time proximity only.
- Knowledge/search plan steps are not Power Automate flow candidates and appear only under
    Knowledge and routing evidence.
- MCP and other `LlmSkill` plan steps are tool/reasoning evidence, not Power Automate flow
    candidates. Tool Calls shows them as planned steps with **execution not evidenced** when no exact
    `DialogTracing` invocation was retained; they do not increase exact invocation metrics. A
    production `CustomTopic` plan step appears under Flow Runs only when at least one backend run
    overlaps its bounded step window; unmatched plan steps remain in Agent Reasoning.
- Largest retained-event gap describes stored transcript events, not guaranteed user-visible
    silence.
- Unknown flow-action status remains unknown. **First likely failure** is a triage starting point,
    not a proven root cause. Chronological map connections are labeled when dependency metadata is
    unavailable.
- Source outcome, implied resolution, user-visible runtime errors, exact tool failures, knowledge
    failures, and candidate flow failures are independent signals and can disagree.

### Session analyzer architecture audit

The PVE Dev audit on 2026-08-27 compared 55 stored sessions with published Copilot Studio bot
components and Dataverse workflow metadata. The analyzer uses these evidence boundaries:

- `CustomTopic` is a selected Copilot Studio topic. It can be the primary topic, but its name alone
    does not prove that a connector or cloud flow executed.
- `KnowledgeSource` is knowledge retrieval. A `KnowledgeTraceData` outcome is associated with the
    nearest prior knowledge step because the trace has no explicit step correlation ID.
- `LlmSkill` / `MCP:` is an MCP or tool plan step. It appears in Agent Reasoning and as qualified
    planned evidence in Tool Calls, but does not become an exact invocation or Power Automate flow
    candidate without the corresponding evidence.
- `DialogTracing` `Invoke*` entries are exact retained tool evidence in test transcripts. A missing
    completion entry means **completion not observed**, not a confirmed failure.
- Flow Runs contains exact `InvokeFlowAction` windows or `CustomTopic` windows with an overlapping
    backend run. Every match remains time correlation, including a single candidate. Resolved Workflow
    table names identify the candidate flow; they do not prove causality.
- Source-local sessions can query `flowrun`. Central sessions cannot query the source environment's
    flow runs through the collector plugin, so flow counters and JSON are **Unavailable**, not zero.
- User error location is the nearest prior retained plan step unless the source adds an explicit
    correlation key. Treat it as sequence context, not exact topic attribution.

Validated live paths include Jira MCP `ListIssues`, ESS IT Universal Search knowledge retrieval,
ESS IT topic-expression and connector failures, and the ServiceNow ITSM Create Ticket path. The
ServiceNow session retained the selected `ServiceNowITSMCreateTicket` topic, three exact tool calls,
and two time-correlated successful flows: **ESS IT ServiceNow ITSM Common Orchestrator** and
**ESS IT ServiceNow ITSM Request Body Generator**.

PVE Dev also contains published Contoso ESS HR Workday topics and Workday cloud flows, including
National IDs, certifications, visas, company code, employment information, and common execution.
The available HR sessions are greeting-only and contain no plan, tool, or flow events. Workday
session analysis therefore remains unvalidated until a representative completed and failed Workday
conversation is retained and reviewed. Do not infer Workday behavior from ServiceNow evidence.

The Overview is the first-stop session view. Use Replay to inspect user/agent turns, then open
Knowledge, Tool Calls, or Flow Runs only when the overview indicates participation or when capture
availability permits it. Raw JSON is supporting evidence, not the primary operating surface.

Agent Reasoning presents the recorded orchestration lifecycle as plan sequences. Read each plan as
request → selected step → prepared input names → observable result. **Step finish not retained** is
an evidence limitation, not automatically a failure. **Recorded routing rationale** is product
telemetry supplied in the transcript and must not be described as hidden model chain-of-thought.
Use **Show raw evidence** only when the summarized lifecycle is insufficient.

Trends is a separate full-width aggregate workspace and does not show the per-session navigator.
Its filter order is **Environment → Agent → Scope → Time grain**. The agent list is constrained by
the selected environment, ESS preset, and test-mode scope; changing an upstream filter resets an
incompatible agent selection. Use Sessions when investigating one conversation. Use Trends only
for the bounded recent sample disclosed at the top of that page.

Environment names shown in Sessions and Trends come from Environment Inventory by exact Power
Platform environment ID. The transcript session keeps the ID as the authoritative key; technical
Dataverse organization names such as `unq...` or `org...` are lineage values, not user-facing
labels. Local sync prefers `pvci_environmentinventory.pvci_displayname`, and the code app enriches
legacy session rows from the same inventory before rendering. Candidate `1.4.0.9` backfilled all
35 PVE Dev session rows with zero unmatched environment IDs.

## Health checks

The single source of truth is `pvci_syncstate`:

```http
GET {dataverseUrl}/api/data/v9.1/pvci_syncstates
    ?$select=pvci_lastrunon,pvci_lastrunstatus,pvci_recordsprocessed,pvci_lasterror
```

| `pvci_lastrunstatus` | Meaning |
| --- | --- |
| `success` | All transcripts in the batch processed |
| `partial` | Some failed; watermark frozen so they retry next run |
| `failed` | Nothing processed — check `pvci_lasterror` |

A frozen watermark is by design: it stops a failing transcript being skipped forever.

## Promoting the public 1.x package to another environment

```bash
pac solution export --name pvConversationInsights --path ./pvConversationInsights.zip --managed
pac auth create --environment <target-org-url>
pac solution import --path ./pvConversationInsights.zip --activate-plugins
```

Afterwards, in the target environment:

1. Supply a current value for the required `pvci_CreditReportingTenantId` environment variable.
    Do not add a default value to the solution.
2. Rebind `pvci_dataversesync` to a Dataverse connection that exists in the target environment.
3. Rebind `pvci_licensinghttp` to a target-local licensing-service connection with the correct
    cloud URL. Credentials and physical connection IDs are deployment bindings, not solution data.
4. Bind `pvci_powerplatformadminv2` to a Power Platform Administrator connection and ensure DLP/ACP
    allow Power Platform for Admins V2.
5. Bind `pvci_powerplatformapi` to a target-local HTTP with Microsoft Entra ID connection whose
    Base Resource URL and resource audience are `https://licensing.powerplatform.microsoft.com/`.
6. Assign **PVCI Analyst** to readers, **PVCI Privacy Approver** only to approved disclosure
    operators, and **PVCI Credit Administrator** only to transcript-collection and threshold-change
    operators. Share the code app separately with the same users/groups.
7. Save and smoke-test all 7 flows, including a no-op governance request, then activate the
    intended schedules and processor.
8. Run the initial `--full` transcript load.
9. Redeploy the code app (`npx power-apps init` + `push`) — it lives outside the core solution.
10. Configure either a DLP-approved Flow API connection or the headless run-detail worker.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `conversationtranscripts` returns empty | Missing Read privilege on the table returns an empty set, not `403`. Also check transcripts are enabled on the agent, and allow for post-session lag |
| Tool Calls empty on a production session | Expected — `DialogTracing` is design-mode only |
| Flow Runs shows `no run matched` | The run aged out of Power Automate retention, or fell outside the ±20s window |
| Flow Runs shows `multiple` | Normal for orchestrator + child flow patterns, and under concurrent load |
| A tab is blank but the header shows a count | The field is missing from the app's detail projection |
| `401` from a script | `az login --tenant <tenantId>` |
| Plugin returns `Status: failed` | Read `Errors` in the response and `pvci_lasterror` |
| Flow does not start | Check the connection reference is bound and the flow is activated |
| Governance flow fails at `Get_resource_thresholds` with `404` | Inspect the action's request URL and response body. The URL must resolve to `/v1.0/tenants/{tenantId}/entitlements/MCSMessages/resourceThresholds`, and the target-local `pvci_powerplatformapi` connection must be **HTTP with Microsoft Entra ID (preauthorized)** with both Base Resource URL and Microsoft Entra ID Resource URI set to `https://licensing.powerplatform.microsoft.com/`. A 404 with the old `/licensing/entitlements/...` URL means the flow definition is stale; update/recreate the stopped flow from the corrected generator. |
| Governance flow returns `200` with body `[]` | The route and connection succeeded, but the licensing service exposed no resource-threshold rows for the configured tenant. Confirm `pvci_CreditReportingTenantId` matches the tenant shown in the request URL and check the inventory flow for agents. There is no supported PPAC screen that independently exposes these threshold rows, so do not require a UI confirmation. Do not treat an empty threshold projection as a flow or importer error, and do not infer that no agents exist. |
| Credit collector fails at `Get_usage_page` | Verify `pvci_licensinghttp` is connected and both licensing connection URLs match the tenant cloud |
| Capacity or users load but agents/resources are empty | Inspect `Get_usage_page`: `401/403` is connection-owner access; `200` with an empty `resources` array means no resource facts were returned for the seven-day window. Capacity is not tenant inventory |
| Only some tenant environments are listed in Credits | Check the latest `pvci_inventorysyncrun`, the `pvci_powerplatformadminv2` connection owner, and Admin V2 DLP/ACP access |
| Inventory flow returns HTTP `442` | Compare the error's `Last refresh` with the ACP modification time; an older timestamp means runtime policy propagation is pending |
| Credit sync is stale | Check the latest `pvci_creditsyncrun`, physical connection health, flow state, and recurrence history |
| Agent day/week chart has sparse dates | PPAC returned aggregate or weekly source periods; do not manufacture daily rows |
| Change is disabled for an agent | A Pending or Processing request already exists; wait for a terminal lifecycle state |
| Request shows Review needed | Current threshold state differs from the submitted expected state; review the latest snapshot and submit a fresh request |
| Request shows Verify applied | The PUT was attempted but read-back/audit failed; verify the live threshold before any retry |

## Data protection

`pvci_*` tables contain personal data. Restrict privileges, set a retention policy, and enable
auditing where required — see [SECURITY.md](../SECURITY.md).
