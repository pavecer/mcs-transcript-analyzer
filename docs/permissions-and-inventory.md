# Permissions and tenant inventory

## What the managed solution includes

Version `1.1.0.0` does **not** include a dedicated PVCI Dataverse security role. The managed
solution installs tables, apps, plug-ins, Custom APIs, connection references, and flows, but it
cannot grant tenant-level Microsoft Entra roles or access to other Dataverse environments.

The model-driven app currently maps to the built-in **System Administrator** and **System
Customizer** role templates. Those mappings permit administration but are not an acceptable
least-privilege analyst model. The preview code app must be shared separately and every user still
needs Dataverse table privileges.

There are three independent permission boundaries:

| Purpose | Required identity and access | Packaged by the solution? |
| --- | --- | --- |
| Import and configure PVCI | Installer with **System Administrator** in the target Dataverse environment | No; assign in the target environment |
| Collect Copilot Credit usage | Owner of `pvci_licensinghttp` with the Power Platform administrative access accepted by the licensing service, plus a premium Power Automate entitlement | No; the connection is target-local |
| Read and write PVCI data | Owner of `pvci_dataversesync` with access to the PVCI tables and Custom APIs in the collector environment | No; the connection is target-local |
| Enumerate all tenant environments | **Power Platform Administrator** tenant role through Power Platform for Admins V2 | Not implemented in `1.1.0.0` |
| Read detailed agent configuration in every environment | The inventory connection identity must also have **System Administrator** in every source Dataverse environment | Not implemented in `1.1.0.0` |
| Open the apps as an analyst | App sharing plus read access to the PVCI tables | No dedicated least-privilege role in `1.1.0.0` |

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
3. Create `pvci_dataversesync` with Microsoft Dataverse and bind both solution connection
   references to the intended dedicated account.
4. Set the current value of `pvci_CreditReportingTenantId` to the tenant GUID. Do not put a
   tenant-specific default value in the managed solution.
5. Confirm DLP and Advanced Connector Policies allow Microsoft Dataverse and HTTP with Microsoft
   Entra ID in the collector environment.
6. Save the credit collector, run it manually, and activate the recurrence only after the smoke
   test passes.

## Understand the current inventory boundary

The `1.1.0.0` collector calls three licensing projections:

- resource usage for agent/resource credit facts;
- tenant-wide user usage;
- environment capacity.

These are billing projections, not a complete Power Platform inventory. Environment choices come
from observed resource rows and capacity snapshots. Environments with neither result are absent.
Agent names exist only when the resource projection supplies `metadata.ResourceName`; otherwise the
resource GUID remains the label.

Copilot Agent Kit obtains broader visibility through separate sources:

1. Power Platform for Admins / Power Platform for Admins V2 lists environments.
2. PPAC One Inventory supplies tenant-level base agent metadata, including display name and
   environment ID, for agents not readable inside an environment.
3. Microsoft Dataverse reads `bot`, `botcomponent`, process, owner, and related tables in each
   environment where the connection identity has System Administrator.
4. The licensing endpoint supplies usage metrics independently.

PVCI `1.1.0.0` implements item 4 only. Assigning the external roles now prepares the correct
identity, but it does not add items 1-3 to the installed flow. A future inventory collector must
add the Admin V2/One Inventory connection references, persist environment inventory independently
of usage, and enrich agent rows without treating missing detailed access as “no agent.”

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

## Current role gap

Until dedicated least-privilege PVCI roles are added and tested, administrators must create their
own analyst role with organization-level read access to the required `pvci_*` tables and share the
apps with that role, or temporarily use an appropriate existing administrative role in a sandbox.
Do not grant System Administrator to ordinary report viewers as a permanent workaround.

Planned packaged roles should be split by duty:

- **PVCI Analyst**: read-only access to reporting tables and apps;
- **PVCI Privacy Approver**: Analyst plus update on `pvci_creditprivacysetting`;
- **PVCI Collector**: minimum Custom API and table privileges needed by the two flow connections.

Tenant Power Platform Administrator and per-environment System Administrator remain external even
after those PVCI roles are packaged.
