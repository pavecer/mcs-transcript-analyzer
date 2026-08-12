---
name: release-documentation
description: "Maintain MCS Transcript Analyzer release documentation and the public GitHub Pages site. Use when changing Copilot Credit behavior, tables, roles, flows, connections, setup, README, docs, release notes, managed packages, or site/index.html; also use when auditing documentation drift before a release."
argument-hint: "Describe the capability or release documentation change"
---

# Release Documentation

Use this workflow whenever product behavior or release packaging changes, and whenever README,
`docs/`, or the public GitHub Pages site is reviewed for completeness.

For version history and prioritized future work, also follow `.github/skills/release-tracking/SKILL.md`.
`CHANGELOG.md` records only shipped behavior; `ROADMAP.md` records planned work and explicit
boundaries.

## Procedure

1. Run `python3 scripts/validate_documentation.py --list-surfaces` to enumerate every current
   credit/release-facing document discovered from the filesystem.
2. Read `config/documentation-contract.json` and the product inputs listed there. Do not document
   behavior from memory or infer unsupported capabilities.
3. Update all affected surfaces, including:
   - `README.md` for capability summary and contributor setup;
   - `docs/credit-reporting.md` for source truth, governance lifecycle, security, and limitations;
   - `docs/operations.md` and `docs/permissions-and-inventory.md` for target setup and roles;
   - `docs/data-model.md` and `docs/architecture.md` for component/data-flow changes;
   - `scripts/transcript_insights/README.md` for contributor commands;
   - `site/index.html` for concise public-facing capabilities, boundaries, and install links.
4. Preserve the reporting truth boundary: resource credits, user credits, capacity, inventory,
   thresholds, transcripts, and evaluations are separate evidence unless a documented source key
   joins them. Never present correlation as billing allocation.
5. If a product input changed, review every indexed surface, run
   `python3 scripts/validate_documentation.py --print-digest`, and update
   `productSourceDigest` only after the documentation review is complete.
6. Run:

   ```text
   python3 scripts/validate_documentation.py
   python3 scripts/validate_site.py
   ```

7. For public-page changes, validate desktop and mobile rendering in the already shared VS Code
   browser page when available. Do not launch a separate browser unless the built-in browser lacks
   a required capability.

## Release Gate

The CI `site` job must run both validators. Do not bypass the documentation contract by deleting
coverage terms or removing a discovered surface from the index. Add new public/docs surfaces to
the contract and state explicitly what capability evidence they must retain.