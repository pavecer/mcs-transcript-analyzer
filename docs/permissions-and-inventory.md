# Permissions and tenant inventory

## What the managed solution includes

The stable `2.1.0.0` release retains the package ownership introduced in `2.0.0.5` without moving
the security or data model. Core and code app are `2.1.0.0`; Credits remains unchanged at `2.0.0.5`.
Required `pvConversationInsights` core still owns all four roles, all tables, plugins, Custom APIs,
the model-driven app, and transcript/inventory runtime. Optional `pvConversationInsightsCredits`
owns only the three credit flows and `pvci_licensinghttp` plus `pvci_powerplatformapi`. Optional
`pvConversationInsightsCodeApp` owns only the supported code app and its declared dependencies. It
remains separate for optional installation and an independent application lifecycle. PVE validation is complete;
the user-performed manual Contoso TPM upgrade passed.

The current source contract includes four least-privilege Dataverse application roles. All are mapped
to the model-driven app and apply to the same Dataverse data sources used by the code app:

- **PVCI Analyst** provides organization-level read access to transcript, flow, inventory, credit,
   capacity, threshold, governance-health, privacy-status, and sync tables. Analysts can read names
   after disclosure is approved, but cannot change approval, stored identities, or platform limits.
- **PVCI Privacy Approver** has the same read access plus organization-level write on
   `pvci_creditprivacysetting` and `pvci_credituserusage`, and read on `systemuser`. These privileges
   let the synchronous disclosure plug-in record the initiating user/time and resolve or revoke all
   stored names.
- **PVCI Credit Administrator** has Analyst read access plus organization-level write on
   `pvci_environmentinventory` for collector enablement, and create/read with the narrow append
   privileges required to bind audited threshold and transcript-access requests. It cannot update
   request outcomes or call licensing APIs directly.
- **PVCI Source Access Processor** has only the app-opening baseline plus read/write/append on
   `pvci_transcriptaccessrequest` and read/write on Environment Inventory. Assign it to the
   verification flow owner, not to ordinary report viewers.

The optional supported code app must still be shared with users or groups through **Manage access**. App
sharing grants the app shell; one of the packaged Dataverse roles grants its additional data
access. Assign ordinary readers **PVCI Analyst** and only authorized approvers **PVCI Privacy
Approver**. Do not grant System Administrator to report viewers.

There are three independent permission boundaries:

| Purpose | Required identity and access | Packaged by the solution? |
| --- | --- | --- |
| Import and configure PVCI | Installer with **System Administrator** in the target Dataverse environment | No; assign in the target environment |
| Collect Copilot Credit usage | Owner of `pvci_licensinghttp` with the Power Platform administrative access accepted by the licensing service, plus a premium Power Automate entitlement | No; the connection is target-local |
| Read and write PVCI data | Owner of `pvci_dataversesync` with access to the PVCI tables and Custom APIs in the collector environment | No; the connection is target-local |
| Enumerate tenant environments and base agents | Owner of `pvci_powerplatformadminv2` with **Power Platform Administrator** tenant role | Flow and reference packaged; target connection/role external |
| Probe source `conversationtranscripts` tables | Probe identity with a Dataverse-scoped token and Read privilege in each source organization | No source solution installation required |
| Collect enabled source transcripts | Owner of `pvci_centralcollector`, present in each enabled source with organization-level Read on Conversation Transcript | Flow/reference packaged; source role assignment external |
| Enable or disable a reviewed transcript source | **PVCI Credit Administrator** plus code-app sharing | Role and Environment Inventory table packaged; assignment external |
| Submit and inspect source verification | **PVCI Credit Administrator** plus code-app sharing | Request table and stopped-by-default verifier packaged; source role assignment external |
| Process source verification results | Owner of `PVCI Verify Transcript Source Access (scheduled)` with **PVCI Source Access Processor** and the mapped `pvci_centralcollector` connection | Flow and processor role packaged; target connection/assignment external |
| Read agent credit threshold controls | Owner of `pvci_powerplatformapi` with Power Platform licensing administration access | Read-only collector/reference packaged; target connection/role external |
| Submit agent threshold changes | **PVCI Credit Administrator** plus app sharing | Role/request table/processor packaged; privileged flow connection external |
| Read detailed agent configuration in every environment | Inventory identity with appropriate Dataverse access in every source environment | Detailed enrichment not implemented in `1.3.0.0` |
| Open the apps as an analyst | **PVCI Analyst** plus model-driven/code-app sharing | Role packaged; assignments and code-app sharing external |
| Reveal or revoke stored user names | **PVCI Privacy Approver** plus app sharing | Role and audited plug-in packaged; assignment external |

Do not assign Global Administrator for routine collection. Use a dedicated account, the least
privileged roles that satisfy the required scope, and Privileged Identity Management where your
organization supports it.

For transcript-only operation, install core without the credit add-on. No licensing HTTP
connection, licensing-administrator access, credit flow ownership, or premium HTTP entitlement is
required for transcript analysis. The model-driven Credits navigation can remain visible because
the schema remains in core, but capability is unavailable until the add-on exists. If the add-on is
installed, its documented licensing permissions still apply; the capability remains setup-required
until a successful credit sync proves runtime readiness.

## Assign the external roles

### Tenant inventory identity

An administrator assigns the dedicated inventory/collector account the **Power Platform
Administrator** role in Microsoft Entra ID or the Microsoft 365 admin center. This role allows the
[Power Platform for Admins connector](https://learn.microsoft.com/connectors/powerplatformforadmins/)
to list tenant environments and retrieve the tenant-level base inventory available to that
identity.

If the account already has an active Power Platform Administrator assignment, do not assign a
second role. Verify instead that the Power Automate connection references are bound to that exact
account. An administrator opening PPAC in a browser does not lend their permissions to a flow that
uses another connection owner. Re-authenticate or recreate the connection after a role change when
its existing token does not reflect the assignment.

Power Platform Administrator does not grant detailed Dataverse table access in every environment.
For detailed agent metadata, an administrator must separately add the same account to each source
environment and assign **System Administrator**:

1. Open the Power Platform admin center.
2. Select **Manage** > **Environments** and open a source environment.
3. Open **Settings** > **Users + permissions** > **Users**.
4. Select or add the dedicated account, choose **Manage security roles**, and assign **System
   Administrator**.
5. Repeat for every environment whose `bot`, `botcomponent`, process, owner, and transcript
   metadata should be enriched.

This broad cross-environment role is the same boundary documented by Copilot Agent Kit: tenant
base inventory can be broader, while detailed feature metadata is available only where its
Dataverse connection has System Administrator access.

The same boundary applies to transcript discovery. The Power Platform admin inventory can tell the
collector that an environment exists, but it cannot by itself grant Read access to that
organization's `conversationtranscripts` table. Phase 1 records an explicit `access_denied` result
for those environments so an empty result is never mistaken for missing activity.

The scheduled central collector uses the identity behind `pvci_centralcollector`, which may differ
from the identity used by other inventory tooling. Add that connection owner to the source
environment and assign a least-privilege role with organization-level Read on **Conversation
Transcript**. In the code app's **Inventory Management** page, choose **Source-managed** and submit
**Verify access**. The packaged verification flow performs a one-row ID-only source probe and writes
the audited result. A failed probe records `access_denied` and keeps collection disabled; repair the
source assignment and submit a new verification request. `ThrowCrmSecurityException` naming
`prvReadconversationtranscript` proves that this source role is missing; it is not fixed by changing
the collector-environment PVCI roles. In the TPM upgrade-test tenant, the user performs this role
assignment and connection refresh manually.

Restricted environments do not require System Administrator onboarding. In **Source-managed** mode,
the source owner creates or approves a `PVCI Transcript Collector` role, assigns it to the dedicated
collector identity, and returns to **Inventory Management** to verify access. Where organizational
policy permits temporary elevation, **Administrator bootstrap** can instead submit an audited
provisioning request to an external reconciler. That control is disabled in the current UI until
the reconciler exists. Both modes must finish with the same least-privilege role and no retained
System Administrator. **Excluded** records a deliberate policy decision and turns collection off.

Inventory Management is the sole configuration surface for these choices. It must show onboarding
mode and lifecycle state independently from transcript probe state and collector enablement. A
successful role assignment does not enable collection automatically; the operator reviews the
verification result and enables collection separately. The enable confirmation is also the explicit
data-movement consent: remote transcript data is copied into and retained by the collector
Dataverse environment. Turning the source off stops subsequent imports and does not delete data
already copied. Sessions, Trends, and Credits resource reporting stay scoped to the host environment,
and their environment selectors remain hidden, until a remote collector is enabled. Credit user usage
and recent governance request history remain tenant-wide.
Ordinary users of the code app are never
added to source environments merely because they can view collector data.

See the Copilot Agent Kit references for its
[inventory architecture](https://github.com/microsoft/Power-CAT-Copilot-Studio-Kit/blob/main/AGENT_INVENTORY.md)
and [field-level data sources](https://github.com/microsoft/Power-CAT-Copilot-Studio-Kit/blob/main/AGENT_INVENTORY_DATA_SOURCE.md).

### Collector environment

Before a fresh install that includes the optional code app, set **Power Apps Code Apps > Enable
code apps** to **On** in the exact target, save, and independently reload the setting before any
solution import. Grouped Managed Environments must also have the effective, published Code Apps
group rule enabled. The complete mandatory/conditional policy matrix is in the
[clean-install runbook](clean-install.md).

For a clean `2.1.0.0` installation, import core, optional credits, then optional code app. For an
upgrade from stable `2.0.0.5`, upgrade core and the optional code app without reimporting unchanged
Credits. For a
manual upgrade from `1.4.0.15`, import credits first, apply the core managed upgrade second, and
upgrade the code app last. This preserves existing credit workflow identities while transferring
their solution ownership additively. Do not perform TPM imports or connection changes through
automation.

In the environment where PVCI is installed:

1. Assign the installer **System Administrator** while importing and configuring the solution.
2. Create `pvci_licensinghttp` with **HTTP with Microsoft Entra ID (preauthorized)**. For commercial
   cloud, set both resource URLs to `https://licensing.powerplatform.microsoft.com/`.
3. Create `pvci_powerplatformadminv2` with **Power Platform for Admins V2** and bind it to the
   dedicated Power Platform Administrator account.
4. Create `pvci_powerplatformapi` with **HTTP with Microsoft Entra ID (preauthorized)**. Set both
   resource URLs to `https://licensing.powerplatform.microsoft.com/` and bind it to the dedicated
   licensing administrator account. The governance route is tenant-scoped and uses the same
   licensing audience as the usage collector; keep the physical connection target explicit.
5. Create `pvci_dataversesync` with Microsoft Dataverse and bind all solution connection
   references to the intended dedicated account.
6. When the optional credit add-on is installed, set the current value of
   `pvci_CreditReportingTenantId` to the tenant GUID. Core does not own or require this definition.
   Do not put a tenant-specific default or current value in either managed solution.
7. Confirm DLP and Advanced Connector Policies allow Microsoft Dataverse, HTTP with Microsoft
   Entra ID, and Power Platform for Admins V2 in the collector environment.
8. Save all three collectors, run each manually, and activate recurrence only after all three
   smoke tests pass.
9. Keep `PVCI Apply Credit Governance Requests (scheduled)` stopped until an empty-queue run and
   a no-op threshold request both succeed with identical before/after control values.

### First-import connection wizard

The managed solution cannot package physical connections or credentials. On a first import, Power
Apps can display an automatically created **HTTP with Microsoft Entra ID (preauthorized)** entry as
`Invalid connection` with a blank `BaseResourceUrl`. That entry is incomplete and must not be bound
to either licensing reference.

For commercial cloud, resolve the connection page as follows:

1. In the import wizard, open the menu beside **PVCI Licensing API** and choose **Add new
   connection**.
2. Create **HTTP with Microsoft Entra ID (preauthorized)**. Enter this exact value in both fields:

   ```text
   Base Resource URL:                https://licensing.powerplatform.microsoft.com/
   Microsoft Entra ID Resource URI:  https://licensing.powerplatform.microsoft.com/
   ```

3. Sign in with the dedicated identity that has the Power Platform licensing administration access
   required by the licensing service and a premium Power Automate entitlement.
4. Return to the import wizard. Refresh the connection list if the new connection is not visible.
5. Select the new valid connection for **PVCI Licensing API** (`pvci_licensinghttp`).
6. Select the same connection for **PVCI Power Platform API** (`pvci_powerplatformapi`) when the
   same identity owns usage collection and governance. Both references call
   `licensing.powerplatform.microsoft.com`; the second display name does not mean
   `api.powerplatform.com`. Use two separately created physical connections only when ownership or
   operational separation requires it, and configure both with the same two licensing URLs.
7. Keep **PVCI Power Platform Admin V2** mapped to a separate **Power Platform for Admins V2**
   connection. Map both Dataverse references to the intended Microsoft Dataverse connection.
8. Continue the import only after all five rows show green checks.

If **Add new connection** is blocked or the completed connection remains invalid, verify that the
environment's DLP and Advanced Connector Policies allow **HTTP with Microsoft Entra ID
(preauthorized)** and that the signing-in account has a premium Power Automate entitlement. Delete
or ignore the incomplete blank-URL connection under **Power Automate > Data > Connections**; it
cannot be repaired by selecting it again in the import wizard. For sovereign clouds, use the
licensing-service audience documented for that cloud instead of the commercial-cloud URL.

## Understand the current inventory boundary

The credit collector calls three licensing projections:

- resource usage for agent/resource credit facts;
- tenant-wide user usage;
- environment capacity.

These are billing projections, not inventory. The separate `PVCI Collect Tenant Agent Inventory
(scheduled)` flow reads Power Platform for Admins V2 environment inventory and PPAC One Inventory
agent resources. It persists environments independently of activity and enriches exact matching
billing resources while retaining unresolved billing-only rows.

Copilot Agent Kit obtains broader visibility through separate sources:

1. Power Platform for Admins / Power Platform for Admins V2 lists environments.
2. PPAC One Inventory supplies tenant-level base agent metadata, including display name and
   environment ID, for agents not readable inside an environment.
3. Microsoft Dataverse reads `bot`, `botcomponent`, process, owner, and related tables in each
   environment where the connection identity has System Administrator.
4. The licensing endpoint supplies usage metrics independently.

PVCI `1.3.0.0` implements items 1, 2, and 4. Item 3 remains future work: the current inventory
records `Has Detailed Access = No` rather than pretending unavailable feature metadata means “no
agent.” Base inventory, environment names, and agent names do not require activity or local
Dataverse access in every source environment.

## Diagnose capacity or users with zero resource facts

The state shown as capacity rows or user rows with zero agents/resources proves that the flow can
authenticate, invoke the importer, and write Dataverse. It does not prove that the resource
projection returned rows.

Open the latest `PVCI Collect Copilot Credit Usage (scheduled)` run, expand **Until usage
complete**, open the first iteration, and inspect **Get usage page** > **Outputs** > **Body**. Do
not use **Get user usage** for this check: that is the separate tenant-wide user projection and can
succeed even when no resource facts are returned.

| Result | Meaning | Action |
| --- | --- | --- |
| `401` or `403` | Licensing connection identity lacks accepted access or consent | Recreate/re-authenticate `pvci_licensinghttp` with the intended admin account |
| `200` and `resources` is empty | No reportable resource facts in the seven-day query window, or the service exposes none to that identity | Compare the same period in PPAC; do not infer inventory from capacity |
| `200` with resource rows, but PVCI remains empty | Import/parser defect | Preserve the action output with identifiers removed and report the schema shape |
| Capacity contains only some environments | Expected for a capacity projection | Use Admin V2/One Inventory for complete tenant enumeration |

Also confirm that the flow connection owner, not merely the person viewing PPAC in the browser, has
the required role. Power Automate runs with the identities bound to its connection references.

## Assign application users

1. Share the model-driven app with users or groups and assign **PVCI Analyst**, **PVCI Privacy
   Approver**, or **PVCI Credit Administrator** according to duty.
2. Share the code app separately through **Apps** > **Manage access**. The sharing dialog lists its
   Dataverse data sources; users still need one of the same packaged roles.
3. Give **PVCI Privacy Approver** only to users authorized to disclose names. The app confirmation
   is not the security boundary; Dataverse write privilege is.
4. Verify the Privacy Approval record after every reveal/revoke. `Approved By`, `Approved On`, and
   `Revoked On` are stamped by the server-side plug-in, not trusted from the browser.
5. Give **PVCI Credit Administrator** only to collection and threshold-change operators. The role
   can enable reviewed Environment Inventory rows and create/read threshold requests, but cannot
   update processor outcomes or call the licensing API from the browser.

Tenant Power Platform Administrator and future per-environment detailed-enrichment access remain
external because a managed Dataverse solution cannot grant tenant or other-environment roles.
