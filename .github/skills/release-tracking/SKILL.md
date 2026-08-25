---
name: release-tracking
description: "Maintain the MCS Transcript Analyzer changelog, roadmap, release manifest, and public GitHub Pages release history. Use when preparing a release, adding a feature, changing product boundaries, updating package versions, or reviewing roadmap drift."
---

# Release Tracking

Use this workflow for every versioned release, user-visible feature, product-boundary change, or
roadmap review.

## Source of truth

- `CHANGELOG.md` records shipped behavior by package version and date.
- `ROADMAP.md` records prioritized work, status, exit criteria, and explicit out-of-scope items.
- `config/release-packages.json` defines synchronized solution versions and package contracts.
- `site/downloads/release-manifest.json` records the exact published ZIP checksums and provenance.
- `site/index.html` presents the public release history and roadmap.

Do not infer shipped capabilities from a branch name or memory. Verify them against the solution
contract, implementation, managed package, and release manifest.

## Release procedure

Programmatic tenant writes are permitted only when the authenticated tenant ID is
`1938ee32-a258-454c-b8db-3a928341bd69`. Never automatically import or publish solution updates in
the TPM manual-upgrade tenant. Candidate automation must build, validate, and publish artifacts only;
the user performs TPM imports and upgrades manually. Tenant names, URLs, and profile aliases do not
override the tenant-ID boundary.

1. Review `ROADMAP.md` and move only completed, verified work into `CHANGELOG.md`.
2. Add a dated changelog entry with user-visible behavior, boundaries, and all three package artifacts.
3. Update the public release-history and roadmap sections in `site/index.html`.
4. Keep the core, optional credit add-on, and optional code-app versions synchronized and never
   overwrite a published version.
5. Regenerate `site/downloads/release-manifest.json` after exporting managed packages.
6. Review the surfaces indexed by `config/documentation-contract.json`.
7. Run `python3 scripts/validate_documentation.py` and `python3 scripts/validate_site.py`.
8. Test the public page at desktop and mobile widths in the shared VS Code browser page when the
   page changes.
9. For a candidate promotion, commit package inputs before generating the stable manifest. Copy
   the exact target-tenant-tested candidate ZIPs into `site/downloads/`; do not rebuild them.
10. Generate the manifest with the implementation commit, commit release surfaces separately, and
    run `python3 scripts/validate_release_promotion.py --version <version>`.
11. Open a PR, wait for every required check, merge, and verify Pages plus the public manifest.
12. Publish the stable GitHub Release. The `publish LinkedIn release` workflow then generates the
   announcement from the matching changelog section and publishes it when the
   `linkedin-production` environment is configured. Verify its release marker and LinkedIn post.

The Release Maintainer is the single mutation owner. Treat package validation, documentation/site
validation, CI build jobs, target-tenant testing, and Pages verification as independent gates rather
than assigning overlapping agents that can race on release files.

## Issue candidate releases

For an affected-tenant bug fix, use `.github/workflows/candidate-release.yml` with a new
backward-compatible version such as `1.3.1.0`. The workflow validates the source, builds a managed
candidate from the stable package plus reviewed workflow changes, and publishes a GitHub prerelease
with an issue comment containing the direct ZIP URL. It must not import into any tenant.
Dataverse managed solutions cannot be exported from a managed target, so do not add a manual target
export step or overwrite the stable package.

For a feature candidate that needs cross-tenant validation before public release, use the next
minor four-part version (for example `2.0.0.0`) for the core, credit add-on, and code-app source
solutions. If a
candidate package must be corrected after import, increment only the fourth segment (for example
`2.0.0.1`) and never overwrite the earlier ZIP. Export
to `output/candidate/`; do not modify `site/downloads/`, the release manifest, changelog shipped
section, or public release history until the candidate passes target-tenant validation. Candidate
packages must pass the same component and tenant-neutrality checks as public packages.
Stable promotion must additionally prove that candidate and public ZIP hashes are identical and
that `sourceCommit` is the latest commit touching package inputs.

## Roadmap discipline

Every active item needs a status, goal, exit criteria, and tracking document. Mark work as
completed only after the relevant build, package, tenant smoke test, or API evidence exists.
Keep unsupported, undocumented, or intentionally excluded behavior under the explicit out-of-scope
section instead of presenting it as planned delivery.
