# Permissions and tenant inventory

## What the managed solution includes

Version `1.3.0.0` includes three least-privilege Dataverse application roles. All are mapped
to the model-driven app and apply to the same Dataverse data sources used by the code app:

- **PVCI Analyst** provides organization-level read access to transcript, flow, inventory, credit,
   capacity, threshold, governance-health, privacy-status, and sync tables. Analysts can read names
   after disclosure is approved, but cannot change approval, stored identities, or platform limits.
- **PVCI Privacy Approver** has the same read access plus organization-level write on
   `pvci_creditprivacysetting` and `pvci_credituserusage`, and read on `systemuser`. These privileges
   let the synchronous disclosure plug-in record the initiating user/time and resolve or revoke all
   stored names.
- **PVCI Credit Administrator** has Analyst read access plus create/read and the narrow append
   privileges required to bind audited requests to Agent Inventory. It cannot update outcomes or
   call licensing APIs directly.

The preview code app must still be shared with users or groups through **Manage access**. App
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
| Read agent credit threshold controls | Owner of `pvci_powerplatformapi` with Power Platform licensing administration access | Read-only collector/reference packaged; target connection/role external |
| Submit agent threshold changes | **PVCI Credit Administrator** plus app sharing | Role/request table/processor packaged; privileged flow connection external |
| Read detailed agent configuration in every environment | Inventory identity with appropriate Dataverse access in every source environment | Detailed enrichment not implemented in `1.3.0.0` |
| Open the apps as an analyst | **PVCI Analyst** plus model-driven/code-app sharing | Role packaged; assignments and code-app sharing external |
| Reveal or revoke stored user names | **PVCI Privacy Approver** plus app sharing | Role and audited plug-in packaged; assignment external |

Do not assign Global Administrator for routine collection. Use a dedicated account, the least
privileged roles that satisfy the required scope, and Privileged Identity Management where your
organization supports it.

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

See the Copilot Agent Kit references for its
[inventory architecture](https://github.com/microsoft/Power-CAT-Copilot-Studio-Kit/blob/main/AGENT_INVENTORY.md)
and [field-level data sources](https://github.com/microsoft/Power-CAT-Copilot-Studio-Kit/blob/main/AGENT_INVENTORY_DATA_SOURCE.md).

### Collector environment

In the environment where PVCI is installed:

1. Assign the installer **System Administrator** while importing and configuring the solution.
2. Create `pvci_licensinghttp` with **HTTP with Microsoft Entra ID (preauthorized)**. For commercial
   cloud, set both resource URLs to `https://licensing.powerplatform.microsoft.com/`.
3. Create `pvci_powerplatformadminv2` with **Power Platform for Admins V2** and bind it to the
   dedicated Power Platform Administrator account.
4. Create `pvci_powerplatformapi` with **HTTP with Microsoft Entra ID (preauthorized)**. Set both
   resource URLs to `https://api.powerplatform.com/` and bind it to the dedicated licensing
   administrator account. Do not reuse `pvci_licensinghttp`; the audiences differ.
5. Create `pvci_dataversesync` with Microsoft Dataverse and bind all solution connection
   references to the intended dedicated account.
6. Set the current value of `pvci_CreditReportingTenantId` to the tenant GUID. Do not put a
   tenant-specific default value in the managed solution.
7. Confirm DLP and Advanced Connector Policies allow Microsoft Dataverse, HTTP with Microsoft
   Entra ID, and Power Platform for Admins V2 in the collector environment.
8. Save all three collectors, run each manually, and activate recurrence only after all three
   smoke tests pass.
9. Keep `PVCI Apply Credit Governance Requests (scheduled)` stopped until an empty-queue run and
   a no-op threshold request both succeed with identical before/after control values.

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
5. Give **PVCI Credit Administrator** only to threshold-change operators. The role can create and
   read requests but cannot update processor outcomes or call the licensing API from the browser.

Tenant Power Platform Administrator and future per-environment detailed-enrichment access remain
external because a managed Dataverse solution cannot grant tenant or other-environment roles.
