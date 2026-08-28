# Clean install validation

This runbook is the authoritative procedure for installing the three managed MCS Transcript
Analyzer packages into a brand-new Dataverse environment. The machine-readable requirements live
in [`config/clean-install-contract.json`](../config/clean-install-contract.json); candidate package
identity and versions come from [`config/release-packages.json`](../config/release-packages.json).

The Power Apps code app is an optional supported surface with its own package and lifecycle. It is
supported by the project maintainer and built on fully supported Microsoft technologies. The
documented Code Apps limitations, environment setting, Power Apps Premium requirement, sharing,
and governance controls still apply. Never change or overwrite a published package while
performing this procedure.

## Verified fresh-environment result

On 2026-08-28, the exact candidate packages imported synchronously from scratch into a second new
unmanaged Sandbox with Dataverse in the authorized test tenant, in this order: core `2.1.0.0`,
Credits `2.0.0.5`, and code app `2.1.0.0`.

Before any import, **Enable code apps** was changed from its default **Off** to **On** in the Power
Platform admin center, saved, and independently reloaded until it remained On and **Save** was
disabled. The core import reported `OpenApiOverrideConnectionInvalidPlaceholderConnection`, and
the Credits import warned that connections must be created. All imports succeeded. These warnings
mean target-local physical connections still need to be created and mapped before flows start; they
do not invalidate a completed package import.

`scripts/validate_clean_install.py` passed against the live environment: 79 core, 6 Credits, and 1
code-app components; 18 required tables; 4 roles; 7 workflows; 5 connection references; 3 Custom
APIs; and one target-generated active managed Code App record. Source app IDs are not portable.
Always use the target-generated app ID and open URI emitted by the validator.

Normal Power Apps launch no longer returned HTTP 403
`CodeAppOperationNotAllowedInEnvironment`. The exact `powerplatformusercontent` runtime document
returned HTTP 200 and rendered Sessions, Trends, Inventory, and Credits. This proves launch
authorization and runtime asset delivery, not authenticated connector/data behavior. A direct
runtime URL lacks the parent Power Apps host token and stays at Loading for data access.

The shared VS Code browser aborted the cross-origin Power Apps host iframe with
`net::ERR_ABORTED`, leaving `fullscreen-app-host` hidden at `about:blank`. The same behavior
reproduced against a previously healthy app, isolating it to that shared browser session. Record
this as a browser-validation limitation, not a package or installation failure. The accepted result
for installation is the successful ordered managed imports plus structural validator success.
Launch authorization/runtime asset delivery passed as a separate gate. Authenticated functional smoke remains an independent gate
that the shared-browser limitation prevented from passing; this result does not claim a full fresh
authenticated data-tab smoke.

## Policy matrix

| Category | Requirement | Decision rule |
| --- | --- | --- |
| Mandatory for the optional code app | **Enable code apps** | Set **On**, save, and independently reload before importing the code-app package. Microsoft documents the default as **Off**. |
| Mandatory for the optional code app | Managed Environment group rule 22 | If the target is a Managed Environment in an environment group, the group's **Power Apps code apps** rule must be enabled and published so its effective state allows code apps. |
| Mandatory for the optional code app | Runner license | Every intended runner needs Power Apps Premium. |
| Mandatory for the optional code app | Sharing and data roles | Share the target-generated app with the intended users/groups and assign an appropriate packaged Dataverse role, normally **PVCI Analyst**. App sharing alone does not grant table access. |
| Mandatory for package/configuration | Dataverse readiness | Wait until the new environment has a ready Dataverse organization before authentication or import. |
| Mandatory for package/configuration | Import authority | The importer holds **System Administrator** in the target Dataverse environment during import and configuration. Remove temporary elevation according to local policy afterward. |
| Mandatory for package/configuration | Clean-install order | Import core first, optional Credits second, and optional code app last. Use the exact immutable candidate bytes and verify their SHA-256 hashes before import. |
| Mandatory for package/configuration | Target-local configuration | Create and map physical connections for every installed feature. If Credits is installed, set `pvci_CreditReportingTenantId` to the target tenant. Neither credentials nor current values are portable package content. |
| Mandatory for package/configuration | Flow activation | Keep packaged flows stopped until connection mappings, environment values, role assignments, and manual smoke tests pass. |
| Conditional governance | DLP and Advanced Connector Policies | For installed features, compatible connector groups must allow Microsoft Dataverse, **HTTP with Microsoft Entra ID (preauthorized)**, and **Power Platform for Admins V2**. Omitted optional features do not require their connectors. |
| Conditional governance | App quarantine | The target-generated app must not be quarantined for intended end users. |
| Conditional governance | App-level Conditional Access | Any policy assigned to the app must permit the intended user, device, and location. |
| Conditional governance | Tenant isolation | Evaluate only when the app or connector reaches external, B2B, or cross-tenant resources. Same-tenant Dataverse-only use does not require a tenant-isolation exception. |
| Conditional governance | App access control | This is separate from Code Apps enablement. A denied app has the distinct message `Access to the Dataverse API is restricted for this application ID.` |
| Conditional governance | Sharing limits | Managed Environment sharing limits can restrict who receives the app; they do not block managed package import. |
| Conditional governance | Content security policy | Configure explicit origins only when the code app uses external origins or resources. The packaged same-tenant Dataverse experience does not require an invented external allowlist. |
| Conditional governance | IP restriction | Code Apps ignore Storage SAS IP restriction. Use Microsoft Entra Conditional Access location policies when runner access must be IP/location restricted. |

Power Platform DLP documentation says policy changes take effect within an hour in most cases and
can require up to 24 hours in the most extreme cases. That is DLP guidance only. Microsoft does not
publish a propagation interval for **Enable code apps**, so do not apply the DLP SLA to that toggle;
save and independently reload its effective state before import.

## Create and confirm the target

Authenticate only to the repository's authorized development/test tenant. Verify the authenticated
tenant ID, target environment ID, and target URL independently before every write. Tenant names,
account domains, PAC profile aliases, and URL labels are not authorization evidence. Never automate
imports into the TPM manual-upgrade tenant.

Create a Sandbox synchronously. Do not pass `--user`: current PAC behavior supports that creation
option only for Developer environments, and it must not be used for Sandbox validation.

```powershell
pac admin create `
  --name "<disposable-environment-name>" `
  --type Sandbox `
  --domain "<unique-domain>" `
  --region "<region>" `
  --currency "<currency>"

pac admin list --type Sandbox
pac auth create --environment "<https://target.crmN.dynamics.com>"
pac org who
```

Wait for Dataverse to report Ready. Confirm the authenticated tenant ID is the authorized tenant
before continuing.

## Mandatory Code Apps preflight

When the optional code app will be installed, complete this before importing any solution:

1. In Power Platform admin center, open **Manage** > **Environments** > the exact target >
   **Settings** > **Product** > **Features** > **Power Apps Code Apps**.
2. Set **Enable code apps** to **On** and select **Save**.
3. Leave or reload the settings page independently. Continue only when the same target still shows
   On and Save is disabled.
4. If the target is a Managed Environment in a group, confirm rule 22, **Power Apps code apps**, is
   enabled and published for that group. The group-effective state must allow the feature.

The supported UI is the primary verification path. As an optional independent read, use the preview
[Power Platform Environment Management Settings API](https://learn.microsoft.com/rest/api/power-platform/environmentmanagement/environment-management-settings/list-environment-management-settings?view=power-platform-latest):

```http
GET https://api.powerplatform.com/environmentmanagement/environments/{environmentId}/settings?$select=powerApps_AllowCodeApps&api-version=2024-10-01
```

The delegated read scope is `EnvironmentManagement.Settings.Read`; mutation requires
`EnvironmentManagement.Settings.ReadWrite`. The response must show `powerApps_AllowCodeApps: true`.
Do not add API mutation to this repository workflow merely to bypass the supported UI preflight.

## Hash and import exact packages

Use the exact candidate paths supplied by the Release Maintainer. Record hashes in temporary
evidence, compare them with the candidate manifest, and do not add target-specific hashes to the
clean-install contract.

```powershell
$EnvironmentUrl = "<https://target.crmN.dynamics.com>"
$Core = "<path-to-core-candidate.zip>"
$Credits = "<path-to-credits-candidate.zip>"
$CodeApp = "<path-to-code-app-candidate.zip>"

Get-FileHash -Algorithm SHA256 $Core, $Credits, $CodeApp

# No --async: each import completes before the next one starts.
pac solution import --environment $EnvironmentUrl --path $Core
pac solution import --environment $EnvironmentUrl --path $Credits
pac solution import --environment $EnvironmentUrl --path $CodeApp
```

Credits and code app are optional, but the relative order of installed packages is fixed. Do not
add `--activate-plugins` to the recommended deterministic package-import command. PAC documents that
flag as activating plug-ins and workflows, while fresh-import configuration requires packaged flows
to remain stopped until target-local mappings and smoke tests pass. This is the recommended command
going forward, not a claim about which flags were used in the 2026-08-28 proof.

An `OpenApiOverrideConnectionInvalidPlaceholderConnection` warning or a prompt to create
connections is expected when no target-local physical connection exists. Preserve the warning,
confirm the import itself succeeded, and complete mappings after structural validation. A failed
solution import is still a failure and must not be relabeled as setup-required.

## Structural validation and configuration

Run the offline contract tests first, then the live validator against the exact target:

```powershell
python scripts/test_validate_clean_install.py
python scripts/validate_clean_install.py `
  --environment-url $EnvironmentUrl `
  --contract config/clean-install-contract.json `
  --config config/transcript_solution_config.dev.json
```

The live command validates the three managed identities and configured versions, contract-driven
tables, roles, workflows, connection references and Custom APIs, and one active managed Code App
component. Its JSON output is the source of truth for the target-generated `canvasappid` and
`appopenuri`; never reuse the source environment's app ID.

After structure passes:

1. Create and map target-local Dataverse, Power Platform for Admins V2, and licensing connections
   required by the packages actually installed.
2. Set `pvci_CreditReportingTenantId` when Credits is installed.
3. Share the apps and assign packaged Dataverse roles.
4. Keep every flow stopped while running its documented manual connection and no-op/data smoke.
5. Activate only flows whose mappings and smoke tests pass.

## Hosted browser smoke

Use the existing shared VS Code browser page. Run navigation, launch, and view checks sequentially;
parallel operations against one shared page race the host and invalidate observations.

1. Open the target-generated `appopenuri` through normal Power Apps launch.
2. Fail launch authorization if the host returns
   `CodeAppOperationNotAllowedInEnvironment`.
3. Record launch authorization/runtime delivery as a gate separate from installation acceptance.
4. For the independent authenticated functional smoke gate, confirm the parent-hosted app renders
   Sessions, Trends, Inventory, and Credits.
5. Validate authenticated Dataverse behavior only while the app is inside its parent Power Apps
   host and has the host token.
6. Use the exact `powerplatformusercontent` runtime URL only to diagnose document/asset delivery.
   HTTP 200 or rendered shell content there is not authenticated connector/data smoke.

If the shared browser aborts the cross-origin host iframe and the same signature reproduces against
a known healthy app, record the shared-browser limitation precisely. Do not convert that limitation
into a package failure or claim full authenticated data smoke.

## Troubleshooting launch authorization

For HTTP 403 `CodeAppOperationNotAllowedInEnvironment`:

1. Confirm the browser, PAC profile, and settings page all target the exact new environment.
2. Confirm **Enable code apps** was saved and independently reloaded as On before code-app import.
3. If the environment is managed and grouped, confirm group rule 22 is effective and published.
4. Resolve and launch the target-generated app ID/open URI from the live validator, never the source
   app ID.
5. If effective state is On and 403 persists, preserve request/correlation evidence and escalate to
   Microsoft support. Microsoft documents no propagation wait for this toggle.

Keep other signatures distinct:

- `Access to the Dataverse API is restricted for this application ID.` is app access control.
- A quarantine message is app quarantine.
- A connector policy or blocked-connector message is DLP/ACP, whose propagation guidance differs.
- `net::ERR_ABORTED` with a hidden `about:blank` host, when reproduced on a healthy app, is a shared
  browser-session limitation.
- A direct runtime stuck at Loading is expected without the parent host token.

## Evidence and cleanup

Capture the environment identity, preflight save/reload evidence, candidate filenames and hashes,
ordered import results and warnings, validator JSON, target-generated app identity, hosted launch
result, runtime asset status, and any shared-browser limitation in temporary release evidence. Do
not commit tenant IDs, environment IDs, temporary URLs, app IDs, hashes, or account names into the
contract.

Hand the evidence to the Release Maintainer, which remains the single owner of release status,
roadmap, public page, and evidence mutations. Candidate validation alone does not change shipped
`CHANGELOG.md` history, public downloads, stable release manifest, or stable artifact bytes.

Always delete the disposable environment after the Release Maintainer reviews the evidence, even
when validation fails:

```powershell
pac admin delete --environment "<environment-id-or-url>"
```

Successful deletion output and successful PAC polling confirm that the delete request was accepted,
not that deletion is complete. Cleanup is complete only when both checks pass:

1. `pac admin list` no longer returns the target in tenant inventory.
2. `pac org who --environment "<target-url>"` no longer reaches target Dataverse.

Until then, leave the environment marked `deletion-in-progress`. After a successful delete request,
`OperationNotStartable` with `canInitiateDelete:false` and an active lifecycle operation means the
existing cleanup is still converging; it is not a reason to start a second delete. `pac admin status`
reporting no async operations is not authoritative for this lifecycle convergence. Do not loop,
aggressively poll, repeat the delete, or issue concurrent deletes. Perform one later verification
and keep the environment marked `deletion-in-progress` until both completion criteria pass.

Cleanup for the still-live 2026-08-28 retry is intentionally owned by the coordinating main agent,
not this documentation change.

## Microsoft references

- [Power Apps code apps overview and prerequisites](https://learn.microsoft.com/power-apps/developer/code-apps/overview)
- [Code Apps feedback and standard Microsoft Support paths](https://learn.microsoft.com/power-apps/developer/code-apps/feedback-support)
- [Power Apps Code Apps environment setting and default](https://learn.microsoft.com/power-platform/admin/settings-features#power-apps-code-apps)
- [Environment group rules, including rule 22](https://learn.microsoft.com/power-platform/admin/environment-groups-rules)
- [Environment Management Settings API](https://learn.microsoft.com/rest/api/power-platform/environmentmanagement/environment-management-settings/list-environment-management-settings?view=power-platform-latest)
- [Power Platform API permissions](https://learn.microsoft.com/power-platform/admin/programmability-permission-reference)
- [Code Apps architecture and Power Apps host](https://learn.microsoft.com/power-apps/developer/code-apps/architecture)
- [Code Apps ALM](https://learn.microsoft.com/power-apps/developer/code-apps/how-to/alm)
- [Power Platform DLP latency](https://learn.microsoft.com/power-platform/admin/wp-data-loss-prevention#latency-considerations)
- [Managed Environment sharing limits](https://learn.microsoft.com/power-platform/admin/managed-environment-sharing-limits)
- [App quarantine and app-level Conditional Access](https://learn.microsoft.com/power-platform/admin/admin-manage-apps)
- [App access control and its denied-user signature](https://learn.microsoft.com/power-platform/admin/control-app-access-environment)
- [Tenant isolation](https://learn.microsoft.com/power-platform/admin/cross-tenant-restrictions)
- [Content security policy](https://learn.microsoft.com/power-platform/admin/content-security-policy)
- [PAC admin commands](https://learn.microsoft.com/power-platform/developer/cli/reference/admin)
- [PAC solution import](https://learn.microsoft.com/power-platform/developer/cli/reference/solution#pac-solution-import)
