# Transcript Insights Scripts

**Primary path — Dataverse `conversationtranscripts` (v9.1).** This is the endpoint that works
and carries end-user identity. See `docs/api-reference.md`.

## Solution pipeline (v9.1)

The current `2.0.0.5` release contract builds exactly three managed candidates:
`pvConversationInsights` required core, `pvConversationInsightsCredits` optional licensing runtime,
and `pvConversationInsightsCodeApp` optional unsupported preview. Core retains all schema, plugins,
APIs, roles, apps, inventory/transcript runtime, four transcript/shared flows, and three
non-licensing references. The add-on owns only three credit flows, the two licensing references,
and the required `pvci_CreditReportingTenantId` definition. Core inventory derives tenant scope
server-side and does not depend on that variable.
These are candidate artifacts under `output/candidate/`; public `1.4.0.15` downloads remain
unchanged until stable promotion; the user-performed manual Contoso TPM upgrade passed.

For a clean candidate install use core, optional credits, then optional code app. For an upgrade
from `1.4.0.15`, install credits first, apply the core managed upgrade second, and upgrade the code
app last. Transcript-only operation omits the credit add-on and does not need licensing
administrator access.

Local transcript sync is automatic in the environment where the solution is installed. Tenant
inventory discovery and a readable verification probe are not consent to collect from another
environment. A verified remote source begins collection only after an administrator explicitly
enables it and confirms that its transcripts will be copied into and retained by the installed
Dataverse environment. Disabling that source stops future imports but does not delete copied data.
Every utility that mutates Dataverse validates the configured tenant through
`require_authorized_config` or `require_authorized_tenant`; only development tenant
`1938ee32-a258-454c-b8db-3a928341bd69` is accepted. Read-only probes remain available elsewhere.
Until a remote source is enabled, Sessions, Trends, and Credits resource reporting are scoped to the
host environment and do not show environment selectors. Credit user usage and recent governance
request history remain tenant-wide. Credits remains visible as Unavailable without its add-on, Setup
required before a successful credit sync, and Ready only after that evidence exists.

Run in this order against a fresh environment:

```bash
# 1. Schema: solution, publisher, 17 custom tables, lookups
python3 scripts/transcript_insights/provision_dataverse_solution_webapi.py \
  --config config/transcript_solution_config.dev.json \
  --definition solution/pvConversationInsights/solution-definition.json

# 2. Views
python3 scripts/transcript_insights/create_app_views.py \
  --config config/transcript_solution_config.dev.json

# 3. Model-driven app
python3 scripts/transcript_insights/create_model_driven_app.py \
  --config config/transcript_solution_config.dev.json

# 4. Initial load, then incremental thereafter
python3 scripts/transcript_insights/sync_transcripts.py \
  --config config/transcript_solution_config.dev.json --full
```

### `sync_transcripts.py`

Reads `conversationtranscripts`, parses the Bot Framework activity stream, resolves the end
user via `from.aadObjectId` → `systemuser`, and upserts into `pvci_transcriptsession`,
`pvci_transcriptturn`, `pvci_transcriptidentitymap`. Watermark lives in `pvci_syncstate`.

| Flag | Effect |
| --- | --- |
| *(none)* | Incremental from stored watermark |
| `--full` | Reprocess everything (idempotent) |
| `--since 2026-07-01T00:00:00Z` | Explicit start |
| `--include-traces` | Also store `trace` / `DialogTracing` activities (~4x row volume) |
| `--limit N` | Cap transcripts, useful for smoke tests |

Re-running is safe: sessions are matched on `pvci_transcriptid` and updated in place, with
their turns replaced.

### Scheduling

`run_sync.sh` is the bash/cron/launchd wrapper for macOS/Linux, and `run_sync.ps1` is the equivalent for Windows PowerShell:

```bash
*/15 * * * * /path/to/scripts/transcript_insights/run_sync.sh >> /var/log/pvci_sync.log 2>&1
```

```powershell
$env:PVCI_CONFIG = 'config/transcript_solution_config.sandbox.json'
.\scripts\transcript_insights\run_sync.ps1
```

Override the target with `PVCI_CONFIG=config/transcript_solution_config.sandbox.json`.

For a fully in-platform option, the same logic belongs in a Dataverse **custom API + plugin**
(no token needed — `IOrganizationService` reads the table in-process) triggered by a scheduled
Power Automate flow.

## Authentication

`dv_token.py` resolves tokens silently, in order:

1. **Azure CLI** — `az account get-access-token`. Silent after one `az login`.
2. **MSAL disk cache** — `.msal_token_cache.json` (gitignored, chmod 600).
3. **Device code** — prints a code rather than opening a browser.

If tokens expire: `az login --tenant <tenantId>`.

## Investigation / reference scripts

- `probe_dual_endpoints.py` — tests Monitor and Dataverse v9.1 side by side into one report.
- `correlate_monitor_to_dataverse.py` — GUID-candidate matching between the two sources.
- `extract_har_contract.py` — recovers the Monitor endpoint contract from a HAR capture.
- `extract_credit_har_contract.py` — emits a schema-only, sanitized Power Platform licensing
  contract from a PPAC HAR capture. It never copies headers, cookies, tenant/user/resource IDs,
  names, or response values.
- `create_credit_sync_flow.py` — creates the solution-aware daily PPAC Copilot Credit resource,
  user-usage, and capacity collector with a seven-day overlap and bounded paging.
- `create_credit_forms.py` — publishes operator forms for Agent Inventory, Credit Usage, Credit
  Capacity, Environment Inventory, Inventory Sync Runs, user usage, and privacy approval.
- `create_inventory_sync_flow.py` — creates the stopped Admin V2/One Inventory tenant inventory
  collector; bind a target-local Power Platform Administrator connection before activation.
- `create_credit_governance_flow.py` — creates the stopped read-only Power Platform resource-
  threshold collector using a dedicated `licensing.powerplatform.microsoft.com` HTTP with Entra ID
  connection and a tenant-scoped `v1.0` route.
- `create_credit_governance_processor_flow.py` — creates the stopped privileged processor for
  validated threshold requests with stale-state detection and before/after audit.
- `create_security_roles.py` — creates PVCI Analyst, PVCI Privacy Approver, PVCI Credit Administrator, and PVCI Source Access Processor
  from the App Opener baseline, adds least-privilege table access, and maps all three
  roles to the model-driven app.
- `ingest_monitor_transcripts.py` — Monitor CSV ingestion (**blocked**: gateway returns
  `403 UnauthenticatedUser` for non-first-party tokens).
- `build_dataverse_upsert_payload.py` — shapes Monitor CSV rows for upsert.

Extract the Copilot Credit endpoint and payload contract from a local PPAC capture:

```bash
python3 scripts/transcript_insights/extract_credit_har_contract.py \
  logs/admin.powerplatform.microsoft.com.har \
  --output output/credit-har-contract.json

python3 -m unittest scripts.transcript_insights.test_extract_credit_har_contract -v
```

The generated `output/` artifact is intentionally gitignored. Commit only reviewed synthetic or
schema-only fixtures; never commit the source HAR.

Create the stopped scheduled collector after creating an **HTTP with Microsoft Entra ID
(preauthorized)** connection whose Base Resource URL and Microsoft Entra ID Resource URI are both
`https://licensing.powerplatform.microsoft.com/`:

```bash
python3 scripts/transcript_insights/create_credit_sync_flow.py \
  --config config/transcript_solution_config.dev.json \
  --http-connection-id shared-webcontents-00000000
```

Install the optional credit add-on first. The script writes the configured tenant ID as the current
value of `pvci_CreditReportingTenantId` outside the solution. On subsequent deployments,
`--http-connection-id` is optional and the existing target-environment `pvci_licensinghttp`
binding is reused. Neither the current tenant value nor the physical connection ID is exported.

The flow reads only the observed PPAC resource-usage, user-usage, and environment-capacity routes,
follows up to 20 pages of 100 resource rows, splits the unpaged tenant-wide user projection into
250-row chunks, and imports through `pvci_ImportCreditUsageBatch`. User facts are GUID-only unless
the shared audited privacy setting is approved. Authenticate and save the stopped solution flow
once, run a smoke test, inspect the Credit Sync Run row, then activate the daily schedule. Do not
use `--activate` before that smoke test succeeds.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r scripts/transcript_insights/requirements.txt
```

Environment configs: `config/transcript_solution_config.dev.json`,
`config/transcript_solution_config.sandbox.json`.

## Multi-environment sync (tenant-wide)

Use `sync_multi_environment.py` to run the same ingest flow across multiple
environment config files and produce one aggregate summary.

```bash
python3 scripts/transcript_insights/sync_multi_environment.py \
  --configs config/transcript_solution_config.dev.json config/transcript_solution_config.sandbox.json
```

Useful options:

| Flag | Effect |
| --- | --- |
| `--full` | Reprocess all configured environments |
| `--since <iso>` | Override watermark for all environments |
| `--limit N` | Cap transcripts per environment |

Each synced session is stamped into `pvci_datasource` with source context:
`dataverse_v9.1|tenant:<id>|env:<id>|envName:<name>|org:<host>`.

`environmentId` is the required Power Platform environment GUID from the maker portal URL and is
stored in `pvci_environmentid`. The optional label override below is otherwise read from
`organization.friendlyname`:

```json
{
  "environmentName": "PVE Dev"
}
```

### Central transcript source discovery (phase 1)

Classify which tenant environments can be read without a
source-environment solution install:

```bash
pac admin list --json > output/test-tenant-admin-environments.json
python3 scripts/transcript_insights/probe_transcript_sources.py \
  --config config/transcript_solution_config.dev.json \
  --inventory output/test-tenant-admin-environments.json \
  --output output/transcript-source-registry.json
```

The probe requests a separate Dataverse audience token for each source organization and performs
a one-row `conversationtranscripts` query. Its output is safe registry metadata only: source
identity, access status, and a sample count. It distinguishes `readable_empty` from
`access_denied`; it does not copy transcript payloads. The resulting registry is the input
contract for the central collector.

Validate least-privilege application-user onboarding only in a newly created disposable sandbox:

```bash
python3 scripts/transcript_insights/validate_source_access_onboarding.py \
  --tenant-id 1938ee32-a258-454c-b8db-3a928341bd69 \
  --environment-id <disposable-environment-id> \
  --environment-url https://<disposable-org>.crm4.dynamics.com \
  --public-client-id aebc6443-996d-45c2-90f0-388ff96faa56
```

The utility refuses other tenants and requires the ID and URL to resolve to a Sandbox named
`PVCI Onboarding E2E ...`. It creates an empty baseline role, proves the application user receives
HTTP 403, assigns organization-level `prvReadconversationtranscript`, proves HTTP 200, verifies
that System Administrator was never assigned, and unregisters the disposable Entra application.
Delete the disposable environment afterward to remove its test roles and application-user rows.

The central worker proof of concept can read and parse the registry-approved sources without
writing by using `--dry-run`:

```bash
python3 scripts/transcript_insights/collect_central_transcripts.py \
  --config config/transcript_solution_config.dev.json \
  --registry output/transcript-source-registry.json \
  --limit 1 --dry-run
```

The flow definition generator emits the tenant-neutral review definition and the packaged core
workflow artifact:

```bash
python3 scripts/transcript_insights/create_central_transcript_flow.py \
  --output output/central-transcript-flow.json \
  --solution-output solution/pvConversationInsights/src/Workflows/PVCICollectCentralTranscriptsscheduled-371B3CAD-8596-F111-8076-7CED8D95B46E.json
```

Register the collector-side `pvci_ImportCentralTranscriptBatch`, import the registry, and perform a
one-row source smoke test before deploying the stopped solution flow. Each source connection must
be created in the collector environment; a connection created in the source environment cannot be
bound across environments. The Custom API caps batches at 25 and uses a composite tenant,
environment, and source transcript key.

The generic flow is packaged in `pvConversationInsights`. It reads Environment Inventory with the
packaged `pvci_centralcollector` Dataverse reference and uses
`ListRecordsWithOrganization` with each row's dynamic `pvci_environmenturl`. Environment names,
IDs, URLs, and enablement remain runtime data; per-source connection references are forbidden.
Operators enable reviewed rows from the code app. The flow performs a one-row ID-only access probe
before each bounded content read. Probe failures record denial, disable that source, and complete
the iteration; downstream collection/import failures remain visible as run failures.

Source-managed onboarding uses an audited request before collector enablement:

```bash
python3 scripts/transcript_insights/create_transcript_access_verification_flow.py \
  --output output/transcript-access-verification-flow.json \
  --solution-output solution/pvConversationInsights/src/Workflows/PVCIVerifyTranscriptSourceAccessscheduled-F324DBAA-6E9D-F111-B8DE-7CED8D95B46E.json

python3 scripts/transcript_insights/smoke_test_transcript_access_verification.py
python3 scripts/transcript_insights/smoke_test_transcript_access_verification.py \
  --request-key <request-key>
```

The packaged verifier processes only `Pending` + `Verify` requests, performs one ID-only read with
`pvci_centralcollector`, and projects verified or denied access. It intentionally leaves role and
elevation-cleanup verification false. `Provision`, `Repair`, and `Remove` remain reserved for the
external administrator-bootstrap reconciler, so the code app keeps that mode unavailable.
