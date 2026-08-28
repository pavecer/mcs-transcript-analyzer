# Release package automation

The stable `2.1.0.0` release contains exactly three managed Power Platform solutions. Core and code
app are `2.1.0.0`; Credits remains byte-identical at `2.0.0.5`:

| Package | Solution | Support status | Import order |
| --- | --- | --- | --- |
| Core | `pvConversationInsights` | Required transcript/shared runtime and supported model-driven experience | First for clean install; second for `1.4.0.15` upgrade |
| Credits | `pvConversationInsightsCredits` | Optional licensing runtime only | Second for clean install; first for `1.4.0.15` upgrade |
| Code app | `pvConversationInsightsCodeApp` | Optional Power Apps code-app preview, unsupported | Last |

For a fresh target that includes the optional code app, **Enable code apps** must be saved and
independently reloaded as On before any package import. Follow the authoritative
[clean-install runbook](clean-install.md); its structural validator and browser evidence are
separate gates, and direct runtime loading is diagnostic only.

Core intentionally retains every table, plugin, Custom API, role, the model-driven app, four
transcript/shared flows, and three non-licensing references. Credits owns only three credit flows,
two licensing references, and the required credit tenant variable definition; managed packages
must contain no environment-variable current value. The code app stays separate so environments can use the supported
model-driven app without preview technology. This release passed PVE package and live-runtime
validation and the user-performed manual Contoso TPM upgrade.

The core artifact version is the stable release identity: the stable Git tag and LinkedIn
announcement use that version. Credits and code app versions remain independent, so a stable
manifest may validly contain mixed artifact versions.

## Automation design

`.github/workflows/refresh-packages.yml` runs daily at 03:17 UTC and can also be started
manually. It uses the following sequence:

1. Expand a fixed `core`, `credits`, and `codeApp` matrix. Scheduled runs and manual
  `artifact=all` requests fan out into independent artifact legs; a manual single-artifact request
  skips the other legs. `all` is not a candidate or promotion scope.
2. Resolve each selected artifact's newest package-input commit. Credits uses only
  `solution/pvConversationInsightsCredits` and credit-specific scripts, so unrelated core,
  parser, configuration, or code-app changes do not advance its provenance.
3. Compare that commit with the artifact's published provenance and skip the leg when they match,
  unless a manual run sets `force=true`.
4. For each changed leg, authenticate to Power Platform by GitHub OIDC. There is no client secret.
5. Build and deploy the committed code app only on a changed `codeApp` leg.
6. Export and validate only that leg's managed ZIP, including its solution identity, version,
  managed state, packaged component contract, ZIP integrity, SHA-256 hash, and exact
  package-input source commit.
7. Upload each changed ZIP and its scoped candidate manifest as a separate retained workflow
  artifact. Do not modify `site/downloads/` or deploy Pages from the candidate refresh.

Failures stop the affected leg before candidate upload. The previously validated downloads remain
live, including the current mixed-version stable manifest while candidate versions diverge.

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

This issue-fix workflow intentionally builds one patched core package from an immutable stable
base. It is not the feature-candidate pipeline and must not be used to publish or promote
`2.0.0.5`. Feature candidates are exported, validated, uploaded, and manifested independently for
each changed artifact, then handed to the user for manual TPM testing. Every candidate manifest
contains the selected artifact scope and exact package-input `sourceCommit`; local validation
derives the same artifact-specific commit from Git when `--source-commit` is omitted.

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

## Release evidence and promotion gate

`config/release-evidence.json` schema 2 records the changed artifact scope, candidate source commit,
hashes, and positive numeric `candidateRunId` values that became the published packages, plus
explicit PVE package/runtime, hosted UI, manual TPM upgrade, and exact-byte clean-install gates.
Each passed gate requires an ISO-8601 completion timestamp and a checked-in evidence reference.

Run:

```bash
python3 scripts/validate_release_evidence.py
```

The validator requires the evidence version, source commit, filenames, and hashes to match
`site/downloads/release-manifest.json`.

Before merging a stable release PR, dispatch **validate release promotion** with the artifact,
version, and approved `refresh release packages` workflow `candidate_run_id`. The workflow
downloads the one retained `managed-candidate-<artifact>-*` artifact for that matrix leg and
executes:

```bash
python3 scripts/validate_release_promotion.py --artifact <core|credits|codeApp> --version <version>
python3 scripts/validate_release_evidence.py
```

Stable manifest generation likewise requires one explicit artifact:

```bash
python3 scripts/update_release_manifest.py --artifact <core|credits|codeApp> --source-commit <implementation-sha>
```

There is no `all` promotion path. The promotion validator and workflow accept exactly one artifact
and require the candidate manifest's `artifactScope` and `artifacts` keys to contain exactly that
artifact. This makes candidate/stable byte identity and release evidence reproducible from a new
session without access to the original developer workstation.

## npm dependency reliability

The code app and PCF lockfiles must contain canonical `https://registry.npmjs.org/` tarball URLs.
Developer workstations may use a local or enterprise npm proxy, but that proxy must not be serialized
into a committed lockfile. Run `python scripts/validate_npm_lockfiles.py` after every dependency or
lockfile update. The build workflow runs the same gate before the Node jobs and uses cached `npm ci`
so CI installs exactly the reviewed dependency graph.

If a Node job fails during package download, inspect the failed URL and step before changing source.
An HTTP 5xx from a registry is an external install failure, not evidence of an application defect.
Validate the lockfile hosts, run the affected build locally, and retry the failed job once the
registry responds. Do not bypass a real compile, test, typecheck, or lint failure as an outage.

## LinkedIn release publication

Stable GitHub Releases can publish a LinkedIn announcement through
`.github/workflows/linkedin-release.yml`. The workflow does not use generative AI. It derives the
release identity from the core artifact version in `site/downloads/release-manifest.json`, requires
the stable tag and exact `CHANGELOG.md` section to use that version, and generates a short awareness announcement with one
audience-focused value statement and one public Pages call to action. Detailed capabilities,
boundaries, validation evidence, package inventories, checksums, and setup instructions remain on
the public site and GitHub Release. The generator enforces a 600-character marketing limit, well
below LinkedIn's technical 3,000-character limit. Prereleases are excluded.

Create a GitHub environment named `linkedin-production` and configure:

| Type | Name | Value |
| --- | --- | --- |
| Secret | `LINKEDIN_ACCESS_TOKEN` | LinkedIn OAuth token with permission to post for the author |
| Variable | `LINKEDIN_AUTHOR_URN` | `urn:li:person:<id>` or `urn:li:organization:<id>` |
| Variable | `LINKEDIN_API_VERSION` | Active LinkedIn API version in `YYYYMM` format |

Person posts require the LinkedIn `w_member_social` permission. Organization posts require
`w_organization_social` and an eligible LinkedIn Page role for the authenticated member. Confirm
current headers, versions, roles, and permission requirements in the official
[LinkedIn Posts API documentation](https://learn.microsoft.com/linkedin/marketing/community-management/shares/posts-api).

Run **publish LinkedIn release** manually with `dry_run=true` before the first live post and after
changing the author or API version. Dry runs call the publisher with `--dry-run` and require none of
the three LinkedIn settings. On a successful live post, the workflow stores the returned LinkedIn
post URN in a hidden marker in the GitHub Release notes. Normal reruns then stop instead of posting
a duplicate.

An automatic stable-release run with any missing LinkedIn setting still generates and validates the
release copy, then emits a GitHub notice and skips public Pages verification, the LinkedIn API call,
and the release marker. This is a successful publication skip, not evidence of a post. Never report
that LinkedIn publication occurred unless the hidden release marker contains the returned post URN.

To recover from an unconfigured run, configure `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN`, and
`LINKEDIN_API_VERSION`, dispatch the same stable tag with `dry_run=true`, and review the generated
copy. Make a separate intentional dispatch with `dry_run=false` only after that dry run succeeds.

To correct an already published announcement without creating a duplicate, dispatch the workflow
from the default branch with the stable tag and `update_post_urn` set to the exact post URN stored in
the release marker. The workflow validates that match before using LinkedIn's partial-update API,
does not create a new post, and preserves the original marker. Review the concise generated copy
with `dry_run=true` before the live update.

After an update, reload the public post and verify the rendered commentary, CTA, and post URL.
LinkedIn can retain old commentary in hidden hydration data, so raw DOM text matches or element
counts are not proof that the visible post is stale. Confirm the visible post text and that no
duplicate announcement was created.

The repository can automate publication after configuration, but it cannot grant LinkedIn API
products or renew an expired OAuth authorization. Keep the token only in GitHub Secrets, rotate it
before expiry, and use an environment approval rule if a human publication gate is preferred.

## Important deployment boundary

Programmatic Power Platform and Dataverse writes are allowed only when the authenticated tenant ID
is `1938ee32-a258-454c-b8db-3a928341bd69`. The TPM tenant is reserved for manual solution upgrade
testing. Automation may build packages and perform read-only checks for TPM, but the user performs
all imports, publishes, connection mappings, and other changes there. Tenant and environment names,
URLs, account domains, and PAC profile aliases are not authorization boundaries.
All Dataverse-mutating transcript utilities call `require_authorized_config` or
`require_authorized_tenant` before their first write. `validate_solution_ownership.py` keeps the
known write-entry-point inventory and fails if any listed script loses that guard.

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
`contents: read` because candidate exports are uploaded as artifacts rather than committed.

## Artifact candidate and promotion flow

1. Deploy and verify changed source solutions in PVE Dev.
2. Export only changed artifacts to `output/candidate/` with immutable versioned filenames; never
  rebuild unchanged packages or place unapproved candidates in `site/downloads/`.
3. Run `scripts/validate_solution_ownership.py` and
  `scripts/validate_candidate_packages.py --artifact <core|credits|codeApp> --source-commit <implementation-sha>`.
4. Test only changed packages. Preserve dependency order when several artifacts change; a
  code-app-only candidate upgrades only `pvConversationInsightsCodeApp`.
5. Record PVE package/runtime, hosted UI, TPM manual-upgrade, and exact-byte clean-install evidence
  separately in `config/release-evidence.json`. Schema 2 records a positive numeric
  `candidateRunId` for every changed artifact. No gate implies another.
6. After manual target approval, commit package inputs first. Copy the exact validated candidate
  bytes into `site/downloads/`; do not rebuild them.
7. Generate the stable manifest with the implementation commit, commit publication surfaces
  separately, and dispatch **validate release promotion** against the approved candidate run.
8. Merge only after required checks pass, then verify Pages, the public manifest, each changed
  download, and unchanged artifact hashes.

For an identity/export smoke test that must not deploy code-app source, run manually with
`force=true` and `export_only=true`. Scheduled runs always deploy the committed code app before
exporting.

## Version changes

The core, credit add-on, and code-app packages use independent immutable four-part versions:

| Change | Version example | Use |
| --- | --- | --- |
| Breaking install or migration change | `2.0.0.0` | Existing consumers need explicit migration work |
| Backward-compatible feature | `1.1.0.0` | New tables, APIs, flows, app capabilities, or dependencies |
| Backward-compatible fix | `1.1.1.0` | Correct behavior without adding a feature surface |
| Rebuilt release artifact only | `1.1.1.1` | Packaging-only correction with unchanged solution behavior |

Every changed package must have a version greater than its own previous package. Unchanged packages
retain their previous version, filename, bytes, hash, and source provenance. Never replace a
published ZIP while keeping its version.

For every artifact version change:

1. Update only changed live Dataverse solutions in PVE Dev with `pac solution online-version`.
2. When core changes, update its source versions in `solution-definition.json` and
  `src/Other/Solution.xml`; otherwise leave core source untouched.
3. Update only changed package versions and filenames in `config/release-packages.json`. Update
  ownership or dependency contracts only when those contracts actually changed.
4. Update the public page's version and install content.
5. Review all indexed documentation surfaces, update the documentation digest when product inputs
  changed, and run `scripts/validate_documentation.py`.
6. Export changed managed candidates to `output/candidate/` and run scoped candidate validation. Do not
   regenerate the stable manifest before target-tenant approval.
7. Test clean install through `docs/clean-install.md` and previous-version upgrade in its documented
  order. Confirm Code Apps preflight before imports, all managed identities/components, target-local
  app resolution, preserved workflow identities, and retained data.
8. Publish through a pull request. Confirm CI, the refresh workflow, Pages deployment, changed
  manifest versions/hashes, changed downloads, and preserved hashes for unchanged artifacts.

The release validator rejects filename/version drift, unsynchronized core source versions when
core changes, unexpected code-app dependencies, stale manifests, and packages exported from a live
solution whose version does not match that artifact's repository contract.

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
