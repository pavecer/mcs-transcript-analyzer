---
name: central-transcript-collector
description: "Deploy and validate the MCS Transcript Analyzer cross-environment central transcript collector. Use when probing transcript access, registering pvci_ImportCentralTranscriptBatch, updating environment inventory collector status, creating source HTTP with Entra connections, binding or activating PVCI Collect Central Transcripts, deploying the model-driven/code apps, or smoke-testing cross-environment transcript import."
argument-hint: "Describe the collector environment and source environments to deploy or validate"
---

# Central Transcript Collector

Use this workflow for the cross-environment transcript collector. The collector solution, Custom
API, scheduled flow, model-driven app, and code app live only in the collector environment. Source
environments do not require the PVCI solution.

## Confirm The Target

Before changing Dataverse metadata or flows, explicitly confirm the collector URL, solution, and
publisher. Before every write, also verify that the authenticated tenant ID is exactly
`1938ee32-a258-454c-b8db-3a928341bd69`. Tenant names and PAC profile aliases are not authorization.
For this repository's current development environment:

- Collector: `PVE Dev`
- URL: `https://org760734c4.crm4.dynamics.com`
- Environment ID: `006cf8b9-27f8-e2f7-8a14-9be3642d8552`
- Solution: `pvConversationInsights`
- Publisher prefix: `pvci`

Run `pac org who` after selecting or creating the PAC profile. Do not infer the target from the
active profile. If the tenant ID is absent, different, or ambiguous, perform read-only checks only.
Never import, upgrade, publish, configure, or write data programmatically in the TPM manual-upgrade
tenant. The user performs TPM solution imports and upgrades manually.

## Implementation And Deployment Order

1. Probe environment access with `probe_transcript_sources.py`. Persist only source identity,
   `readable_with_rows`, `readable_empty`, `access_denied`, `unavailable`, sample count, and bounded
   errors. Never persist transcript payloads in the registry.
2. Provision the `pvci_environmentinventory` transcript-access and collector-health columns through
   `provision_dataverse_solution_webapi.py`.
3. Build the Release plugin and register `pvci_ImportCentralTranscriptBatch` with
   `register_central_transcript_plugin.py`.
4. Import the registry with `import_transcript_source_registry.py`. `readable` means the mapped
   Dataverse identity can query the source. Keep `pvci_transcriptcollectorenabled=false` until the
   source is reviewed and explicitly selected.
5. Deploy model-driven views/forms and push the code app. Both apps read the same environment
   inventory rows; the code app's dedicated Inventory Management page is the operator surface for
   discovery health, source readiness, and collector enablement.
6. Run `invoke_central_transcript_import.py --limit 1` against a readable source before activating
   the flow. Run it twice: the first call must create/update, and the second must skip through the
   composite tenant/environment/transcript key.
7. Create/update `PVCI Collect Central Transcripts (scheduled)` stopped inside
   `pvConversationInsights`. It must use the packaged `pvci_centralcollector` Microsoft Dataverse
   reference and `ListRecordsWithOrganization` with the dynamic inventory URL.
8. Map the one packaged Dataverse reference, mark only reviewed sources collector-enabled in the
   code app, activate the packaged flow, and verify the first run plus environment
   watermark/status/error fields. The flow must probe one ID-only row before collection. Failed
   probes must disable and skip only that source; collection/import failures must remain visible.
9. Export the live unmanaged solution, unpack into `solution/pvConversationInsights/src`, remove
   unrelated tenant drift, then run all tests, builds, documentation validators, and solution pack.

## Public Package Invariant

The repository has exactly three managed product solutions. `pvConversationInsights` owns the
required transcript and shared inventory runtime, including
`PVCI Collect Central Transcripts (scheduled)`. `pvConversationInsightsCredits` is optional and
owns only the licensing HTTP references and three credit runtime flows.
`pvConversationInsightsCodeApp` contains only the separate preview code app and its dependencies.

The core flow must be tenant-neutral and must package:

- one `pvci_centralcollector` Microsoft Dataverse connection reference;
- one generic `PVCI Collect Central Transcripts (scheduled)` flow;
- `ListRecordsWithOrganization` using `pvci_environmenturl` from Environment Inventory;
- the bounded `pvci_ImportCentralTranscriptBatch` action.

It must not package hardcoded source tenant/environment IDs, names, URLs, physical connection IDs,
or `pvci_transcript_http_*` / `pvci_transcript_source_*` references. `validate_site.py` and the
candidate validator enforce these rules.

## Connection Boundary

Map `pvci_centralcollector` during solution import to one active Microsoft Dataverse connection.
That connection identity must have read access to `conversationtranscripts` in every selected
source and read/write/Custom API permission in the collector. The selected-environment connector
operation supports dynamic source URLs and user or service-principal connections. Tenant
isolation, DLP, and Dataverse security still apply.

This connection alone is not a tenant-wide authorization mechanism. Dataverse evaluates access in
every source environment. The built-in `Bot Transcript Viewer` role grants user-depth transcript
Read and does not provide an unattended collector organization-wide access to every agent's rows.
Do not present manual per-environment user/role assignment as the scalable product design.

Support two source-authorization modes, both controlled from the code app's Inventory Management
workspace:

- **Source-managed** for restricted environments: the source owner creates/approves the limited
   role and assigns the dedicated collector identity; PVCI performs verification only.
- **Administrator bootstrap** where policy permits temporary elevation: an audited external
   reconciler provisions access and must prove elevation cleanup.
- **Excluded** for environments intentionally outside collection scope.

For administrator bootstrap, use a central access reconciler that:

1. discovers Dataverse environments through the tenant inventory;
2. provisions one dedicated application user in each eligible source;
3. creates or verifies a custom role with organization-level
   `prvReadconversationtranscript` only;
4. associates the application user to that role and removes temporary System Administrator;
5. verifies a one-row transcript read and records health/drift in Environment Inventory; and
6. repeats for newly discovered environments and repairs role drift.

Do not grant source roles to ordinary code-app users. The principal requiring source access is the
identity behind `pvci_centralcollector`. Keep onboarding mode/status, probe status, and collector
enablement separate. Do not render provisioning controls unless the corresponding request processor
or reconciler is deployed; source-managed verification must remain usable without that automation.

Microsoft documents `pac admin assign-user --application-user` for external automation. The BAP
`addAppUser` endpoint that can be called by a packaged HTTP flow is preview and initially grants
System Administrator. Therefore, a solution-only reconciler is not a GA-supported product path
until that endpoint is accepted as a preview dependency or Microsoft exposes an equivalent GA
connector/API. Never leave the temporary System Administrator role in place.

## Browser And OAuth Handling

Repository browser policy normally requires the shared VS Code browser. Use it for portal
navigation, forms, app checks, and screenshots.

The shared browser can fail some Power Platform OAuth popups because Microsoft COOP policy closes
or isolates the popup. This is no longer required per source for the central collector, but can
still affect other packaged references.

When the user explicitly approves an external-browser exception:

1. Read Edge profile metadata from
   `%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\Local State`.
2. Select the profile whose `user_name` matches the intended tenant account. On the current machine,
   `Profile 1` is `D365 Demo Admin` / `admin@D365DemoTSCE54115347.onmicrosoft.com`.
3. Resolve Edge from Windows App Paths or
   `C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe`.
4. Launch only the connector URL with:

   ```powershell
   Start-Process -FilePath $edge -ArgumentList @(
     '--profile-directory=Profile 1',
     '--new-window',
     '<connector-url>'
   )
   ```

5. The agent cannot control that external Edge window in this VS Code session because no native CUA
   or Windows UI Automation tool is exposed. The user performs only the OAuth account/consent step.
6. Detect completion with `pac connection list --environment <collector-url>`. Continue only when
   the intended connection reports `Connected`.

Do not use terminal-launched Playwright, Chromium, coordinate-based SendKeys, or password handling.
Do not treat an `Error` connection as usable. Failed user-owned connections may also be undeletable
through PAC under a different caller; leave them unbound and clean them up through the owning
portal account.

## Validation Evidence

Required before completion:

- focused central collector contract tests;
- all `scripts/transcript_insights/test_*.py` tests;
- Release plugin build;
- code-app tests, build, and lint;
- `scripts/validate_documentation.py`;
- `scripts/validate_site.py`;
- `scripts/validate_browser_policy.py`;
- successful unmanaged solution pack;
- real one-row source import and idempotent replay;
- active packaged-flow run using the mapped `pvci_centralcollector` connection;
- solution membership proof for the flow and reference;
- no per-source references or hardcoded source topology.

## Cross-Tenant Candidate Packages

When another tenant must validate this feature, never overwrite an existing published package
version. Advance core, optional credit add-on, and code app on one synchronized four-part version,
for example `2.0.0.0`.

Before exporting:

1. Verify the generic central flow and `pvci_centralcollector` reference are members of
   `pvConversationInsights` and no supported runtime is outside both product solutions.
2. Run the three-solution ownership and tenant-neutrality guards against source.
3. Set all live PVE Dev product solutions to the candidate version with
   `pac solution online-version`.
4. Export fresh managed core, credit add-on, and code-app ZIPs into `output/candidate/`, not
   `site/downloads/`.
5. Validate solution name, version, managed state, required tables/APIs/apps, code-app dependencies,
   absence of tenant runtime markers, ZIP integrity, and SHA-256 hashes.
6. Provide the validated artifacts for manual target-tenant testing. For a clean install the user
   imports core, optional credit add-on, then code app. For an upgrade from `1.4.0.15`, import the
   add-on first, apply the core managed upgrade second, and upgrade the code app last. Do not
   perform those writes in TPM.

Release `1.4.0.15` supports source-managed verification and collection only after the mapped
identity receives organization-level Conversation Transcript Read in each selected source.
Administrator bootstrap remains unavailable until an external reconciler can provision access and
prove temporary elevation cleanup. Never present manual per-source authorization as zero-touch
onboarding, and never overwrite any prior candidate or published package version.
