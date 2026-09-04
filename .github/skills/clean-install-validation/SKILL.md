---
name: clean-install-validation
description: "Create, install, and validate MCS Transcript Analyzer in a fresh disposable Dataverse environment. Use when testing clean install, fresh Sandbox import, Code Apps enablement, CodeAppOperationNotAllowedInEnvironment, target-generated app IDs, candidate package order, or clean-install evidence and cleanup."
argument-hint: "Describe the candidate artifacts and disposable target environment"
---

# Clean Install Validation

Use this deterministic workflow for a from-scratch candidate install. The authoritative operator
procedure is [`docs/clean-install.md`](../../../docs/clean-install.md), and machine requirements are
in [`config/clean-install-contract.json`](../../../config/clean-install-contract.json). Do not
create another custom agent for this workflow: all steps use the same safety and evidence boundary,
while the existing Release Maintainer remains the single release/status mutation owner.

## 1. Confirm tenant, target, and artifact boundaries

Before every write, verify the authenticated tenant ID is exactly the development/test tenant
authorized by `.github/instructions/solution-boundaries.instructions.md`. Never infer authorization
from an environment name, URL label, account domain, or PAC profile alias. Never automate imports,
configuration, or cleanup in the TPM manual-upgrade tenant.

Confirm that the target is a new disposable Sandbox with Dataverse and that its environment ID and
URL agree across `pac admin list`, `pac org who`, PPAC, and the planned browser launch. Preserve
published ZIPs, `site/downloads/`, the stable manifest, `CHANGELOG.md`, and release evidence while
validating candidates.

Create a Sandbox without `pac admin create --user`; that parameter is Developer-only in this
workflow and must not be used for Sandbox creation. Wait synchronously for Dataverse Ready.

## 2. Complete mandatory preflight before imports

If the optional code app will be imported, do this before importing any package:

Use one supported enablement path:

1. Direct: in PPAC, open **Manage** > **Environments** > exact target > **Settings** > **Product** >
  **Features** > **Power Apps Code Apps**, set **Enable code apps** On, and save; or
2. Group: add the managed target to a validation environment group whose published rule 23,
  **Power Apps code apps**, is configured On. Published group rules enforce and lock the setting.

Then run the mandatory read-only effective-state check:

```text
python scripts/validate_clean_install.py --preflight-only --environment-id <target-guid> --config <authorized-config>
```

The command gets a Power Platform token from the selected PAC profile, validates the authorized
tenant claim, queries the exact environment ID, and requires `powerApps_AllowCodeApps: true` through
the Environment Management Settings API. Do not import any package when this check fails. API
mutation requires `EnvironmentManagement.Settings.ReadWrite`; the repository preflight is read-only.

Also confirm Dataverse Ready, importer System Administrator, Power Apps Premium for intended code
app runners, packaged app sharing/Dataverse role plans, and applicable group governance.

## 3. Evaluate policy by category

Mandatory package/configuration checks are Dataverse readiness, authorized System Administrator,
exact package order, target-local connection mappings, the Credits tenant variable when Credits is
installed, and stopped flows until mappings and manual smokes pass.

Conditional checks apply only when target policy or installed features require them: DLP and ACP
connector grouping, app quarantine, app-level Conditional Access, tenant isolation for
external/B2B/cross-tenant resources, app access control, sharing limits, CSP for external origins,
and location restriction. Code Apps ignore Storage SAS IP restriction; use Entra Conditional Access
for IP/location policy.

Do not apply DLP timing to Enable code apps. Microsoft says DLP changes take effect within an hour
in most cases and can take 24 hours in extreme cases; Microsoft publishes no propagation interval
for the Code Apps toggle.

## 4. Hash and import synchronously

Read package order and versions from `config/release-packages.json`, then compare the candidate
files with their candidate manifest using SHA-256. Never calculate a new hash as authority and
never overwrite a package at an existing version.

For a fresh install, import exact immutable bytes in this order:

1. `core` (required)
2. `credits` (optional)
3. `codeApp` (optional)

Run `pac solution import` without `--async` and wait for each import to finish before starting the
next. The recommended deterministic package-import command omits `--activate-plugins`: PAC
documents that flag as activating plug-ins and workflows, while fresh-import configuration requires
packaged flows to remain stopped until target-local mappings and smokes pass. Treat this as the
prescribed command, not as a claim about which flags were used in historical proof runs.

Preserve import warnings. `OpenApiOverrideConnectionInvalidPlaceholderConnection` and Credits
connection-creation warnings mean physical target connections remain setup-required when the
solution import succeeds. They are not package failures, and they are not permission to start
flows with unresolved mappings.

## 5. Run structural validation

Run:

```powershell
python scripts/test_validate_clean_install.py
python scripts/validate_clean_install.py `
  --environment-url "<target-url>" `
  --contract config/clean-install-contract.json
```

The script retains the repository's authorized-config and access-token tenant checks. Require all
configured managed solution identities/versions, contract-driven tables, roles, workflows,
connection references and Custom APIs, plus exactly one active managed Code App component.

Use the validator's `codeApp.canvasappid` and `codeApp.appopenuri` for the target. Source app IDs and
source open URIs are not portable.

## 6. Configure, then smoke sequentially

Create and map target-local physical connections, set `pvci_CreditReportingTenantId` when Credits
is installed, assign packaged roles, and share the target-generated apps. Keep flows stopped until
their mappings and manual smoke tests pass.

Reuse one already shared VS Code built-in browser page. Run all launch, navigation, responsive, and
screenshot operations sequentially. Never issue parallel browser operations against one shared
page; they race the Power Apps host and invalidate evidence.

Launch through normal Power Apps using the target-generated open URI. Success requires no
`CodeAppOperationNotAllowedInEnvironment`; runtime delivery additionally requires the exact runtime
document and packaged shell assets. This launch authorization/runtime delivery proof is independent
of installation acceptance. Authenticated functional smoke is another independent gate: it requires
parent-host rendering of Sessions, Trends, Inventory, and Credits plus authenticated connector/data
behavior through the parent Power Apps host token.

An exact `powerplatformusercontent` runtime URL is diagnostic only. HTTP 200 and rendered shell
assets prove runtime delivery, not authenticated connector/data behavior; never treat direct
runtime loading as authenticated smoke.

## 7. Classify failure signatures

- `CodeAppOperationNotAllowedInEnvironment`: exact-target effective Code Apps setting or group rule;
  rerun the API preflight, verify published rule 23 and the target-generated app ID, then
  escalate to Microsoft support if effective state is On and 403 persists.
- `Access to the Dataverse API is restricted for this application ID.`: app access control, not the
  Code Apps environment toggle.
- Quarantine message: app quarantine.
- Connector-policy violation: DLP/ACP; preserve connector/group details and observe DLP-specific
  propagation guidance.
- `OpenApiOverrideConnectionInvalidPlaceholderConnection`: successful import can still need
  target-local physical connections.
- `net::ERR_ABORTED` with hidden `fullscreen-app-host` at `about:blank`, reproduced against a known
  healthy app: shared-browser limitation, not package failure.
- Direct runtime remains Loading: expected when the parent host token is absent.

Do not claim a full authenticated data-tab smoke from launch authorization, runtime HTTP 200, or a
direct-runtime render.

## 8. Capture evidence and always clean up

Capture candidate filenames/hashes/order, target and tenant confirmation, preflight save/reload,
import results/warnings, validator JSON, target-generated app output, hosted launch/runtime results,
and browser limitations. Keep target-specific IDs, URLs, hashes, and account names out of the
committed clean-install contract.

Always delete the disposable environment after evidence review, including after failed validation.
Use a `finally`-style operational plan so cleanup is not skipped when an earlier step fails. When a
coordinating agent explicitly owns cleanup, leave the environment intact and record that owner.

A successful `pac admin delete` message and successful polling mean the delete request was accepted;
they do not prove deletion is complete. Keep the environment marked `deletion-in-progress` until
both the target is absent from `pac admin list` tenant inventory and `pac org who --environment
<target-url>` no longer reaches target Dataverse. If a second delete attempt after the accepted
request returns `OperationNotStartable` with `canInitiateDelete:false` because an active lifecycle
operation is running, cleanup is still converging; do not start another delete. `pac admin status`
reporting no async operations is not authoritative for this lifecycle convergence. Do not loop,
aggressively poll, repeat the delete, or issue concurrent deletes. Perform one later verification
and leave cleanup as `deletion-in-progress` until both completion criteria pass.

## Release Maintainer handoff

Return evidence to the existing Release Maintainer. It alone updates candidate status,
`ROADMAP.md`, public site text, documentation contracts/digest, and release evidence. A deterministic
skill is appropriate here because the procedure needs no separate context or mutation owner; a new
custom agent would create competing ownership over release files.

Report package validation, target-tenant structural/hosted validation, browser limitations, and
cleanup as separate outcomes. Do not promote candidates or change shipped history unless the
applicable release gates independently pass.