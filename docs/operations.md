# Operations

## Configuration

Copy the sample and fill it in — environment-specific configs are gitignored.

```bash
cp config/transcript_solution_config.sample.json config/transcript_solution_config.dev.json
```

| Key | Notes |
|---|---|
| `tenantId` | Entra tenant GUID |
| `environmentId` | Power Platform environment GUID (from the maker portal URL) |
| `dataverseUrl` | `https://<org>.crm<N>.dynamics.com` — no trailing slash |
| `oauth.dataverseScope` | `<dataverseUrl>/.default` |
| `botId` | Copilot Studio agent id — only used by the Monitor probe scripts |

## Authentication

`dv_token.py` resolves tokens silently, in order:

1. **Azure CLI** — `az account get-access-token`. Silent after one `az login`.
2. **MSAL disk cache** — `.msal_token_cache.json`, chmod 600, gitignored.
3. **Device code** — prints a code rather than opening a browser.

If tokens expire: `az login --tenant <tenantId>`.

## First-time deployment

```bash
CFG=config/transcript_solution_config.dev.json
source .venv/bin/activate

# 1. Schema — idempotent, safe to re-run after editing solution-definition.json
python3 scripts/transcript_insights/provision_dataverse_solution_webapi.py \
        --config $CFG --definition solution/pvConversationInsights/solution-definition.json

# 2. Views and app
python3 scripts/transcript_insights/create_app_views.py        --config $CFG
python3 scripts/transcript_insights/create_model_driven_app.py --config $CFG

# 3. PCF control, then forms (forms bind to the control, so order matters)
cd pcf/JsonViewer && npm install && npm run build && pac pcf push --publisher-prefix pvci && cd ../..
python3 scripts/transcript_insights/create_forms.py --config $CFG

# 4. Plugin + Custom API
cd plugin && dotnet build -c Release && cd ..
python3 scripts/transcript_insights/register_plugin.py --config $CFG

# 5. Schedule
python3 scripts/transcript_insights/create_sync_flow.py --config $CFG --frequency Hour --interval 1 --activate

# 6. Initial load
python3 scripts/transcript_insights/sync_transcripts.py --config $CFG --full
```

`pac pcf push` prefixes the publisher, registering the control as
`pvci_PvciControls.JsonViewer`. `create_forms.py` resolves that name at runtime, so it works in
any environment.

## Routine operation

Once the flow is active, nothing manual is required. It calls the Custom API hourly and loops
until a batch returns fewer records than `MaxRecords`, so a backlog clears in one run.

Run details are the exception — the Power Automate API needs a different token audience than
Dataverse, so a plugin cannot fetch them:

```bash
python3 scripts/transcript_insights/fetch_flow_run_details.py --config $CFG
```

Schedule this separately (cron, CI, or an Azure Function). Flow runs age out of Power Automate
independently of Dataverse, so late fetches return nothing.

## Manual sync

```bash
python3 scripts/transcript_insights/sync_transcripts.py --config $CFG            # incremental
python3 scripts/transcript_insights/sync_transcripts.py --config $CFG --full     # rescan, still additive
python3 scripts/transcript_insights/sync_transcripts.py --config $CFG --full --reprocess   # re-derive
```

Use `--reprocess` after changing parser logic. It rewrites sessions and replaces their turns,
which issues new turn GUIDs.

Or invoke the Custom API directly:

```http
POST {dataverseUrl}/api/data/v9.1/pvci_SyncConversationTranscripts
{ "FullSync": false, "MaxRecords": 50, "Reprocess": false, "IncludeTraces": false }
```

## Health checks

The single source of truth is `pvci_syncstate`:

```http
GET {dataverseUrl}/api/data/v9.1/pvci_syncstates
    ?$select=pvci_lastrunon,pvci_lastrunstatus,pvci_recordsprocessed,pvci_lasterror
```

| `pvci_lastrunstatus` | Meaning |
|---|---|
| `success` | All transcripts in the batch processed |
| `partial` | Some failed; watermark frozen so they retry next run |
| `failed` | Nothing processed — check `pvci_lasterror` |

A frozen watermark is by design: it stops a failing transcript being skipped forever.

## Promoting to another environment

```bash
pac solution export --name pvConversationInsights --path ./pvConversationInsights.zip --managed
pac auth create --environment <target-org-url>
pac solution import --path ./pvConversationInsights.zip --activate-plugins
```

Afterwards, in the target environment:

1. Rebind the connection reference `pvci_dataversesync` to a connection that exists there.
2. Re-activate the flow.
3. Run the initial `--full` load.
4. Redeploy the code app (`npx power-apps init` + `push`) — it lives outside the solution.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `conversationtranscripts` returns empty | Missing Read privilege on the table returns an empty set, not `403`. Also check transcripts are enabled on the agent, and allow for post-session lag |
| Tool Calls empty on a production session | Expected — `DialogTracing` is design-mode only |
| Flow Runs shows `no run matched` | The run aged out of Power Automate retention, or fell outside the ±20s window |
| Flow Runs shows `multiple` | Normal for orchestrator + child flow patterns, and under concurrent load |
| A tab is blank but the header shows a count | The field is missing from the app's detail projection |
| `401` from a script | `az login --tenant <tenantId>` |
| Plugin returns `Status: failed` | Read `Errors` in the response and `pvci_lasterror` |
| Flow does not start | Check the connection reference is bound and the flow is activated |

## Data protection

`pvci_*` tables contain personal data. Restrict privileges, set a retention policy, and enable
auditing where required — see [SECURITY.md](../SECURITY.md).
