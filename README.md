# MCS Transcript Analyzer

Ingest, correlate and analyse **Microsoft Copilot Studio** conversation transcripts in
Dataverse — with end-user attribution, response latency, agent reasoning, tool calls, and
correlated Power Automate flow runs.

Built because the Copilot Studio Monitor CSV export drops the two things you need most when
a customer says *"the agent answered wrong"*: **who** was talking, and **why** the agent did
what it did.

---

## What you get

| Surface | What it is |
|---|---|
| **Dataverse solution** | 6 tables, views, forms, a model-driven app, a Custom API, and a scheduled flow |
| **Model-driven app** | GA, standard-licensed. Grids + tabbed forms with a JSON viewer PCF control |
| **Code app** (preview) | React/Vite triage UI: conversation replay, latency trends, tool and flow drill-down |
| **Custom API + plugin** | In-platform incremental sync — no token, no external host |
| **Python toolkit** | Bulk backfill, plugin registration, flow-run detail fetch |

### Captured per session

- **End user** — resolved from `from.aadObjectId` to a real `systemuser`
- **Latency** — first / average / slowest reply, in milliseconds, and per turn
- **Agent reasoning** — the `DynamicPlan*` trace showing which topic or tool was chosen, and why
- **Tool calls** — connector and AI Builder invocations with duration, output and exceptions
- **Flow runs** — correlated Power Automate runs, drillable to per-action inputs and outputs
- **Outcome** — resolved / abandoned, reason, implied success, turn count
- **Test-mode flag** — so maker-portal testing does not pollute production metrics

---

## Why not the Monitor export?

Copilot Studio surfaces transcripts in two places, and they are **not** the same data.

| | Monitor / Analytics export | `conversationtranscripts` (used here) |
|---|---|---|
| Format | CSV, one row per session | JSON, full Bot Framework activity stream |
| End-user identity | ✗ | ✅ `from.aadObjectId` |
| Reasoning / orchestration events | ✗ | ✅ full `DynamicPlan*` trace |
| Callable with a normal token | ✗ `403 UnauthenticatedUser` | ✅ standard Dataverse auth |
| Usable from a plugin or flow | ✗ | ✅ |

See [docs/monitor-endpoint-findings.md](docs/monitor-endpoint-findings.md) for the evidence.

---

## Quick start

**Prerequisites:** Python 3.10+, Node 22+, .NET SDK 8+, [Power Platform CLI](https://aka.ms/PowerPlatformCLI),
Azure CLI, and a Dataverse environment where you hold System Customizer.

```bash
git clone https://github.com/pavecer/mcs-transcript-analyzer.git
cd mcs-transcript-analyzer

python3 -m venv .venv && source .venv/bin/activate
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

cd plugin && dotnet build -c Release && cd ..
python3 scripts/transcript_insights/register_plugin.py  --config $CFG
python3 scripts/transcript_insights/create_sync_flow.py --config $CFG --activate

python3 scripts/transcript_insights/sync_transcripts.py --config $CFG --full   # initial load
```

Optional code app:

```bash
cd codeapp && npm install
npx power-apps init -n 'Conversation Insights Explorer' -e <environment-id>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_transcriptsession --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_transcriptturn   --org-url <org-url>
npx power-apps add-data-source --api-id dataverse --resource-name pvci_flowrundetail    --org-url <org-url>
npm run build && npx power-apps push
```

Full walkthrough: [docs/operations.md](docs/operations.md).

---

## How the sync works

```
Dataverse conversationtranscript
        │
        │  pvci_SyncConversationTranscripts   (Custom API + sandboxed plugin)
        │  ← called hourly by a Power Automate recurrence flow, in a drain loop
        ▼
pvci_transcriptsession ──< pvci_transcriptturn
        │                        │
        ├── pvci_transcriptidentitymap   (aadObjectId → systemuser)
        ├── pvci_syncstate               (watermark + last run status)
        └── pvci_flowrundetail           (per-action inputs/outputs, fetched by script)
```

**Additive by default.** A transcript is immutable once Copilot Studio finalises it, so an
already-ingested one is skipped without re-parsing or rewriting. `Reprocess: true` is the
deliberate escape hatch when parser logic changes.

| Parameter | Default | Effect |
|---|---|---|
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
3. **Flow run details need a separate token.** The Power Automate API uses a different audience
   than Dataverse, so a plugin cannot call it. `fetch_flow_run_details.py` runs outside the
   platform and is **not** covered by the scheduled flow.
4. **Retention.** Flow runs age out of Power Automate independently of Dataverse. Fetch details
   promptly or the drill-down will be empty.
5. **Code apps are preview** and require premium licensing. The model-driven app is the
   supportable surface; the code app is the richer one.
6. **Inputs to connector actions are not logged** in the transcript itself — only outputs and
   exceptions. Full inputs come from the flow run detail fetch.

---

## Repository layout

```
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

- [API reference](docs/api-reference.md) — the `conversationtranscripts` payload, field by field
- [Architecture](docs/architecture.md) — data model, sync semantics, correlation strategy
- [Operations](docs/operations.md) — deploy, run, schedule, troubleshoot
- [Monitor endpoint findings](docs/monitor-endpoint-findings.md) — why the CSV export is not used

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE).

> Not affiliated with or endorsed by Microsoft. "Copilot Studio", "Power Apps", "Power Automate"
> and "Dataverse" are trademarks of Microsoft Corporation. This project uses documented and
> observed platform behaviour; undocumented behaviour may change without notice.
