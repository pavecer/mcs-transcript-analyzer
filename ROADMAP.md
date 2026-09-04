# Roadmap

This roadmap describes product direction, not a promise of delivery dates. The public copy and
this file must agree about supported behavior and boundaries. Use the status and exit criteria to
keep work testable.

Last reviewed: 2026-08-28

## Shipped in 2.1.0.0

Core `2.1.0.0` and code app `2.1.0.0` shipped on 2026-08-28; Credits remains at stable
`2.0.0.5`. This mixed-version release is valid, and the core version defines the stable release
identity and announcement tag. The refresh workflow evaluates the fixed three-artifact
matrix independently, skips unchanged legs unless forced, and gives each changed artifact its own
export, validation, candidate manifest, and upload. Credits provenance resolves from its solution
and credit-specific scripts only, so unrelated core, parser, or configuration changes do not
advance it; it currently remains at the published stable source commit
`be33af99ae56ec4bf50e4334f94f47e96d918b31`. Exact retained core and code-app workflow artifacts
for package-input commit `89aa24423324d5b54600f837f018cdb22ade88e0` passed component and
tenant-neutral package validation and are the bytes promoted to stable. Semantically identical
candidates passed manual target-tenant upgrade over stable `2.0.0.5`. The failed first clean-install
launch from 2026-08-27 is superseded by a second brand-new Sandbox retry on 2026-08-28. Before any import, the
default-Off **Enable code apps** setting was saved and independently reloaded as On. Exact immutable
core `2.1.0.0`, unchanged Credits `2.0.0.5`, and code app `2.1.0.0` packages then imported from
scratch, synchronously and in order. Structural validation passed with 79 core, 6 Credits, and 1
code-app component, including all 18 required tables, 4 roles, 7 workflows, 5 connection references,
and 3 Custom APIs; the target-generated Code App record was active and managed. Connection placeholder
warnings remain target-local setup work, not import failures. Normal Power Apps launch no longer
returned HTTP 403 `CodeAppOperationNotAllowedInEnvironment`, and the exact runtime document returned
HTTP 200 and rendered Sessions, Trends, Inventory, and Credits. The shared VS Code browser still
aborted the cross-origin host iframe and left the fullscreen host hidden at `about:blank`; the same
signature reproduced against a previously healthy PVE app, isolating a shared-browser limitation.
Direct runtime loading lacks the parent host token, so this evidence proves structural clean
installation plus launch authorization/runtime asset delivery, not a full fresh authenticated
connector/data-tab smoke. The original Code Apps policy blocker is resolved and no longer blocks
the stable release. The published manifest records the exact promoted core and code-app bytes while
preserving the unchanged Credits bytes and provenance. In signed-in PVE Dev on 2026-08-27, the
full parser parity and runtime suites passed, all 38 code-app tests passed, and code-app lint and
build were green. Explicit local and alternate-source reprocessing now clears stale nullable
session values and the Dataverse user lookup when the corresponding evidence disappears.

Workday architecture is configured, but the available sessions are greeting-only. Representative
substantive Workday evidence remains a known gap, not a Conversation Investigation exit criterion.

The separate `pvConversationInsightsCodeApp` package is shipped as an optional supported code app.
Its clean-install and upgrade paths, automated checks, accessibility workflow, Premium licensing,
environment enablement, documented platform limitations, and maintainer support model are recorded
in the current product documentation.

### ESS structured runtime diagnostics

- **Status:** Shipped in `2.1.0.0` after PVE Dev parser/runtime and signed-in hosted failure-timeline validation, package validation, manual target-tenant upgrade, structural clean installation, and fresh-target launch authorization/runtime asset proof; a shared-browser iframe limitation prevents claiming a full fresh authenticated data-tab smoke
- **Goal:** Turn ESS topic/runtime failures into filterable session facts and an ordered operational timeline without requiring raw JSON inspection.
- **Exit criteria:** Local and central ingestion produce identical topic/error summaries; user-facing error traces survive default retention; core form/views and code app display the failure; changed candidate packages pass package validation and the manual target-tenant upgrade; and the hosted app completes a signed-in failure-timeline smoke without a Power Apps web-player host error.
- **Tracking:** [Architecture](docs/architecture.md), [data model](docs/data-model.md), and [operations](docs/operations.md)

### Knowledge retrieval diagnostics

- **Status:** Shipped in `2.1.0.0`; the signed-in PVE Dev Knowledge-tab smoke passed, including one `Answered` retrieval with one cited source, alongside package validation, manual target-tenant upgrade, structural clean installation, and fresh-target launch authorization/runtime asset proof; a shared-browser iframe limitation prevents claiming a full fresh authenticated data-tab smoke
- **Goal:** Make Universal Search and other knowledge retrievals visible independently from connector/tool calls, including completion, latency, cited sources, and failed source types.
- **Exit criteria:** Local and central ingestion agree on observed `KnowledgeTraceData`; model-driven and code apps show the same counts; the representative knowledge session reports one successful `Answered` retrieval and one cited source; no query text or retrieved passage is duplicated into summary JSON; changed candidate packages pass package validation and the manual target-tenant upgrade; and the hosted app completes a signed-in Knowledge-tab smoke without the Power Apps web-player host error.
- **Tracking:** [Architecture](docs/architecture.md), [data model](docs/data-model.md), and [operations](docs/operations.md)

### Conversation investigation usability

- **Status:** Shipped in `2.1.0.0`; the signed-in PVE Dev visual matrix passed simple/sparse, one-source Knowledge Answered, connector failure, expression failure, production and central unavailable telemetry, ServiceNow exact-tool and multiple-candidate-flow cases, Jira MCP planned-versus-exact evidence, filter/detail consistency, and availability-aware telemetry labels; package validation, manual target-tenant upgrade, structural clean installation, and fresh-target launch authorization/runtime asset proof also passed, while a shared-browser iframe limitation prevents claiming a full fresh authenticated data-tab smoke
- **Goal:** Let an operator understand context, outcome, routing, knowledge, tools, candidate flows, errors, and timing before opening technical payloads.
- **Exit criteria:** Overview is the default; filter and detail selections cannot disagree; zero is distinguished from unavailable telemetry; timing and correlation labels avoid false attribution; unknown flow states remain unknown; representative simple, knowledge, expression-failure, connector-failure, no-flow, and multiple-candidate sessions pass a signed-in visual smoke; and changed candidate packages pass package validation and the manual target-tenant upgrade.
- **Tracking:** [Operations interpretation guide](docs/operations.md) and the [code app](codeapp/)

### Agent reasoning visualization

- **Status:** Shipped in `2.1.0.0`; signed-in PVE Dev smokes passed for the Jira test plan and a production two-plan session at `1440x1000` and `390x844`, including geometry and screenshots; package validation, manual target-tenant upgrade, structural clean installation, and fresh-target launch authorization/runtime asset proof also passed, while a shared-browser iframe limitation prevents claiming a full fresh authenticated data-tab smoke
- **Goal:** Replace raw-first DynamicPlan inspection with a human-readable plan and step lifecycle while retaining exact evidence on demand.
- **Exit criteria:** Multi-plan and single-plan sessions group correctly; completed, incomplete, and Knowledge-answered steps are distinct; argument values remain behind raw evidence; representative test and production sessions pass signed-in desktop and mobile visual smokes; and the changed code-app candidate passes package validation and the manual target-tenant upgrade.
- **Tracking:** [Architecture reasoning model](docs/architecture.md), [operations](docs/operations.md), and `codeapp/src/components/ReasoningFlow.tsx`

## Now

### ESS HR Workday transcript privacy

- **Status:** In progress for code app `2.2.0.3` and not shipped. Read-only Contoso TPM structural inspection on 2026-09-03 confirmed substantive Workday PII repeated across retained activities, embedded Workday responses, tool output, planner observations, and turn text without recording source values. The code app now has a tenant-neutral exact-agent policy, recursive masked projection, always-masked JSON download, and fail-closed Privacy Approver reveal control. All 69 code-app tests, lint, build, PVE deployment, and non-HR desktop/narrow boundary validation pass; PVE has no representative HR row for the privacy-state visual smoke. The local managed candidate `output/candidate/pvConversationInsightsCodeApp-managed-2.2.0.3.zip` passed solution/version/component/dependency validation and contains the privacy feature markers; SHA-256 is `6f0c0d90e9d50941d8cf48f5416aa9b61bd3fea0929042c40d305a34a6776b20`. Its package inputs are still uncommitted, so no Git source-commit provenance or automated candidate-run evidence is claimed. Manual TPM import/validation and a server-enforced restricted raw-payload/audit boundary remain open.
- **Goal:** Prevent accidental disclosure of Workday employee data during normal transcript investigation and provide an export that remains masked regardless of on-screen reveal state.
- **Exit criteria:** Exact ESS HR Workday sessions are masked consistently across navigator, overview, replay, tool/knowledge/flow/reasoning evidence, and raw JSON; masked exports contain no synthetic fixture PII and remain independent of filters/reveal; ordinary analysts cannot reveal; approved privacy administrators must explicitly confirm reveal; PVE Dev passes signed-in `1440x1000` and `390x844` validation; changed artifacts pass candidate/package and manual target-tenant gates; and enforced raw-data authorization/audit limitations remain explicit until a core backend boundary ships.
- **Tracking:** [Operations guide](docs/operations.md), [permissions](docs/permissions-and-inventory.md), and the [code app](codeapp/)

### Telemetry flow operations workspace

- **Status:** In progress for code app `2.2.0.1`. The source now consolidates configuration readiness, health, last attempt/success, failure streak, duration regression, pending/overdue requests, and retained run evidence for all seven packaged flows; it adds review filters, visibility-aware auto-refresh, payload-free diagnostic copy, top-positioned review, direct maker links, and Inventory/Credits remediation. All 52 code-app tests, lint, build, PVE Dev redeployment, and direct deployed-asset checks pass at `1440x1000` and `390x844`, including filter counts, auto-refresh control, diagnostic copy, review ordering, local-only filter scrolling, and document/container geometry. The first `2.2.0.0` refresh exported successfully but package validation exposed that runtime-only system data sources were conflated with managed solution dependencies; `2.2.0.1` separates those contracts and adds regression coverage. Candidate run `33600510038` passed deployment, managed export, package validation, and upload for the code-app-only artifact `pvConversationInsightsCodeApp-managed-2.2.0.1.zip`; its source commit is `8635ae2ff5a028a6d936ddd29707b34de1850397` and SHA-256 is `4a03b8c3563a41dec9cdc394c7e76785a2e7f9fcdf06662c84132e98afcf7ea7`. The audited Run now backend contract is documented but intentionally not implemented against recurrence-only flows. The signed-in Power Apps shell still hides the runtime iframe at `0x0`, so representative authenticated configuration/run data states and manual target-tenant upgrade remain open.
- **Goal:** Let an operator identify failed or overdue telemetry collection, inspect recent retained evidence, and reach the correct remediation workspace without scanning separate pages or mistaking data refresh for flow execution.
- **Exit criteria:** All seven packaged flows appear with truthful freshness and availability states; observed zero remains distinct from unavailable; one failed, stale, optional-add-on-absent, loading, and empty/requestless state passes the signed-in PVE Dev matrix at `1440x1000` and `390x844`; the app never labels recurrence-only flows as directly invokable; and the changed code-app candidate passes package validation plus manual target-tenant upgrade.
- **Tracking:** [Operations guide](docs/operations.md) and the [code app](codeapp/)

### Tenant agent and session inventory

- **Status:** In progress for code app `2.2.0.2`. Inventory now lists discovered agents by environment, distinguishes Microsoft-reserved agents from user-created agents with direct creator evidence independently from managed deployment, filters authorship/deployment/collection state, exposes exact or clearly qualified candidate sessions only for collection-capable environments, and drills visible sessions into their full Sessions overview. All 64 code-app tests, lint, and build pass, including strict tenant/environment/Bot ID exact matching and an explicit session-loading state. The authenticated PVE Dev matrix covered 176 agents across 13 environments, three simultaneous User-created + Managed agents, environment drill-in, Microsoft-provided ESS candidate sessions, unavailable-source detail suppression, and session drill-through with filter reset at `1440x1000` and `390x844`. Candidate run `33654512447` passed main-branch deployment, managed export, package validation, and upload for `pvConversationInsightsCodeApp-managed-2.2.0.2.zip`; source commit `5f77e0536104c8372de7e7fb5dbdf16f50cfe108`, package SHA-256 `70e317c4e4218d49fdcdbc3300f7e01f1b6b344f22d4b88d1606b96163fe7a28`. The user approved the manual Contoso TPM test on 2026-09-03. Stable promotion remains blocked by the exact-byte clean-install gate: in a new authorized Sandbox, PPAC reported Saved twice but **Enable code apps** reverted to Off on reload, so no package was imported. Cleanup is complete: the delete request succeeded, the target disappeared from tenant inventory, and its Dataverse organization no longer resolves.
- **Goal:** Let analysts understand which tenant agents were discovered, where they live, which are user-created even after managed import, and where collected conversation evidence can be reviewed without overstating identity correlation or unavailable sources.
- **Exit criteria:** Duplicate environment/name resources remain distinct; user-created and managed states are independent; unavailable and observed-zero evidence remain distinct; exact, candidate, and ambiguous session matches are labeled truthfully; collection-ineligible environments reveal no session details; representative PVE agent/filter/session states pass desktop and narrow visual validation; and the changed code-app candidate passes package validation plus manual target-tenant upgrade.
- **Tracking:** [Permissions and inventory](docs/permissions-and-inventory.md#discovered-agent-inventory) and [operations](docs/operations.md#agent-inventory-and-collected-sessions)

### Audited telemetry flow execution

- **Status:** Design complete; implementation not started. The current seven collectors are recurrence-triggered and expose no supported shared execution unit or audited command surface.
- **Goal:** Let authorized operators queue a bounded, idempotent Run now request for an allowlisted packaged operation and observe the real resulting run without accepting arbitrary flow IDs or inputs.
- **Exit criteria:** Core-owned request schema and guard, Core/Credits-owned processors, shared scheduled/manual execution units, least-privilege roles, cooldown and duplicate prevention, crash recovery, bounded outcomes, code-app confirmation/reason/status UX, and PVE plus clean-install/upgrade evidence all pass; no undocumented test endpoint or runtime in the code-app solution is used.
- **Tracking:** [Audited Run now contract](docs/operations.md#audited-run-now-contract)

### Replace pre-authorized collection with zero-touch onboarding

- **Status:** Source-managed request/status backend, code-app workflow, and packaged verifier are implemented and smoke-tested in PVE Dev; external administrator-bootstrap reconciliation remains
- **Goal:** Support both source-managed least-privilege onboarding for restricted environments and optional administrator bootstrap where policy permits it, while converging on a dedicated collector identity with organization Read on Conversation Transcript and no retained System Administrator.
- **Exit criteria:** Inventory Management controls each environment's onboarding mode (`Source-managed`, `Administrator bootstrap`, or `Excluded`), exposes approval/setup/verification/cleanup state, and never offers unavailable automation. Source-managed environments can verify a locally assigned least-privilege role without elevation. Bootstrap environments are reconciled automatically, temporary System Administrator access is removed and proven removed, new environments are detected, and denied/unsupported environments remain explicit.
- **Tracking:** [Operations guide](docs/operations.md) and [permissions checklist](docs/permissions-and-inventory.md)

## Next

### Central transcript batch collector

- **Status:** Source-managed import, routing, and verified-only enablement shipped in `1.4.0.15`; signed-in PVE Dev central unavailable and no-flow telemetry validation passed on 2026-08-27, but automated administrator bootstrap remains incomplete
- **Goal:** Read transcripts from registry-approved source environments and import normalized sessions and turns into the collector environment through a bounded, idempotent Custom API.
- **Exit criteria:** PVE Preview to PVE Dev import/idempotent replay and generic-flow runs pass. Completion additionally requires automated least-privilege source onboarding; manual role assignment in every environment is not accepted as completion.
- **Tracking:** [Cross-environment design](docs/cross-environment-credit-consumption-design.md) and [architecture](docs/architecture.md)

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
- Claiming a release candidate is shipped or TPM-validated before its manual upgrade gate
  completes.

Changes to this boundary require product evidence, documentation review, versioned managed-package
upgrades, and a new release entry in [CHANGELOG.md](CHANGELOG.md).

## How to update this roadmap

1. Add a concrete item with a status, goal, exit criteria, and tracking link.
2. Move completed work to [CHANGELOG.md](CHANGELOG.md) in the same change that updates the public page.
3. Keep unsupported or unavailable capabilities in the explicit out-of-scope section until evidence and implementation exist.
4. Review this file during every versioned release and record the review in the pull request.
