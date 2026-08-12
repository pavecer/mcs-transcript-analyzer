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

1. Review `ROADMAP.md` and move only completed, verified work into `CHANGELOG.md`.
2. Add a dated changelog entry with user-visible behavior, boundaries, and both package artifacts.
3. Update the public release-history and roadmap sections in `site/index.html`.
4. Keep the core and code-app versions synchronized and never overwrite a published version.
5. Regenerate `site/downloads/release-manifest.json` after exporting managed packages.
6. Review the surfaces indexed by `config/documentation-contract.json`.
7. Run `python3 scripts/validate_documentation.py` and `python3 scripts/validate_site.py`.
8. Test the public page at desktop and mobile widths in the shared VS Code browser page when the
   page changes.

## Roadmap discipline

Every active item needs a status, goal, exit criteria, and tracking document. Mark work as
completed only after the relevant build, package, tenant smoke test, or API evidence exists.
Keep unsupported, undocumented, or intentionally excluded behavior under the explicit out-of-scope
section instead of presenting it as planned delivery.
