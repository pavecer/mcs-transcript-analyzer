# Changelog

Release history for MCS Transcript Analyzer. Each published package version is immutable; package
checksums and source provenance are recorded in `site/downloads/release-manifest.json`.

## 2.0.0.5 - 2026-08-25

Stable three-package architecture release after PVE deployment and hosted UI smoke, tenant-neutral
package validation, and the user-performed manual Contoso TPM upgrade test.

- Split the product into exactly three synchronized managed packages: required transcript/shared
  core, optional Copilot Credit runtime add-on, and optional unsupported preview code app.
- Kept all Dataverse schema, plugins, Custom APIs, roles, the model-driven app, inventory and
  transcript runtime, four transcript/shared flows, and three non-licensing connection references
  in core to avoid destructive schema or data migration.
- Moved ownership of only the three credit flows and the `pvci_licensinghttp` and
  `pvci_powerplatformapi` references, plus the required `pvci_CreditReportingTenantId` definition,
  into `pvConversationInsightsCredits`. Core imports no longer prompt for this credit-only setting.
- Changed tenant inventory import to derive the current tenant from Dataverse organization metadata,
  while preserving rejection when an explicit payload tenant conflicts with the environment.
- Prevented managed packages from including environment-variable current values; the optional
  add-on prompts each target for its own tenant ID and no PVE value is distributed.
- Fixed the code-app Credits capability check so entering the checking state no longer cancels its
  own Dataverse queries and leaves the page stuck at availability validation. Capability queries
  now time out into the retry state instead of displaying an indefinite loading message.
- Defined clean installation order as core, optional credits, optional code app. For upgrades from
  `1.4.0.15`, install the credit add-on first, apply the core managed upgrade second, and upgrade
  the code app last so existing credit workflow identities move additively.
- Kept Credits navigation visible with capability states: unavailable without the add-on,
  setup-required until successful credit-sync evidence exists, and ready only when both exist.
  Credit data services are not mounted before ready.
- Confirmed transcript analysis does not require licensing-administrator access when the optional
  credit add-on is omitted.
- Made transcript scope local-only by default in the code app. Inventory discovery and access
  verification do not enable remote collection; a verified remote source requires explicit
  administrator consent that transcripts will be copied into and retained in the installed
  Dataverse environment. Reporting environment selectors appear only while a remote source is
  enabled, and Sessions, Trends, and Credits resource reporting remain scoped to the host environment
  until then. User usage and recent governance request history remain tenant-wide. Disabling a
  source stops future imports without deleting data already copied.
- Corrected Credits local-only filtering so hiding its environment selector cannot leave remote
  usage, capacity, agent, threshold, or correlation rows in the active reporting scope.
- Validated in PVE that all three live solutions are `2.0.0.5`; core exports exactly four flows and
  three non-licensing references; the add-on exports exactly three flows and two licensing
  references; all seven unique flows are active; all five references are mapped; and all three
  managed exports pass tenant-neutral package validation. The hosted PVE UI smoke and the
  user-performed manual Contoso TPM upgrade passed.

Published downloads:

- Core: `pvConversationInsights-managed-2.0.0.5.zip`
- Credits: `pvConversationInsightsCredits-managed-2.0.0.5.zip`
- Preview: `pvConversationInsightsCodeApp-managed-2.0.0.5.zip`

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
