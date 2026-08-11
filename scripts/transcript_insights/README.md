# Transcript Insights Scripts

**Primary path — Dataverse `conversationtranscripts` (v9.1).** This is the endpoint that works
and carries end-user identity. See `docs/customer-facing/ConversationTranscripts-API-Reference.md`.

## Solution pipeline (v9.1)

Run in this order against a fresh environment:

```bash
# 1. Schema: solution, publisher, 4 tables, lookups
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
|---|---|
| *(none)* | Incremental from stored watermark |
| `--full` | Reprocess everything (idempotent) |
| `--since 2026-07-01T00:00:00Z` | Explicit start |
| `--include-traces` | Also store `trace` / `DialogTracing` activities (~4x row volume) |
| `--limit N` | Cap transcripts, useful for smoke tests |

Re-running is safe: sessions are matched on `pvci_transcriptid` and updated in place, with
their turns replaced.

### Scheduling

`run_sync.sh` is a cron/launchd-ready wrapper:

```bash
*/15 * * * * /path/to/scripts/transcript_insights/run_sync.sh >> /var/log/pvci_sync.log 2>&1
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
  Capacity Snapshots, and Credit Sync Runs.
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

Provision the solution schema first. The script writes the configured tenant ID as the current
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
|---|---|
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
