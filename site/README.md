# GitHub Pages maintenance

The public presentation is deployed from this directory by `.github/workflows/pages.yml`.
The two managed solution ZIPs are release artifacts, not generic source archives: they must be
exported from their deployed Dataverse solutions and pass `scripts/validate_site.py`.
Product capabilities, setup, and public copy must also pass `scripts/validate_documentation.py`.
The root [CHANGELOG.md](../CHANGELOG.md) records shipped versions and [ROADMAP.md](../ROADMAP.md)
records prioritized work and explicit product boundaries; update both with the public page.

## Required for every user-visible feature

1. Update `index.html` so the capability, screenshot, limitations, and install steps still
   describe the product accurately.
2. Increase both live solution versions and both package versions. Backward-compatible features
   increase the second component (`1.0.0.0` to `1.1.0.0`), fixes increase the third, and
   packaging-only rebuilds increase the fourth. Never overwrite a published package at the same
   version. Keep the core source files, page, filenames, and `config/release-packages.json` aligned.
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

6. Review every surface indexed by `config/documentation-contract.json`. When a listed product
   input changed, update the reviewed product digest only after documentation is complete:

   ```bash
   python3 scripts/validate_documentation.py --list-surfaces
   python3 scripts/validate_documentation.py --print-digest
   ```

7. Regenerate the manifest and validate documentation and both packages:

   ```bash
   python3 scripts/update_release_manifest.py --source-commit "$(git rev-parse HEAD)"
   python3 scripts/validate_documentation.py
   python3 scripts/validate_site.py
   ```

8. Refresh `assets/conversation-insights-preview.png` when the visible product changes. Use
   anonymized sample data only; never capture a real tenant, transcript, user, or environment.
9. Test both independent acknowledgment gates and the public Credits section at desktop and mobile widths.
10. Import the core ZIP and then the preview ZIP into a clean sandbox before publishing. Bind all
   target-local connection references, set required environment variables, smoke-test all 7 flows,
   and verify both apps open. Also test an upgrade over the previous public version when
   that package is available.

The validator checks that both packages are managed, versions match the release config, the JSON
Viewer PCF and code app are embedded in the correct package, checksums match the manifest, both
risk gates are present, and local site links resolve.

The documentation validator derives table/role/workflow/dependency counts, verifies required
Copilot Credit coverage, checks README data-source commands, discovers unindexed release surfaces,
and compares current product inputs with the reviewed digest. The checked-in
`.github/skills/release-documentation/SKILL.md` describes the corresponding agent workflow.

## Publishing

Merges to `main` that change `site/`, the validator, or the Pages workflow deploy automatically.
The repository administrator must select **GitHub Actions** as the Pages source once under
**Settings > Pages**.

Daily change-aware refresh is owned by `.github/workflows/refresh-packages.yml`. See
`docs/release-automation.md` for OIDC setup, deployment boundaries, and recovery.
