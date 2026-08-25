---
name: Product Solution Boundaries
description: "Use for every Power Platform solution, flow, connection-reference, package, release, model-driven app, or code-app change in this repository."
applyTo: "{solution/**,scripts/**,plugin/**,codeapp/**,config/**,docs/**,README.md,ROADMAP.md,CHANGELOG.md,site/**,.github/skills/**,.github/agents/**}"
---

# Product Solution Boundaries

This repository has exactly two managed product solutions:

1. `pvConversationInsights` is the supported core solution. It owns every Dataverse table, plugin,
   Custom API, security role, model-driven app, connection reference, and supported cloud-flow
   runtime, including `PVCI Collect Central Transcripts (scheduled)`.
2. `pvConversationInsightsCodeApp` contains only the separate preview code app and its dependencies.
   It is separate because Power Apps code apps are preview, not because runtime components are
   optional or tenant-local.

Never create a third product solution. Never leave a supported product flow only in the default
solution or generate it outside the core solution after import.

The core package must remain tenant-neutral. The central collector must use one packaged Microsoft
Dataverse connection reference and the generally available selected-environment actions. Source
URLs, IDs, names, enablement, watermarks, and health are runtime rows in
`pvci_environmentinventory`; they are not hardcoded flow actions, environment variables, physical
connection IDs, or per-source connection references.

Post-import setup may require mapping packaged connection references, assigning roles, running the
tenant inventory, selecting supported environments, and turning packaged flows on. It must not
require creating the supported collector flow itself.

## Tenant Write Boundary

Programmatic Power Platform and Dataverse writes are allowed only in tenant
`1938ee32-a258-454c-b8db-3a928341bd69`, the development/test tenant. This includes solution
imports, upgrades, publishes, metadata changes, registrations, flow activation, connection-reference
updates, app pushes, and data writes.

Never programmatically change or import a solution into the TPM manual-upgrade tenant. TPM exists
so the user can test solution upgrades manually. Agents may prepare and validate tenant-neutral ZIPs
for TPM and may perform read-only verification there, but must stop before any write and hand the
artifacts to the user. Determine authorization from the authenticated tenant ID, never from a tenant
display name, environment name, URL label, account domain, or PAC profile alias. If the tenant ID
cannot be verified as `1938ee32-a258-454c-b8db-3a928341bd69`, treat the target as read-only.

Release validation must fail when:

- `PVCI Collect Central Transcripts (scheduled)` is absent from the core package;
- the flow appears outside `pvConversationInsights` as the supported deployment path;
- source tenant/environment names, IDs, URLs, or physical connection IDs are hardcoded in core;
- `pvci_transcript_http_*` or `pvci_transcript_source_*` per-source references appear;
- backend runtime is added to `pvConversationInsightsCodeApp`.
- automation can import or publish a candidate to an arbitrary target tenant.
