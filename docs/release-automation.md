# Daily release package automation

The public site publishes two independent managed Power Platform solutions:

| Package | Solution | Support status | Import order |
| --- | --- | --- | --- |
| Core | `pvConversationInsights` | Supported model-driven experience | First |
| Code app | `pvConversationInsightsCodeApp` | Power Apps code-app preview, unsupported | Second |

The code app stays separate so environments can use the supported model-driven app without
enabling preview technology. Its managed solution depends on the three core Dataverse tables.

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

## Important deployment boundary

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

Update both the live solution version and `config/release-packages.json`. Rename the expected
ZIP filename in the same config. The site reads filenames and hashes from the release manifest,
while `scripts/validate_site.py` prevents Pages from publishing mismatched versions.

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
