# Conversation Insights Explorer code app

This React/Vite Power Apps code app is the optional supported investigation surface for MCS
Transcript Analyzer. It is supported by the project maintainer and built on fully supported
Microsoft technologies. It provides Sessions, Trends, Operations, Inventory, and Credits
workspaces over the Dataverse schema owned by the required `pvConversationInsights` core solution.
Operations consolidates configuration readiness, health, retained run evidence, failure streaks,
duration changes, pending request counts, filters, optional auto-refresh, and payload-free diagnostic
copy for all seven packaged flows. It does not own backend runtime, tables, flows, plugins, roles, or
Custom APIs, and it cannot directly start the current recurrence-only flows.

Inventory includes separate **Environments** and **Agents** views. The Agents view groups tenant
discoveries by environment, keeps authorship evidence independent from managed deployment, and shows
exact or candidate collected-session evidence only where transcript collection is currently
available. Environment-scoped display-name matches are always labeled candidate or ambiguous, never
exact. Each visible session can open its full retained Sessions workspace record. The inventory
session view is bounded to the 2,000 most recent retained sessions.

Sessions attributed exactly to `msdyn_copilotforemployeeselfservicehr` or its Workday topic prefix
are masked by default across the session navigator, overview, replay, diagnostics, and JSON views.
The app can download a fresh masked JSON bundle independently of the current filter or reveal state.
Reveal is fail-closed and available only when the current Dataverse user has a direct assignment to
a business-unit copy of the packaged **PVCI Privacy Approver** role. Team-inherited assignments are
not resolved by this version and remain masked. This UI safeguard reduces accidental disclosure; it
does not revoke direct Dataverse/API access to stored raw payload columns.

## Prerequisites

- Node.js 22 and npm.
- Current Power Apps CLI and a Power Platform environment with Dataverse.
- The required core solution installed; install the optional Credits add-on for live credit runtime.
- **Power Apps Code Apps > Enable code apps** saved and independently reloaded as **On** before a
  fresh code-app solution import. It defaults Off.
- Power Apps Premium for every runner.
- App sharing plus an appropriate packaged Dataverse role, normally **PVCI Analyst**.
- **PVCI Privacy Approver** for users authorized to reveal ESS HR Workday PII in the session UI.

If the target is a Managed Environment in an environment group, the effective and published group
rule 23, **Power Apps code apps**, can centrally enable and lock the feature. See the authoritative
[clean-install runbook](../docs/clean-install.md) for the complete mandatory and conditional policy
matrix.

## Local development

Install exactly the lockfile dependency graph and run the normal checks:

```powershell
npm ci
npm run dev
npm test
npm run lint
npm run build
```

Copy `power.config.sample.json` to the ignored target-specific `power.config.json`, then initialize
or add Dataverse sources through the Power Apps CLI. Never commit target environment IDs, app IDs,
open URIs, physical connection IDs, or credentials.

Local Vite rendering validates frontend behavior but does not reproduce the parent Power Apps host
token. Connector/data validation must use the normally hosted app.

## ALM and package ownership

`pvConversationInsightsCodeApp` contains only the code-app component and declared core table
dependencies. The separate solution supports optional installation and an independent application
lifecycle. Microsoft documents solution portability, CI/CD, and Power Platform Pipelines for
development, test, and production environments in the
[Code Apps ALM guidance](https://learn.microsoft.com/power-apps/developer/code-apps/how-to/alm).
Candidate versions and filenames come from
[`config/release-packages.json`](../config/release-packages.json). Candidate ZIPs stay under
`output/candidate/` until all target-tenant and release gates pass; never overwrite a published ZIP
at an existing version.

The current mixed stable set is core `2.1.0.0`, unchanged Credits `2.0.0.5`, and Code App
`2.2.0.3`; the overall stable identity and Git tag remain `v2.1.0.0`. Existing code-app users should
upgrade only the Code App to `2.2.0.3` for this code-app-only update.

For a fresh install:

1. Enable Code Apps in the exact target before any import.
2. Import core `pvConversationInsights-managed-2.1.0.0.zip`.
3. Import optional Credits `pvConversationInsightsCredits-managed-2.0.0.5.zip`.
4. Import `pvConversationInsightsCodeApp-managed-2.2.0.3.zip` last.

Source app IDs are not portable. Resolve the target-generated managed Code App row and open URI
with `scripts/validate_clean_install.py`; do not launch a source environment ID in the target.

## Fresh-install validation

Run the offline tests, then the live structural check:

```powershell
python scripts/test_validate_clean_install.py
python scripts/validate_clean_install.py `
  --environment-url "<https://target.crmN.dynamics.com>" `
  --contract config/clean-install-contract.json
```

Use one shared VS Code browser page and perform hosted checks sequentially. A direct
`powerplatformusercontent` runtime URL is diagnostic only because it lacks the parent host token;
HTTP 200 there is not authenticated connector/data smoke.

## Policy and troubleshooting

Code Apps follow DLP, Advanced Connector Policies, app quarantine, app-level Conditional Access,
tenant isolation where cross-tenant resources are used, app access control, sharing limits, and CSP
for external origins. Code Apps ignore Storage SAS IP restriction; use Entra Conditional Access for
location restrictions.

Current documented platform limitations include no Power Platform Git integration, no Power Apps
for Windows support, no `PowerBIIntegration`, no SharePoint forms integration, and public asset
delivery that requires Conditional Access for IP/location controls. See the Microsoft
[Code Apps overview](https://learn.microsoft.com/power-apps/developer/code-apps/overview) and
[feedback and support guidance](https://learn.microsoft.com/power-apps/developer/code-apps/feedback-support).
Documented SDK/CLI mismatches and regressions use standard Microsoft Support; project-specific
support remains with this repository's maintainer.

For `CodeAppOperationNotAllowedInEnvironment`, confirm the exact target, independently reload
**Enable code apps** as On, confirm any effective group rule is published, and use the
target-generated app ID. `Access to the Dataverse API is restricted for this application ID.` is a
separate app access-control failure.

Operational details, Microsoft references, evidence criteria, and disposable-environment cleanup
are maintained in [docs/clean-install.md](../docs/clean-install.md).
