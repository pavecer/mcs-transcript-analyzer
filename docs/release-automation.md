# Daily release package automation

The public site publishes two independent managed Power Platform solutions:

| Package | Solution | Support status | Import order |
| --- | --- | --- | --- |
| Core | `pvConversationInsights` | Supported model-driven experience | First |
| Code app | `pvConversationInsightsCodeApp` | Power Apps code-app preview, unsupported | Second |

The code app stays separate so environments can use the supported model-driven app without
enabling preview technology. Its managed solution depends on the 14 core Dataverse tables used by
the transcript, flow, inventory, governance, credit, capacity, privacy, and sync experiences.

## Automation design

`.github/workflows/refresh-packages.yml` runs daily at 03:17 UTC and can also be started
manually. It uses the following sequence:

1. Find the newest commit that changed deployable inputs under `codeapp/`, `plugin/`, `pcf/`,
   `solution/`, or `scripts/transcript_insights/`.
2. Compare that commit with `sourceCommit` in `site/downloads/release-manifest.json`.
3. Exit successfully without touching Power Platform when the commits match.
4. Authenticate to Power Platform by GitHub OIDC. There is no client secret.
5. Build the committed code app and deploy it to `pvConversationInsightsCodeApp`.
6. Export both source solutions as managed ZIPs.
7. Verify solution identity, version, managed state, embedded JSON Viewer PCF, embedded code app,
   ZIP integrity, and SHA-256 hashes.
8. Commit only `site/downloads/`. The existing Pages workflow publishes that commit.

Failures stop before the artifact commit. The previously validated downloads remain live.

## Issue candidate releases

Backward-compatible fixes can be tested by affected tenants before the next public release. Run
the **publish issue candidate** workflow manually with a candidate version such as `1.3.1.0` and
the issue number. `.github/workflows/candidate-release.yml` runs the focused governance tests,
builds the managed candidate through `scripts/build_candidate_package.py`, then creates the
prerelease `v1.3.1.0-rc.1` and comments the direct ZIP URL on the issue.

The candidate builder starts from the immutable public managed package and overlays only the
reviewed source workflow definitions. This is intentional: Dataverse does not allow exporting a
managed solution from a managed target environment. The GitHub prerelease asset is the package
distributed to affected testers. The user imports and upgrades it manually in TPM; automation must
not authenticate to or write to TPM. Never overwrite the stable `1.3.0.0` ZIP. After manual
validation, promote the same fix through the normal versioned release process.

## Release documentation gate

Product behavior and public documentation are coupled through
`config/documentation-contract.json`. The contract inventories release-facing Markdown/HTML
surfaces, records product inputs that define Copilot Credit behavior, derives component counts from
the solution contracts, and requires capability evidence on the appropriate surfaces.

Run both gates before release:

```bash
python3 scripts/validate_documentation.py
python3 scripts/validate_site.py
```

If a listed product input changes, the documentation validator fails until every indexed surface
has been reviewed. After the review, run `python3 scripts/validate_documentation.py --print-digest`
and update `productSourceDigest` in the contract. Do not update the digest merely to make CI green.

Agents should load the checked-in `.github/skills/release-documentation/SKILL.md` workflow for
README, docs, release-package, or public Pages changes. The skill is guidance; the CI `site` job and
Pages workflow run the deterministic gate and are the enforcement boundary.

## Important deployment boundary

Programmatic Power Platform and Dataverse writes are allowed only when the authenticated tenant ID
is `1938ee32-a258-454c-b8db-3a928341bd69`. The TPM tenant is reserved for manual solution upgrade
testing. Automation may build packages and perform read-only checks for TPM, but the user performs
all imports, publishes, connection mappings, and other changes there. Tenant and environment names,
URLs, account domains, and PAC profile aliases are not authorization boundaries.

The workflow deploys the code app because `pac code push` supports deterministic solution
targeting under the same PAC authentication used for export.

The core deployment remains a developer operation. Its schema provisioners, Python parser,
PCF push, plugin registration, forms, views, and flow creation use several deployment paths and
aren't yet unified under the release service principal. Before committing core changes that
should be packaged, deploy and verify them in PVE Dev. The daily workflow then exports the live,
tested source solution.

This boundary prevents an unattended schedule from changing Dataverse schema, plugin execution,
or production-like data processing merely because a commit landed on `main`.

## One-time GitHub OIDC setup

Create a single-tenant Entra application and service principal. Add a federated credential with:

| Setting | Value |
| --- | --- |
| Issuer | `https://token.actions.githubusercontent.com` |
| Subject | `repo:pavecer@37548236/mcs-transcript-analyzer@1319587093:ref:refs/heads/main` |
| Audience | `api://AzureADTokenExchange` |

No client secret is required or permitted for this workflow. Example Azure CLI sequence:

```bash
tenant_id="<tenant-id>"
app_name="mcs-transcript-analyzer-release"

az login --tenant "$tenant_id"
app_id=$(az ad app list --display-name "$app_name" --query '[0].appId' -o tsv)
if [[ -z "$app_id" ]]; then
  app_id=$(az ad app create \
    --display-name "$app_name" \
    --sign-in-audience AzureADMyOrg \
    --query appId -o tsv)
fi
az ad sp create --id "$app_id"
app_object_id=$(az ad app show --id "$app_id" --query id -o tsv)
az ad app federated-credential create --id "$app_object_id" --parameters @- <<'JSON'
{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:pavecer@37548236/mcs-transcript-analyzer@1319587093:ref:refs/heads/main",
  "description": "Daily managed solution packaging from main",
  "audiences": ["api://AzureADTokenExchange"]
}
JSON
echo "$app_id"
```

Create the corresponding Dataverse application user in PVE Dev and assign **System Customizer**.
This is broad enough for code-app deployment and solution export but does not grant System
Administrator. Review the role periodically and replace it with a tested custom role when the
exact code-app deployment privileges are stable.

```bash
pac admin assign-user \
  --environment "<dataverse-url>" \
  --user "$app_id" \
  --application-user \
  --role "System Customizer"
```

Configure these repository **Actions variables** (not secrets):

| Variable | Value |
| --- | --- |
| `POWER_PLATFORM_CLIENT_ID` | Entra application/client ID |
| `POWER_PLATFORM_TENANT_ID` | Entra tenant ID |
| `POWER_PLATFORM_ENVIRONMENT_ID` | Power Platform environment GUID |
| `POWER_PLATFORM_ENVIRONMENT_URL` | Dataverse organization URL |

The workflow has `id-token: write` solely to request the short-lived federated token and
`contents: write` solely to commit generated package files.

## Normal release flow

1. Deploy and verify core changes in PVE Dev when the core solution changed.
2. Commit source changes to `main`.
3. Wait for the next daily run, or start **refresh release packages** manually with `force=true`.
4. Confirm the generated artifact commit and Pages deployment succeeded.
5. Download both public ZIPs and verify their hashes against `release-manifest.json`.
6. Before a versioned release, import core and then code app into a clean sandbox.

For an identity/export smoke test that must not deploy code-app source, run manually with
`force=true` and `export_only=true`. Scheduled runs always deploy the committed code app before
exporting.

## Version changes

The core and code-app packages use one synchronized four-part release train:

| Change | Version example | Use |
| --- | --- | --- |
| Breaking install or migration change | `2.0.0.0` | Existing consumers need explicit migration work |
| Backward-compatible feature | `1.1.0.0` | New tables, APIs, flows, app capabilities, or dependencies |
| Backward-compatible fix | `1.1.1.0` | Correct behavior without adding a feature surface |
| Rebuilt release artifact only | `1.1.1.1` | Packaging-only correction with unchanged solution behavior |

Every published package must have a version greater than the previous package. Never replace a
published ZIP while keeping its version: Power Platform upgrade detection and administrator audit
trails depend on the version being immutable.

For every version change:

1. Update both live Dataverse solutions in PVE Dev with `pac solution online-version`.
2. Update the core source versions in `solution-definition.json` and `src/Other/Solution.xml`.
3. Update both package versions, filenames, and the code-app core-table dependency contract in
  `config/release-packages.json`.
4. Update the public page's version and install content.
5. Review all indexed documentation surfaces, update the documentation digest when product inputs
  changed, and run `scripts/validate_documentation.py`.
6. Export both managed ZIPs, regenerate `release-manifest.json`, and run
  `scripts/validate_site.py`.
7. Import core first and code app second into a clean sandbox. For an existing installation,
  confirm both imports are recognized as upgrades and retained data remains available.
8. Publish through a pull request. Confirm CI, the refresh workflow, Pages deployment, public
  manifest versions and hashes, and both public downloads.

The release validator rejects filename/version drift, unsynchronized core source versions,
unexpected code-app dependencies, stale manifests, and packages exported from a live solution
whose version does not match the repository contract.

## Recovery

- **No changes detected:** expected; no authentication or export occurs.
- **OIDC failure:** verify the branch subject, tenant/client variables, and that the federated
  credential audience is `api://AzureADTokenExchange`.
- **Code-app push failure:** no ZIPs are committed; fix the app or permissions and force-run.
- **Export validation failure:** inspect the source solution membership. Do not bypass the
  validator or manually replace only one ZIP.
- **Bad published package:** revert the generated artifact commit. Pages restores both previous
  validated downloads together.

## Current status

- Dedicated preview solution created in PVE Dev: `pvConversationInsightsCodeApp`.
- Existing code app attached as solution component type `300`.
- Initial managed preview export validated and published with a separate risk acknowledgment.
- Secretless GitHub OIDC identity configured with branch-scoped federation.
- Dataverse application user assigned System Customizer in PVE Dev.
- Four non-secret repository variables configured; daily workflow is ready for smoke testing.
