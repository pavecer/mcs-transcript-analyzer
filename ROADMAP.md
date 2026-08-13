# Roadmap

This roadmap describes product direction, not a promise of delivery dates. The public copy and
this file must agree about supported behavior and boundaries. Use the status and exit criteria to
keep work testable.

Last reviewed: 2026-08-13

## Now

### Central transcript source discovery

- **Status:** Implemented and tenant-probed in PVE Dev and TPM
- **Goal:** Build a read-only tenant-wide source registry that uses the Power Platform admin inventory to test Dataverse transcript access per environment, without installing the solution into source environments.
- **Exit criteria:** Met. PVE and TPM probes distinguish readable-with-data, readable-empty, access-denied, and unavailable environments without copying transcript content. Both apps expose the persisted status.
- **Tracking:** [Operations guide](docs/operations.md), [architecture](docs/architecture.md), and `scripts/transcript_insights/probe_transcript_sources.py`

### Validate the 1.4.0.2 tenant rollout

- **Status:** Enabled-source-only candidate prepared; manual TPM upgrade validation required
- **Goal:** Import the core managed solution, optionally import the preview code app, and smoke-test all six packaged flows in a clean sandbox and a second test tenant.
- **Exit criteria:** The user manually imports the packages in TPM; connection references, target tenant environment variable, roles, DLP/ACP policy, flow runs, both apps, and upgrade behavior are recorded in the release checklist. Automated TPM imports do not count as upgrade evidence.
- **Tracking:** [Operations guide](docs/operations.md) and [permissions checklist](docs/permissions-and-inventory.md)

## Next

### Central transcript batch collector

- **Status:** Generic selected-environment flow packaged and validated in PVE Dev; corrected 1.4.0.2 candidate awaits a user-performed TPM upgrade test
- **Goal:** Read transcripts from registry-approved source environments and import normalized sessions and turns into the collector environment through a bounded, idempotent Custom API.
- **Exit criteria:** PVE Preview to PVE Dev import/idempotent replay and generic-flow runs pass. Completion requires the user to import the corrected candidate in TPM, map `pvci_centralcollector`, enable a supported source, and observe a packaged-flow collection run.
- **Tracking:** [Cross-environment design](docs/cross-environment-credit-consumption-design.md) and [architecture](docs/architecture.md)

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

Changes to this boundary require product evidence, documentation review, versioned managed-package
upgrades, and a new release entry in [CHANGELOG.md](CHANGELOG.md).

## How to update this roadmap

1. Add a concrete item with a status, goal, exit criteria, and tracking link.
2. Move completed work to [CHANGELOG.md](CHANGELOG.md) in the same change that updates the public page.
3. Keep unsupported or unavailable capabilities in the explicit out-of-scope section until evidence and implementation exist.
4. Review this file during every versioned release and record the review in the pull request.
