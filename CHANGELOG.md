# Changelog

Release history for MCS Transcript Analyzer. Each published package version is immutable; package
checksums and source provenance are recorded in `site/downloads/release-manifest.json`.

## 1.4.0.15 - 2026-08-25

Cross-environment transcript operations release.

- Added tenant inventory-backed central transcript collection through one packaged, tenant-neutral Dataverse connection reference.
- Added source-managed onboarding with audited access requests, least-privilege verification, explicit access states, and a verified-only collection gate.
- Added runtime-failure, knowledge-retrieval, agent-reasoning, and time-based flow-correlation investigation surfaces.
- Added Inventory Management with clickable readiness summaries, source enablement controls, and visible denied or unsupported environments.
- Added one persistent code-app navigation bar for Sessions, Trends, Inventory, and Credits, with contextual sidebars and responsive mobile behavior.
- Kept Administrator bootstrap unavailable until external reconciliation can provision access and prove that temporary elevation was removed.
- Validated both managed packages as upgrades in PVE Dev and through a manual cross-tenant TPM upgrade.

Artifacts:

- Core: `pvConversationInsights-managed-1.4.0.15.zip`
- Preview: `pvConversationInsightsCodeApp-managed-1.4.0.15.zip`
- Release manifest: [`site/downloads/release-manifest.json`](site/downloads/release-manifest.json)

## 1.3.1.0 - 2026-08-12

Backward-compatible governance bug fix.

- Fixed the Copilot Credit threshold collector and processor to call the observed tenant-scoped licensing route.
- Preserved the stable `1.3.0.0` packages and published the corrected managed packages as `1.3.1.0`.
- Validated the core upgrade in PVE Preview Sand US before promoting the release.

Artifacts:

- Core: `pvConversationInsights-managed-1.3.1.0.zip`
- Preview: `pvConversationInsightsCodeApp-managed-1.3.1.0.zip` (unchanged code, synchronized release version)
- Release manifest: [`site/downloads/release-manifest.json`](site/downloads/release-manifest.json)

## 1.3.0.0 - 2026-08-12

Copilot Credit operations release.

- Added actual billed and non-billed resource usage, tenant-wide user usage, and environment capacity collection.
- Added tenant environment and agent inventory independent of credit activity, including zero-usage agents.
- Added `PVCI Analyst`, `PVCI Privacy Approver`, and `PVCI Credit Administrator` roles.
- Added read-only threshold governance snapshots with Critical, High, Watch, Healthy, and No limit risk bands.
- Added audited, stale-state-checked agent threshold requests with Requested, Processing, Applied, Review needed, Failed, and Verify applied outcomes.
- Kept resource, user, capacity, inventory, transcript, and evaluation evidence separate; the product does not claim exact billing allocation.
- Published the supported managed model-driven solution and the separate unsupported preview code-app solution.

Artifacts:

- Core: `pvConversationInsights-managed-1.3.0.0.zip`
- Preview: `pvConversationInsightsCodeApp-managed-1.3.0.0.zip`
- Release manifest: [`site/downloads/release-manifest.json`](site/downloads/release-manifest.json)

## Earlier versions

The repository retains the previous managed package artifacts for upgrade testing:

- `1.2.0.0` - [`pvConversationInsights-managed-1.2.0.0.zip`](site/downloads/pvConversationInsights-managed-1.2.0.0.zip)
- `1.1.0.0` - [`pvConversationInsights-managed-1.1.0.0.zip`](site/downloads/pvConversationInsights-managed-1.1.0.0.zip)
- `1.0.0.0` - [`pvConversationInsights-managed-1.0.0.0.zip`](site/downloads/pvConversationInsights-managed-1.0.0.0.zip)

For implementation-level history, use the [Git commit history](https://github.com/pavecer/mcs-transcript-analyzer/commits/main)
and version tag `v1.3.0.0`. Future releases must add a dated entry here and update the public
release section on the [GitHub Pages site](https://pavecer.github.io/mcs-transcript-analyzer/).
