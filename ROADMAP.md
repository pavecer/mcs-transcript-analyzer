# Roadmap

This roadmap describes product direction, not a promise of delivery dates. The public copy and
this file must agree about supported behavior and boundaries. Use the status and exit criteria to
keep work testable.

Last reviewed: 2026-08-25

## Now

### Three-package 2.0 candidate promotion

- **Status:** All three `2.0.0.5` solutions are deployed; their tenant-neutral managed exports, hosted PVE UI smoke, and user-performed manual Contoso TPM upgrade passed; stable promotion remains pending
- **Goal:** Separate optional licensing runtime from required transcript/shared core without moving schema, APIs, roles, or data ownership and without breaking existing credit workflow identities.
- **Exit criteria:** A manual TPM upgrade from public `1.4.0.15` succeeds in the required order (credits add-on, core managed upgrade, code app); existing data and credit workflow identities remain intact; credit capability states reach unavailable, setup-required, and ready under the documented conditions; candidate and promoted public ZIP bytes match; release-promotion, documentation, and site validators pass.
- **Tracking:** [Unreleased changelog](CHANGELOG.md), [release automation](docs/release-automation.md), [operations](docs/operations.md), and `output/candidate/`

### Central transcript source discovery

- **Status:** Implemented and tenant-probed in PVE Dev and TPM
- **Goal:** Build a read-only tenant-wide source registry that uses the Power Platform admin inventory to test Dataverse transcript access per environment, without installing the solution into source environments.
- **Exit criteria:** Met. PVE and TPM probes distinguish readable-with-data, readable-empty, access-denied, and unavailable environments without copying transcript content. Both apps expose the persisted status.
- **Tracking:** [Operations guide](docs/operations.md), [architecture](docs/architecture.md), and `scripts/transcript_insights/probe_transcript_sources.py`

The preview code app remains local-only until an administrator enables a verified remote source and
accepts the remote-to-collector data transfer. Reporting environment controls follow that persisted
consent state; discovery and verification alone never reveal or activate cross-environment scope.

### Replace pre-authorized collection with zero-touch onboarding

- **Status:** Source-managed request/status backend, code-app workflow, and packaged verifier are implemented and smoke-tested in PVE Dev; external administrator-bootstrap reconciliation remains
- **Goal:** Support both source-managed least-privilege onboarding for restricted environments and optional administrator bootstrap where policy permits it, while converging on a dedicated collector identity with organization Read on Conversation Transcript and no retained System Administrator.
- **Exit criteria:** Inventory Management controls each environment's onboarding mode (`Source-managed`, `Administrator bootstrap`, or `Excluded`), exposes approval/setup/verification/cleanup state, and never offers unavailable automation. Source-managed environments can verify a locally assigned least-privilege role without elevation. Bootstrap environments are reconciled automatically, temporary System Administrator access is removed and proven removed, new environments are detected, and denied/unsupported environments remain explicit.
- **Tracking:** [Operations guide](docs/operations.md) and [permissions checklist](docs/permissions-and-inventory.md)

## Next

### Central transcript batch collector

- **Status:** Source-managed import, routing, and verified-only enablement shipped in `1.4.0.15` after cross-tenant upgrade validation; automated onboarding remains
- **Goal:** Read transcripts from registry-approved source environments and import normalized sessions and turns into the collector environment through a bounded, idempotent Custom API.
- **Exit criteria:** PVE Preview to PVE Dev import/idempotent replay and generic-flow runs pass. Completion additionally requires automated least-privilege source onboarding; manual role assignment in every environment is not accepted as completion.
- **Tracking:** [Cross-environment design](docs/cross-environment-credit-consumption-design.md) and [architecture](docs/architecture.md)

### ESS structured runtime diagnostics

- **Status:** Phase 1 deployed and backend-smoke-tested in PVE Dev as candidate `1.4.0.3`; clean-sandbox upgrade and full hosted UI smoke pending
- **Goal:** Turn ESS topic/runtime failures into filterable session facts and an ordered operational timeline without requiring raw JSON inspection.
- **Exit criteria:** Both local and central ingestion produce identical topic/error summaries; user-facing error traces survive default retention; core form/views and code app display the failure; the candidate upgrades cleanly in a second environment; and the hosted app completes a signed-in failure-timeline smoke without a Power Apps web-player host error.
- **Tracking:** [Architecture](docs/architecture.md), [data model](docs/data-model.md), and [operations](docs/operations.md)

### Knowledge retrieval diagnostics

- **Status:** Candidate `1.4.0.4` deployed and backend-smoke-tested in PVE Dev; full hosted Knowledge-tab smoke pending
- **Goal:** Make Universal Search and other knowledge retrievals visible independently from connector/tool calls, including completion, latency, cited sources, and failed source types.
- **Exit criteria:** Local and central ingestion agree on observed `KnowledgeTraceData`; model-driven and code apps show the same counts; the PVE Preview ServiceNow knowledge session reports one successful `Answered` retrieval and one cited source; no query text or retrieved passage is duplicated into summary JSON; and the hosted app completes a signed-in Knowledge-tab smoke without the Power Apps web-player host error.
- **Tracking:** [Architecture](docs/architecture.md), [data model](docs/data-model.md), and [operations](docs/operations.md)

### Conversation investigation usability

- **Status:** First-time-reader clarity, full-width Trends, and inventory-backed environment names implemented for candidate `1.4.0.9`; PVE Dev visual smoke pending
- **Goal:** Let an operator understand context, outcome, routing, knowledge, tools, candidate flows, errors, and timing before opening technical payloads.
- **Exit criteria:** Overview is the default; filter and detail selections cannot disagree; zero is distinguished from unavailable telemetry; timing and correlation labels avoid false attribution; unknown flow states remain unknown; representative simple, knowledge, expression-failure, connector-failure, no-flow, and multiple-candidate sessions pass a signed-in visual smoke.
- **Tracking:** [Operations interpretation guide](docs/operations.md) and the [code app](codeapp/)

### Agent reasoning visualization

- **Status:** Validated against 23 stored plans and implemented for candidate `1.4.0.10`; PVE Dev visual smoke pending
- **Goal:** Replace raw-first DynamicPlan inspection with a human-readable plan and step lifecycle while retaining exact evidence on demand.
- **Exit criteria:** Multi-plan and single-plan sessions group correctly; completed, incomplete, and Knowledge-answered steps are distinct; argument values remain behind raw evidence; representative test and production sessions pass a signed-in visual smoke.
- **Tracking:** [Architecture reasoning model](docs/architecture.md), [operations](docs/operations.md), and `codeapp/src/components/ReasoningFlow.tsx`

### Agent and user conversation behavior telemetry

- **Status:** Discovery; intentionally separate from the per-session workspace
- **Goal:** Provide grouped operational behavior by agent, environment, channel, topic, and privacy-approved user dimensions: volume, outcomes, reply availability/latency, routing, knowledge/tool/flow participation, failure categories, repeat incidents, and trend changes.
- **Exit criteria:** Aggregates use server-side bounded windows and freshness metadata; agent/user identity is deduplicated; capture availability is a grouping dimension so missing traces are never counted as zero; flow candidates are deduplicated; user-level views follow the existing privacy approval boundary; every aggregate drills into its supporting sessions.
- **Tracking:** [Architecture](docs/architecture.md), [data model](docs/data-model.md), and the recent-sample boundary in [operations](docs/operations.md)

### In-platform flow-run detail enrichment

- **Status:** Blocked on deployment-policy validation
- **Goal:** Move flow-run body enrichment from the headless worker into an approved DLP/custom-connector path where the Power Automate API audience and runtime policy permit it.
- **Exit criteria:** A sandbox run fetches action and loop-iteration details without storing credentials or weakening the Dataverse plugin boundary.
- **Tracking:** [Flow-run detail findings](docs/flow-run-detail-findings.md)

### Detailed cross-environment agent enrichment

- **Status:** Planned
- **Goal:** Enrich base tenant inventory with Dataverse agent metadata, owners, components, and related process information in environments where the collector identity has explicit access.
- **Exit criteria:** Access is granted per source environment, unavailable metadata is represented as unknown, and no missing access is reported as a missing agent.
- **Tracking:** [Permissions and tenant inventory](docs/permissions-and-inventory.md)

## Later

### Make the code app a supported production surface

- **Status:** Preview
- **Goal:** Stabilize the React code app, its data-source contract, accessibility, ALM path, licensing requirements, and support model before changing its unsupported-preview status.
- **Exit criteria:** A clean-sandbox installation and upgrade path are documented, automated checks cover the supported workflow, and the public package is no longer described as unsupported.
- **Tracking:** [Release automation](docs/release-automation.md) and the [code app source](codeapp/)

### Expand governance only as documented APIs allow

- **Status:** Discovery
- **Goal:** Evaluate additional control surfaces without conflating source facts with billing allocation or granting browser-side licensing authority.
- **Exit criteria:** Each new mutation has a documented API contract, narrow authorization boundary, stale-state protection, before/after audit, and rollback guidance.
- **Tracking:** [Copilot Credit reporting](docs/credit-reporting.md)

## Explicitly out of scope for the current product boundary

These are not silently forgotten backlog items:

- Per-user Copilot Studio limit controls, because no documented API exposes them.
- Exact credit allocation to a transcript, evaluation, tool call, or user-agent pair.
- Environment allocation, `TenantPool`, or PayGo mutation.
- Treating unavailable cross-environment metadata as evidence that an agent does not exist.
- Claiming the `2.0.0.5` candidates are shipped or TPM-validated before the manual upgrade gate
  completes.

Changes to this boundary require product evidence, documentation review, versioned managed-package
upgrades, and a new release entry in [CHANGELOG.md](CHANGELOG.md).

## How to update this roadmap

1. Add a concrete item with a status, goal, exit criteria, and tracking link.
2. Move completed work to [CHANGELOG.md](CHANGELOG.md) in the same change that updates the public page.
3. Keep unsupported or unavailable capabilities in the explicit out-of-scope section until evidence and implementation exist.
4. Review this file during every versioned release and record the review in the pull request.
