# Full Power Automate run detail: verified findings

Tested in PVE Dev on 2026-08-03 with the admin identity and real ESS ServiceNow flows.

## What is available natively in Dataverse

The `flowrun` table is solution-friendly and readable by the plugin. It provides run-level
metadata, including:

- run, workflow, status, start/end, duration
- `errorcode` and `errormessage`
- `parentrunid`, `callingproductrunid`, and `isprimary`
- `workflowname` and `conversationid`

It does not contain action inputs, outputs, per-iteration errors, trigger bodies, or response
bodies. The live `flowevent` table has an `eventcontent` memo column, but contained no records in
PVE Dev and cannot be relied on as the action-history source.

## What the Flow service API provides

The Flow service API is the only tested source that returned the complete cloud-flow execution:

```text
GET https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/
    environments/{environmentId}/flows/{flowApiId}/runs/{runId}
GET .../runs/{runId}/actions
GET .../runs/{runId}/actions/{actionName}/repetitions
```

Authentication requires a token for `https://service.flow.microsoft.com/`. Action, trigger, and
response records contain short-lived `inputsLink` and `outputsLink` SAS URLs. The caller must
download those links immediately to obtain the actual bodies.

This `2016-11-01` Flow service surface is an observed contract used by the maker experience and
current diagnostic tooling; it is not the documented Power Platform REST run-history contract.
Treat API shape/version changes as an operational risk and keep the structural live test in the
deployment validation process.

Live proof against `ESS IT ServiceNow ITSM Get Tickets List`:

- 21 actions returned
- 13 action input links and 10 action output links returned
- a SAS output downloaded as structured JSON (`statusCode`, `headers`, `body`)
- six actions had repetition history, totaling ten loop iterations
- trigger input/output, response output, `clientTrackingId`, and Copilot `clientKeywords` returned

Secure inputs/outputs remain intentionally unavailable when a flow author enabled those settings.

## APIs and connectors that were not sufficient

### Power Automate Management connector

The live connector exposes 24 operations. It can list/get flows, manage owners, resubmit/cancel a
known run, and perform admin operations. It has no operation to list runs, get run details, list
actions, or download inputs/outputs.

### Power Platform DSR API

The 2026 Power Platform REST API documents environment-scoped DSR endpoints for flow runs and run
history data. In PVE Dev, normal cloud-flow requests returned:

- `403 PowerPlatformAuthZFailure` for flow runs and run-history data
- `404 RouteNotFound` for the `aiFlows/.../actions` route with a normal cloud-flow ID

These DSR/compliance endpoints are not a drop-in operational diagnostics API in this environment.

### HTTP with Microsoft Entra ID

The preauthorized connector successfully created a connected Flow-service connection. Before the
policy update, Power Automate suspended its probe flow with:

```text
CompanyDlpViolation
Admin data policy 'Advanced Connector Policy' restricts use of .../shared_webcontents.
```

On 2026-08-03, `shared_webcontents` and `shared_webcontentsv2` were added as `AllAllowed` to the
ACP inherited from **PVE Admin Group** (`3fe576fb-4f71-4d96-b8d7-3a97449fd2b5`). The source policy
was modified at `07:45:24Z`; PVE Dev's generated synced policy copy updated at `07:45:30Z` with the
same 28-entry allowlist. A new probe then remained `Started`, proving design-time enforcement had
accepted the connector.

Its first runtime call still returned HTTP `442 ConnectorPolicyRuntime`. The signed action output
reported that the runtime policy cache was last refreshed on `2026-07-29`, five days before the
allowlist update. The remaining blocker is policy propagation, not policy content, authentication,
or flow suspension. Microsoft documents that data-policy propagation normally completes within an
hour and can take up to 24 hours in extreme cases.

## Implemented data path

Transcript sync now creates an idempotent `pvci_flowrundetail` placeholder for every correlated run.
The row is a durable retry queue item; `pvci_fetchedon` distinguishes pending from enriched rows.

`fetch_flow_run_details.py` now:

1. maps Dataverse workflow IDs to Flow API IDs,
2. reads the flow definition and attaches action type, operation, `runAfter`, parent, and branch,
3. follows paged flow/action/repetition collections,
4. downloads trigger, response, action, and iteration bodies,
5. stores correlation context and structured root errors,
6. updates pending placeholders rather than skipping them.

The code app turns this data into a connected execution map. Actions are colored by status,
dependencies are drawn as directed paths, the likely root failure is selected and centered first,
and skipped branches are hidden by default. Selecting a node opens a human-readable inspector with
the error, action metadata, prerequisites, loop status, and collapsible technical inputs/outputs.
Expected `ActionSkipped` branch messages no longer fill the main error surface.

Use `--run-name <run-id>` to reproduce one specific failed execution.

## Deployment choices

### Power Platform-only

Allow an approved HTTP/custom connector to call `api.flow.microsoft.com`, bind it through a solution
connection reference, and use the built-in HTTP action for the SAS downloads. This requires a DLP
policy decision and premium licensing. PVE Dev's ACP now allows the connector and its synced policy
copy is current; runtime validation and processor packaging remain pending until the connector
policy cache refreshes.

### Headless worker

Run the existing fetcher core in an Azure Function, Container App job, or another scheduled worker.
Use a service principal/application user with explicit environment and flow access, and store no
client secret in Dataverse. This mode is compatible with the current DLP policy but adds a deployed
component outside the Power Platform solution.

Until the in-platform processor is packaged or the headless worker is deployed, a solution ZIP by
itself cannot retrieve full run bodies. Claiming full portability before one path is validated
would be incorrect.
