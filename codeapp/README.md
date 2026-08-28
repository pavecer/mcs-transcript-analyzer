# Conversation Insights Explorer code app

This React/Vite Power Apps code app is the optional unsupported preview surface for MCS Transcript
Analyzer. It provides Sessions, Trends, Inventory, and Credits workspaces over the Dataverse schema
owned by the required `pvConversationInsights` core solution. It does not own backend runtime,
tables, flows, plugins, roles, or Custom APIs.

## Prerequisites

- Node.js 22 and npm.
- Current Power Apps CLI and a Power Platform environment with Dataverse.
- The required core solution installed; install the optional Credits add-on for live credit runtime.
- **Power Apps Code Apps > Enable code apps** saved and independently reloaded as **On** before a
  fresh code-app solution import. It defaults Off.
- Power Apps Premium for every runner.
- App sharing plus an appropriate packaged Dataverse role, normally **PVCI Analyst**.

If the target is a Managed Environment in an environment group, the effective and published group
rule 22, **Power Apps code apps**, must also allow the feature. See the authoritative
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
dependencies. Candidate versions and filenames come from
[`config/release-packages.json`](../config/release-packages.json). Candidate ZIPs stay under
`output/candidate/` until all target-tenant and release gates pass; never overwrite a published ZIP
at an existing version.

For a fresh install:

1. Enable Code Apps in the exact target before any import.
2. Import core.
3. Import optional Credits.
4. Import the code-app package last.

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

For `CodeAppOperationNotAllowedInEnvironment`, confirm the exact target, independently reload
**Enable code apps** as On, confirm any effective group rule is published, and use the
target-generated app ID. `Access to the Dataverse API is restricted for this application ID.` is a
separate app access-control failure.

Operational details, Microsoft references, evidence criteria, and disposable-environment cleanup
are maintained in [docs/clean-install.md](../docs/clean-install.md).
