# Changelog

Release history for MCS Transcript Analyzer. Each published package version is immutable; package
checksums and source provenance are recorded in `site/downloads/release-manifest.json`.

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
