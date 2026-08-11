# Copilot Credit reporting

## Current implementation

The existing `pvConversationInsights` solution collects read-only Copilot Credit usage and capacity
from the Power Platform licensing service. It covers Copilot Studio standard and GitHub Copilot
harness runtimes; it does not use the separate GitHub Copilot product billing APIs.

| Component | Current behavior |
| --- | --- |
| `PVCI Collect Copilot Credit Usage (scheduled)` | Runs daily, re-reads seven days, follows up to 20 pages of 100 resource rows, imports user rows in bounded 250-row chunks, and captures environment capacity |
| `pvci_ImportCreditUsageBatch` | Validates tenant scope, normalizes raw PPAC responses, computes stable keys, and idempotently imports bounded batches |
| `pvci_agentinventory` | One row per observed tenant, environment, and resource ID; harness remains `unknown` without verified evidence |
| `pvci_creditusage` | One row per source resource/period fact with billed and non-billed credits and optional driver dimensions |
| `pvci_creditcapacitysnapshot` | One row per environment, entitlement, and source as-of date |
| `pvci_creditsyncrun` | Collector freshness, combined user/resource/capacity import counts, status, schema version, and bounded errors |
| `pvci_credituserusage` | Separate user/source-period projection; source user GUID is the default label and no name is accepted from PPAC |
| `pvci_creditprivacysetting` | Singleton, default-off, shared and audited approval controlling server-side name resolution and revocation |
| Model-driven app | Agent, usage, user consumption, privacy approval, capacity, unresolved-resource, unknown-harness, and sync-run views/forms |
| Code app | Left-rail environment, agent/resource, and user navigator; credit totals, user consumption and approval, contribution, source-period trends, capacity, and data quality |

The licensing connection uses **HTTP with Microsoft Entra ID (preauthorized)**. For commercial
cloud, both its Base Resource URL and Microsoft Entra ID Resource URI are
`https://licensing.powerplatform.microsoft.com/`. The flow is solution-aware and binds through
`pvci_licensinghttp`. Its tenant path comes from the required
`pvci_CreditReportingTenantId` environment variable. The solution exports an empty default and no
current value, credentials, or physical connection ID; each target supplies those deployment
bindings during import.

## Supported reporting grain

The licensing APIs return aggregate reporting facts, not one billing event per conversation or
model call. Preserve the source period and do not distribute an aggregate across sessions or users.

### Agent and resource usage

The current collector calls:

```text
GET /v2.0/tenants/{tenantId}/entitlements/MCSMessages/resources
    ?fromDate={date}&toDate={date}&pageNumber={n}&pageSize=100&includeFields=users
```

Observed resource rows contain `resourceId`, optional `environmentId`, `asOfDate`, `consumed`,
`unit`, `metadata.ResourceName`, `metadata.NonBillableQuantity`, and optional `metadata.Users`.
This supports actual billed and non-billed totals by resource/agent and source date.

The captured responses demonstrate that the endpoint's date behavior depends on the projection:

- a 30-day request returned one aggregate snapshot date for each resource;
- a shorter request with `includeFields=users` returned resource rows at multiple dates;
- Microsoft Copilot Agent Kit documents its richer usage history as per-agent, per-feature, weekly,
  with `FromDate` and `ToDate` and up to 180 days of lookback.

Therefore the UI may group imported source facts by day or week, but must call them **source-period
buckets**. It must not claim guaranteed daily billing detail unless the returned source period is
daily. Weekly facts must remain weekly facts even if their `asOfDate` falls on one day.

### Tenant daily capacity trend

The observed endpoint below supplies tenant-level daily capacity values, not per-agent usage:

```text
GET /v1.0/tenants/{tenantId}/capacityTypes/MCSMessages/trends?interval=daily
```

It can support a daily tenant burn chart in a future collector, but it cannot be used to infer each
agent's daily charge.

## Per-user consumption

Per-user consumption is technically available from a separate projection:

```text
GET /v2.0/tenants/{tenantId}/entitlements/MCSMessages/users
    ?fromDate={date}&toDate={date}
```

The test-tenant capture returned nested user rows with:

- `userId`,
- `asOfDate`,
- billed `consumed`,
- `metadata.NonBillableQuantity`,
- `metadata.Resources`,
- source `unit`.

The projection does not include an environment ID. User totals are therefore tenant-wide even when
the resource and transcript views are scoped to one environment. This is not an
agent-user-event fact table. It can answer “how much was attributed to this user in the source
period?” and which resources contributed according to source metadata. It cannot prove which
individual conversation or action incurred a charge. The all-zero user ID can represent background
or non-human usage and must remain visible rather than being resolved to a person.

The scheduled collector now imports this projection into the separate organization-owned
`pvci_credituserusage` table. Privacy behavior is shared across both applications:

1. The importer stores only the source `userId` as the primary label by default. It ignores any
  caller-supplied display name, UPN, or Dataverse user ID.
2. The singleton `pvci_creditprivacysetting` row starts with `Reveal User Names = No`.
3. In the code app, **Reveal user names** shows an explicit confirmation dialog. In the
  model-driven app, an authorized user opens **Privacy Approval**, changes the same field to Yes,
  and saves the record after reading the approval statement.
4. A synchronous Dataverse plug-in records the initiating user and approval time, resolves source
  IDs against `systemuser.azureactivedirectoryobjectid`, and updates the user facts.
5. The all-zero source ID becomes `Background activity`; it is never resolved to a person.
6. Every re-import clears any stored display name, UPN, and linked system-user ID before applying
  the current approval and resolution result, so stale identity data cannot survive an unresolved
  or hidden transition. Revocation applies the same clearing behavior to every user fact.
7. Only security principals with update privilege on the privacy-setting row should be granted the
  ability to approve. The approval is tenant/environment-wide, not a browser-local preference.
8. Resource and user projections remain separate totals and must never be added together.

The code app follows the Sessions interaction pattern: the left rail contains search, environment
scope, selectable agent/resource cards, and tenant-wide selectable user cards. Agent selection
filters the environment-scoped credit KPIs and contribution charts. User selection filters the
tenant-wide user-consumption detail table. Both lists retain explicit **All** choices and show
compact totals/status so the main reporting pane can remain focused on analysis rather than
selectors. Dataverse usage, capacity, inventory, user, and transcript reads follow `skipToken`
until complete; the app fails explicitly instead of silently presenting a truncated global total.

The main pane is organized as a human-readable report with three non-overlapping bands:

1. **Global overview** always uses all resource facts in the selected environment and never changes
  when an agent or user is selected.
2. **Scoped analysis** contains only selected agent/user/combo credits, trends, correlation metrics,
  evidence boundaries, and the selected user's source rows.
3. **Operations** contains capacity, shared privacy approval, and collector health.

Selected agent and user credit trends use grouped source-period rows with separate billed and
non-billed lanes on one shared scale. This avoids hiding the billing split in a single total bar.
Major report and chart headers include keyboard-accessible hover/focus help that explains source
grain, attribution boundaries, and the intended interpretation without adding permanent instruction
text to the report.

Selected-agent and selected-user analysis keeps source truth separate:

- agent credit trends come from `pvci_creditusage`;
- user credit trends come from `pvci_credituserusage`;
- users observed with an agent, agents observed for a user, and user+agent trends come from exact
  transcript user-ID/bot-ID relationships and are labeled **Correlated, not allocated**;
- related-user credit bars show each user's total across all agents, and related-agent credit bars
  show each agent's total across all users; neither is presented as the selected pair's charge;
- PPAC currently supplies only resource/user counts in the opposite projection, not identifiers,
  so the solution never assigns aggregate user credits to a specific agent or vice versa.

When a selected billing resource has no exact transcript bot ID/name match, the UI shows the PPAC
reported user count but explains that identities and pair-level trends cannot be derived. Likewise,
selected users show PPAC's reported resource count even when those resource identities are absent.

Organizations still need an approved reporting purpose, retention policy, auditing, and role
design before enabling names outside the test tenant. The current implementation provides the
technical approval and revocation gate; environment administrators remain responsible for table
privileges and export controls.

## Reporting truth

| Label | Meaning |
| --- | --- |
| Actual | Billed or non-billed value imported directly from PPAC |
| Exact join | Environment and resource ID match one inventory agent |
| Correlated | A source period overlaps transcripts, tools, evaluations, or flow runs |
| Estimated | A documented allocation model distributes an aggregate; never a bill |
| Unresolved | The source resource cannot be matched without guessing |

No reviewed source currently exposes a billing-event identifier shared with a transcript turn.
Session-level “credits” can only be a clearly labeled estimate or period correlation.

## Known limitations and next work

- Harness remains `unknown` until a controlled standard-versus-GitHub-harness probe finds a stable,
  documented discriminator or an administrator supplies an audited override.
- The current resource endpoint does not guarantee daily agent facts for every query.
- Feature, channel, model, tool, and knowledge dimensions require the richer Agent Usage History
  projection or a completed PPAC report schema; missing dimensions are not inferred.
- Power Platform Admin V2 and One Inventory now provide tenant-wide base environment/agent
  metadata independently of usage. Per-environment `bot`/`botcomponent`, owner, and configuration
  enrichment remains future work and requires separately authorized source-environment access.
- A completed PPAC CSV capture is still required to validate report-only columns and correction
  behavior.
- User-name disclosure is a global setting; row-level/per-viewer approval is not implemented.

See [Cross-environment Copilot credit consumption](cross-environment-credit-consumption-design.md)
for evidence, architecture decisions, delivery phases, and source references.
