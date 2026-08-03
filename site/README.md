# GitHub Pages maintenance

The public presentation is deployed from this directory by `.github/workflows/pages.yml`.
The two managed solution ZIPs are release artifacts, not generic source archives: they must be
exported from their deployed Dataverse solutions and pass `scripts/validate_site.py`.

## Required for every user-visible feature

1. Update `index.html` so the capability, screenshot, limitations, and install steps still
   describe the product accurately.
2. Increase the version in `solution/pvConversationInsights/solution-definition.json` and in
   the source Dataverse solution. Use the same four-part version in the page and ZIP filename.
3. Ensure every new core component is a root component of `pvConversationInsights`. In
   particular, do not leave forms depending on a PCF control from the Active solution.
4. Keep the preview code app in `pvConversationInsightsCodeApp`; do not add it to the core
   package.
5. Export fresh **managed** packages from the approved development environment:

   ```bash
   pac org who
   pac solution export \
     --name pvConversationInsights \
     --path site/downloads/pvConversationInsights-managed-<version>.zip \
     --managed --overwrite --environment <approved-dataverse-url>
   pac solution export \
     --name pvConversationInsightsCodeApp \
     --path site/downloads/pvConversationInsightsCodeApp-managed-<version>.zip \
     --managed --overwrite --environment <approved-dataverse-url>
   ```

6. Regenerate the manifest and validate both packages:

   ```bash
   python3 scripts/update_release_manifest.py --source-commit "$(git rev-parse HEAD)"
   python3 scripts/validate_site.py
   ```

7. Refresh `assets/conversation-insights-preview.png` when the visible product changes. Use
   anonymized sample data only; never capture a real tenant, transcript, user, or environment.
8. Test both independent acknowledgment gates at desktop and mobile widths.
9. Import the core ZIP and then the preview ZIP into a clean sandbox before publishing. Bind the
   connection reference, activate the flow, and verify both apps open.

The validator checks that both packages are managed, versions match the release config, the JSON
Viewer PCF and code app are embedded in the correct package, checksums match the manifest, both
risk gates are present, and local site links resolve.

## Publishing

Merges to `main` that change `site/`, the validator, or the Pages workflow deploy automatically.
The repository administrator must select **GitHub Actions** as the Pages source once under
**Settings > Pages**.

Daily change-aware refresh is owned by `.github/workflows/refresh-packages.yml`. See
`docs/release-automation.md` for OIDC setup, deployment boundaries, and recovery.
