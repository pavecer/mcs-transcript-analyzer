# GitHub Pages maintenance

The public presentation is deployed from this directory by
`.github/workflows/pages.yml`. The managed solution ZIP is a release artifact, not a generic
source archive: it must be exported from the deployed Dataverse solution and pass
`scripts/validate_site.py`.

## Required for every user-visible feature

1. Update `index.html` so the capability, screenshot, limitations, and install steps still
   describe the product accurately.
2. Increase the version in `solution/pvConversationInsights/solution-definition.json` and in
   the source Dataverse solution. Use the same four-part version in the page and ZIP filename.
3. Ensure every new component is a root component of `pvConversationInsights`. In particular,
   do not leave forms depending on a PCF control from the Active solution.
4. Export a fresh **managed** package from the approved development environment:

   ```bash
   pac org who
   pac solution export \
     --name pvConversationInsights \
     --path site/downloads/pvConversationInsights-managed-<version>.zip \
     --managed --overwrite --environment <approved-dataverse-url>
   ```

5. Replace the SHA-256 shown in `index.html`:

   ```bash
   shasum -a 256 site/downloads/pvConversationInsights-managed-<version>.zip
   ```

6. Refresh `assets/conversation-insights-preview.png` when the visible product changes. Use
   anonymized sample data only; never capture a real tenant, transcript, user, or environment.
7. Run `python3 scripts/validate_site.py`, then test the page at desktop and mobile widths.
8. Import the managed ZIP into a clean sandbox before publishing a release. Bind the connection
   reference, activate the flow, and verify the model-driven app opens.

The validator deliberately checks that the package is managed, its version matches the page,
the JSON Viewer PCF is embedded, the checksum is current, and all local site links resolve.

## Publishing

Merges to `main` that change `site/`, the validator, or the Pages workflow deploy automatically.
The repository administrator must select **GitHub Actions** as the Pages source once under
**Settings > Pages**.
