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
- `config/release-packages.json` defines independent artifact versions and package contracts.
- The core artifact version defines the stable release identity, Git tag, changelog section, and
   LinkedIn announcement version. Credits and code app may retain independent versions.
   Mixed-version stable manifests are valid.
- `site/downloads/release-manifest.json` records the exact published ZIP checksums and provenance.
- `config/release-evidence.json` records changed candidate identity and the independent PVE,
  hosted UI, manual TPM, and exact-byte clean-install gates for the published release. Schema 2
  requires a positive numeric `candidateRunId` for each changed artifact.
- `site/index.html` presents the public release history and roadmap.

Keep `site/index.html` a concise maker-facing summary. Internal environment names, test evidence,
component counts, browser-tool failures, and candidate/promotion/provenance mechanics belong in the
changelog, roadmap, detailed docs, or release evidence instead of the public page.

Do not infer shipped capabilities from a branch name or memory. Verify them against the solution
contract, implementation, managed package, and release manifest.

## Release procedure

Programmatic tenant writes are permitted only when the authenticated tenant ID is
`1938ee32-a258-454c-b8db-3a928341bd69`. Never automatically import or publish solution updates in
the TPM manual-upgrade tenant. Candidate automation must build, validate, and publish artifacts only;
the user performs TPM imports and upgrades manually. Tenant names, URLs, and profile aliases do not
override the tenant-ID boundary.

1. Review `ROADMAP.md` and move only completed, verified work into `CHANGELOG.md`.
2. Add a dated changelog entry with user-visible behavior, boundaries, and only the changed package artifacts.
3. Update the public release-history and roadmap sections in `site/index.html`.
4. Increment only changed solution artifacts. Leave unchanged package versions, filenames, ZIPs,
   hashes, and provenance intact; never rebuild them merely to align version numbers.
5. Regenerate `site/downloads/release-manifest.json` one artifact at a time after exporting managed
   packages; `update_release_manifest.py` requires `--artifact <core|credits|codeApp>`.
6. Review the surfaces indexed by `config/documentation-contract.json`.
7. Run `python3 scripts/validate_documentation.py` and `python3 scripts/validate_site.py`.
8. Test the public page at desktop and mobile widths in the shared VS Code browser page when the
   page changes.
9. For a candidate promotion, commit package inputs before generating the stable manifest. Copy
   the exact target-tenant-tested candidate ZIPs into `site/downloads/`; do not rebuild them.
10. Generate the manifest and release evidence with the implementation commit, commit release
   surfaces separately, and dispatch **validate release promotion** with one explicit artifact and
   its approved candidate workflow run ID. The candidate `artifactScope` and `artifacts` keys must
   contain exactly that artifact.
11. Open a PR, wait for every required check, merge, and verify Pages plus the public manifest.
12. Publish the stable GitHub Release using the core artifact version as its tag. The
   `publish LinkedIn release` workflow then generates the
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
minor four-part version (for example `2.1.0.0`) for each changed artifact only. If a
candidate package must be corrected after import, increment only the fourth segment (for example
`2.1.0.1`) and never overwrite the earlier ZIP. Export only changed artifacts
to `output/candidate/`; do not modify `site/downloads/`, the release manifest, changelog shipped
section, or public release history until the candidate passes target-tenant validation. Candidate
packages must pass the same component and tenant-neutrality checks as public packages.
Stable promotion must additionally prove that each promoted candidate/public ZIP pair is identical
and that its artifact-level `sourceCommit` is the latest commit touching that artifact's inputs.

The refresh workflow uses a fixed `core`, `credits`, and `codeApp` matrix. Scheduled and manual
`artifact=all` requests fan out into independent artifact legs and skip unchanged legs unless
`force=true`; a manual single-artifact request runs only its selected leg. Each changed leg exports,
validates, manifests, and uploads only its own candidate. No `all` candidate or promotion path
exists. Credits provenance is limited to
`solution/pvConversationInsightsCredits` and credit-specific scripts, so unrelated product changes
must not trigger a Credits candidate.

## Roadmap discipline

Every active item needs a status, goal, exit criteria, and tracking document. Mark work as
completed only after the relevant build, package, tenant smoke test, or API evidence exists.
Keep unsupported, undocumented, or intentionally excluded behavior under the explicit out-of-scope
section instead of presenting it as planned delivery.
