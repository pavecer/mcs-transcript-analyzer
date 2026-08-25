# MCS Transcript Analyzer

Ingest, correlate and analyse **Microsoft Copilot Studio** conversation transcripts and Copilot
Credit consumption in Dataverse — with end-user attribution, response latency, agent reasoning,
tool calls, correlated Power Automate flow runs, capacity, and billed/non-billed usage.

Built because the Copilot Studio Monitor CSV export drops the two things you need most when
a customer says *"the agent answered wrong"*: **who** was talking, and **why** the agent did
what it did.

**[View the solution presentation and download the managed installer](https://pavecer.github.io/mcs-transcript-analyzer/)**

Track shipped versions in [CHANGELOG.md](CHANGELOG.md) and planned work in [ROADMAP.md](ROADMAP.md).
For a first managed import, follow the
[connection-wizard checklist](docs/permissions-and-inventory.md#first-import-connection-wizard).
Do not bind a licensing entry that shows `Invalid connection` or a blank `BaseResourceUrl`; create
the preauthorized HTTP connection with both licensing-service URLs first.

---

## What you get

| Surface | What it is |
| --- | --- |
| **Dataverse solution** | 17 custom tables, views, forms, 4 application roles, a model-driven app, 3 Custom APIs, and 7 packaged scheduled flows |
| **Model-driven app** | GA, standard-licensed. Transcript operations, environment collection coverage, Credits and Capacity grids, and evidence forms |
| **Code app** (preview) | React/Vite workspaces for transcript triage, trends, Copilot Credit reporting, and dedicated tenant inventory/transcript-source management |
| **Custom APIs + plugin** | Local incremental transcript sync, bounded cross-environment transcript import, and validated idempotent credit import |
| **Python toolkit** | Bulk backfill, plugin registration, flow-run detail fetch |

### 2.0.0.5 stable package architecture

The current stable release contains three synchronized managed packages after hosted PVE UI
validation, tenant-neutral package validation, and the user-performed manual Contoso TPM upgrade.

| Package | Required? | Ownership |
| --- | --- | --- |
| `pvConversationInsights` | Required | All 17 tables, plugins and Custom APIs, four roles, model-driven app, inventory/transcript runtime, four transcript/shared flows, and `pvci_dataversesync`, `pvci_powerplatformadminv2`, and `pvci_centralcollector` |
| `pvConversationInsightsCredits` | Optional | Only the three credit collection/governance flows, licensing references `pvci_licensinghttp` and `pvci_powerplatformapi`, and required `pvci_CreditReportingTenantId` definition |
| `pvConversationInsightsCodeApp` | Optional preview | Only the unsupported preview code app and its declared core dependencies |

For a clean `2.0.0.5` installation, import core, then optional credits, then optional code app. To
upgrade from `1.4.0.15`, import the credits add-on first, apply the core managed upgrade second,
and upgrade the code app last. This additive ownership transfer preserves the existing credit flow
identities while core retains schema and data ownership. Core does not contain or request the credit
tenant variable. The optional credit add-on prompts for its required target-tenant current value and
never packages the value from PVE.

Credits navigation remains visible. It reports **Unavailable** when the add-on is absent,
**Setup required** when the add-on is installed without successful credit-sync evidence, and
**Ready** only after both are present. Credit data services are not mounted before Ready. A
transcript-only deployment does not require either licensing HTTP connection or
licensing-administrator access.

`PVCI Collect Central Transcripts (scheduled)` is packaged in the core solution. It uses one
solution-aware Microsoft Dataverse connection reference and the supported selected-environment
action to read source URLs dynamically from Environment Inventory. After import, map that one
connection and run tenant inventory. In the code app, choose **Source-managed**, grant the collector
identity a least-privilege role with organization-level Read on **Conversation Transcript** in each
selected source environment, and submit **Verify access**. The packaged request processor records
the one-row ID-only probe result; discovery and verification do not enable collection. Transcript
sync is local to the installed environment by default. Enabling a readable `Verified` remote source
requires an explicit administrator confirmation that transcript data will be copied into and stored
in the installed Dataverse environment. Disabling it stops future imports but does not delete records
already copied. Sessions, Trends, and Credits resource reporting remain scoped to the host environment,
with their environment selectors hidden, until at least one remote source is enabled. User usage and
recent governance request history remain tenant-wide. Failed probes remain
visible and keep collection off. Administrator bootstrap is shown as
unavailable until its external reconciler is deployed. No tenant name, source ID, URL, or physical
connection is hardcoded.

### Captured per session

The session workspace opens on a plain-language **Overview**. Replay, exact tool traces, knowledge
retrieval, candidate Power Automate runs, reasoning, and raw JSON remain available as progressively
deeper evidence.

- **End user** — resolved from `from.aadObjectId` to a real `systemuser`
- **Latency** — first / average / slowest reply, in milliseconds, and per turn
- **Agent reasoning** — the `DynamicPlan*` trace showing which topic or tool was chosen, and why
- **Tool calls** — connector and AI Builder invocations with duration, output and exceptions
- **Flow runs** — correlated Power Automate runs, enrichable with action and loop-iteration inputs and outputs
- **Outcome** — resolved / abandoned, reason, implied success, turn count
- **Runtime failures** — user-facing error count, category, code, message, active topic, and failure timeline
- **Knowledge retrieval** — search completion, latency, cited source identifiers, and failed source types
- **Test-mode flag** — so maker-portal testing does not pollute production metrics

### Captured for Copilot Credits

- **Actual billed and non-billed credits** — resource/agent source-period facts from PPAC
- **Capacity** — environment allocation, consumption, available quantity, PAYG, and policy state
- **Tenant inventory** — environments and Copilot agents from Power Platform Admin V2 and PPAC One Inventory, including agents with zero credit usage
- **Credit governance** — direct GitHub harness evidence, spend-risk bands, threshold utilization, and audited limit-change requests
- **Granularity** — environment, agent/resource, source day or week, feature when supplied
- **Lineage and quality** — source API/schema, freshness, unresolved resources, and unknown harnesses
- **User support** — separate user-period facts display source GUIDs by default; an audited shared
   approval can resolve names in both apps and revocation removes them again

### Copilot Credit capabilities

| Capability | What the solution provides | Important boundary |
| --- | --- | --- |
| Usage and capacity | Actual billed/non-billed resource facts, tenant-wide user facts, environment capacity, source-period trends, and collector health | Resource and user projections are separate totals; neither is allocated to a conversation |
| Tenant inventory | Environment and agent inventory independent of usage, including zero-usage agents and exact GitHub harness evidence | Missing `isCLIAgent` evidence remains Unknown; false means only Not GitHub Copilot harness |
| Governance | Current monthly limit, consumption, notification, stop-at-limit, explicit-stop state, and Critical/High/Watch/Healthy/No limit risk grouping | Threshold snapshots are source facts; environment allocation and tenant-pool settings stay read-only |
| Audited changes | Credit Administrators submit desired and expected state with justification; the processor validates, writes one agent threshold, reads back, and records before/after evidence | The browser never receives licensing API authority; active requests prevent duplicate submissions |

Request status is visible on each agent as **Requested**, **Processing**, **Applied**, **Review
needed**, **Failed**, or **Verify applied**. Per-user Copilot Studio limits are not available from a
documented API, and the solution does not invent them. See
[Copilot Credit reporting](docs/credit-reporting.md) for source grain, security, risk rules, and
operational boundaries.

---

## Why not the Monitor export?

Copilot Studio surfaces transcripts in two places, and they are **not** the same data.

| | Monitor / Analytics export | `conversationtranscripts` (used here) |
| --- | --- | --- |
| Format | CSV, one row per session | JSON, full Bot Framework activity stream |
| End-user identity | ✗ | ✅ `from.aadObjectId` |
| Reasoning / orchestration events | ✗ | ✅ full `DynamicPlan*` trace |
| Callable with a normal token | ✗ `403 UnauthenticatedUser` | ✅ standard Dataverse auth |
| Usable from a plugin or flow | ✗ | ✅ |

See [docs/monitor-endpoint-findings.md](docs/monitor-endpoint-findings.md) for the evidence.

---

## Quick start

For a normal installation, download the managed solution from the
[project website](https://pavecer.github.io/mcs-transcript-analyzer/#install) and import it in
Power Apps under **Solutions > Import solution**. The source deployment below is intended for
contributors and environments where you want to rebuild every component.

Before enabling collection, review [permissions and tenant inventory](docs/permissions-and-inventory.md).
Version `1.3.0.0` includes **PVCI Analyst**, **PVCI Privacy Approver**, and **PVCI Credit Administrator**.
The current source also defines **PVCI Source Access Processor** for audited verification outcomes.
The solutions provide separate inventory/governance collectors, exact GitHub harness filtering,
spend-risk grouping, threshold snapshots, code-app collector enablement for administrators, and an
audited privileged processor. Tenant roles and target-local connections remain installation steps
that a managed solution cannot grant.

**Prerequisites:** Python 3.10+, Node 22+, .NET SDK 8+, [Power Platform CLI](https://aka.ms/PowerPlatformCLI),
Azure CLI, and a Dataverse environment where you hold System Customizer.

```bash
git clone https://github.com/pavecer/mcs-transcript-analyzer.git
cd mcs-transcript-analyzer

# macOS / Linux
python3 -m venv .venv && source .venv/bin/activate

# Windows PowerShell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r scripts/transcript_insights/requirements.txt

az login --tenant <your-tenant-id>          # silent tokens from here on
pac auth create --environment <org-url>

cp config/transcript_solution_config.sample.json config/transcript_solution_config.dev.json
# fill in tenantId, environmentId, dataverseUrl, oauth.dataverseScope, botId
```

Then, in order:

```bash
CFG=config/transcript_solution_config.dev.json

python3 scripts/transcript_insights/provision_dataverse_solution_webapi.py --config $CFG \
        --definition solution/pvConversationInsights/solution-definition.json
python3 scripts/transcript_insights/create_app_views.py       --config $CFG
python3 scripts/transcript_insights/create_model_driven_app.py --config $CFG

cd pcf/JsonViewer && npm install && npm run build && pac pcf push --publisher-prefix pvci && cd ../..
python3 scripts/transcript_insights/create_forms.py --config $CFG   # binds the PCF control
python3 scripts/transcript_insights/create_credit_forms.py --config $CFG

cd plugin && dotnet build -c Release && cd ..
python3 scripts/transcript_insights/register_plugin.py  --config $CFG
python3 scripts/transcript_insights/register_credit_plugin.py --config $CFG
python3 scripts/transcript_insights/create_security_roles.py --config $CFG
python3 scripts/transcript_insights/create_sync_flow.py --config $CFG --activate

# Create a licensing connection first; see docs/credit-reporting.md and docs/operations.md.
python3 scripts/transcript_insights/create_credit_sync_flow.py --config $CFG \
   --http-connection-id shared-webcontents-00000000

# Create a Power Platform for Admins V2 connection first; smoke-test before --activate.
python3 scripts/transcript_insights/create_inventory_sync_flow.py --config $CFG \
   --admin-connection-id shared-powerplatform-00000000

# Create a dedicated licensing.powerplatform.microsoft.com connection before the first command.
python3 scripts/transcript_insights/create_credit_governance_flow.py --config $CFG \
   --http-connection-id shared-webcontents-00000000
python3 scripts/transcript_insights/create_credit_governance_processor_flow.py --config $CFG

python3 scripts/transcript_insights/sync_transcripts.py --config $CFG --full   # initial load
```

Optional code app:

```bash
cd codeapp && npm install
npx power-apps init -n 'Conversation Insights Explorer' -e <environment-id>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_transcriptsession --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_transcriptturn   --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_flowrundetail    --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_agentinventory  --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_creditusage      --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_creditcapacitysnapshot --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_creditsyncrun    --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_credituserusage  --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_creditprivacysetting --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_environmentinventory --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_transcriptaccessrequest --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_inventorysyncrun --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_agentthresholdsnapshot --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_governancesyncrun --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_thresholdchangerequest --org-url <org-url>
npm run build && npx power-apps push
```

Full walkthrough: [docs/operations.md](docs/operations.md).

---

## How the sync works

```text
Dataverse conversationtranscript
        │
        │  pvci_SyncConversationTranscripts   (Custom API + sandboxed plugin)
        │  ← called hourly by a Power Automate recurrence flow, in a drain loop
        ▼
pvci_transcriptsession ──< pvci_transcriptturn
        │                        │
        ├── pvci_transcriptidentitymap   (aadObjectId → systemuser)
        ├── pvci_syncstate               (watermark + last run status)
            └── pvci_flowrundetail           (durable queue + enriched run payloads)
```

**Additive by default.** A transcript is immutable once Copilot Studio finalises it, so an
already-ingested one is skipped without re-parsing or rewriting. `Reprocess: true` is the
deliberate escape hatch when parser logic changes.

| Parameter | Default | Effect |
| --- | --- | --- |
| *(none)* | — | Incremental, additive |
| `FullSync` | `false` | Rescan from the beginning, still additive |
| `Reprocess` | `false` | Rewrite already-ingested sessions |
| `MaxRecords` | `20` | Batch cap — plugins have a 2-minute sandbox limit |
| `IncludeTraces` | `false` | Also store `trace` / `DialogTracing` activities (~4× rows) |

---

## Known limitations

These are real and worth understanding before you rely on the numbers.

1. **`DialogTracing` is design-mode only.** Exact tool-call and flow-invocation traces exist
   only for maker-portal test chats. Production channels (`msteams`, `m365copilot`) fall back
   to coarser `DynamicPlan` step windows. Each entry is badged `action` or `plan step`.
2. **Flow correlation is time-based.** `flowrun.conversationid` is null, so runs are matched by
   time overlap (±20s) and ranked by closeness. Confidence is shown as `high` / `multiple` /
   `no run matched`. Under concurrent load, `multiple` gets noisier.
3. **Flow run details cross a separate security boundary.** The Power Automate API uses a
   different audience than Dataverse, so the plugin creates durable pending rows but cannot fetch
   their bodies. Enrichment needs either a DLP-approved HTTP/custom connector or the headless
   `fetch_flow_run_details.py` worker. PVE Dev now allows the connector, but runtime policy cache
   propagation must complete before the in-platform processor can be validated.
4. **Retention.** Flow runs age out of Power Automate independently of Dataverse. Fetch details
   promptly or the drill-down will be empty.
5. **Code apps are preview** and require premium licensing. The model-driven app is the
   supportable surface; the code app is the richer one.
6. **Inputs to connector actions are not logged** in the transcript itself — only outputs and
   exceptions. Full inputs come from the flow run detail fetch.
7. **Credits are aggregate source facts.** No reviewed source exposes a billing-event ID shared
   with one transcript, evaluation, tool call, or user-agent pair. Correlation is shown as context,
   never as exact allocation.
8. **Governance writes are deliberately narrow.** Version `1.3.0.0` changes only one agent/resource
   threshold per audited request. Per-user limits, environment allocations, TenantPool, and PayGo
   mutation are not implemented.

---

## Repository layout

```text
config/      environment configuration (only *.sample.json is committed)
docs/        API reference, architecture, operations, findings
plugin/      C# Dataverse plugin behind the Custom API (net462)
pcf/         PCF JSON viewer control
codeapp/     Power Apps code app (React + Vite)
solution/    declarative Dataverse schema definition
scripts/     Python toolkit — provisioning, sync, registration, fetch
```

---

## Documentation

- [API reference](docs/api-reference.md) — transcript payloads, PPAC credit source routes, and Custom API contracts
- [Dataverse data model](docs/data-model.md) — tables, columns, relationships, keys, and retention
- [Architecture](docs/architecture.md) — data model, sync semantics, correlation strategy
- [Cross-environment credit consumption design](docs/cross-environment-credit-consumption-design.md) — Copilot Studio harness usage, capacity, attribution, and reporting plan
- [Copilot Credit reporting](docs/credit-reporting.md) — live components, source grain, agent/day/week reporting, per-user endpoint, security, and limitations
- [Operations](docs/operations.md) — deploy, run, schedule, troubleshoot
- [Flow run detail findings](docs/flow-run-detail-findings.md) — tested APIs, payload depth, DLP and deployment options
- [Monitor endpoint findings](docs/monitor-endpoint-findings.md) — why the CSV export is not used

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE).

> Not affiliated with or endorsed by Microsoft. "Copilot Studio", "Power Apps", "Power Automate"
> and "Dataverse" are trademarks of Microsoft Corporation. This project uses documented and
> observed platform behaviour; undocumented behaviour may change without notice.
