#!/usr/bin/env python3
"""Build operator-focused main forms for Copilot credit reporting tables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import create_forms as forms  # noqa: E402
from dv_token import get_token_from_config  # noqa: E402

SOLUTION = "pvConversationInsights"
ENTITIES = (
    "pvci_environmentinventory",
    "pvci_inventorysyncrun",
    "pvci_agentinventory",
    "pvci_creditusage",
    "pvci_creditcapacitysnapshot",
    "pvci_creditsyncrun",
    "pvci_credituserusage",
    "pvci_creditprivacysetting",
)
DECIMAL = "{C3EFE0C3-0EC6-42be-8349-CBD9079DFD8E}"


def agent_form() -> str:
    identity = forms.section(
        "ai_identity",
        "Agent or resource",
        forms.row(forms.field_cell("ai_name", "pvci_name", forms.TEXT, "Name"),
                  forms.field_cell("ai_display", "pvci_displayname", forms.TEXT, "Display name"))
        + forms.row(forms.field_cell("ai_resource", "pvci_resourceid", forms.TEXT, "Resource ID"),
                    forms.field_cell("ai_bot", "pvci_botid", forms.TEXT, "Bot ID"))
        + forms.row(forms.field_cell("ai_type", "pvci_resourcetype", forms.TEXT, "Resource type"),
                    forms.field_cell("ai_published", "pvci_published", forms.BOOL, "Published"))
        + forms.row(forms.field_cell("ai_status", "pvci_agentstatus", forms.TEXT, "Agent status"),
                forms.field_cell("ai_detail", "pvci_hasdetailedaccess", forms.BOOL, "Detailed access"))
        + forms.row(forms.field_cell("ai_schema", "pvci_schemaname", forms.TEXT, "Schema name"),
                    forms.field_cell("ai_model", "pvci_model", forms.TEXT, "Model")),
    )
    classification = forms.section(
        "ai_classification",
        "Harness classification",
        forms.row(forms.field_cell("ai_harness", "pvci_harness", forms.TEXT, "Harness"),
                  forms.field_cell("ai_confidence", "pvci_classificationconfidence", forms.TEXT, "Confidence"))
        + forms.row(forms.field_cell("ai_source", "pvci_classificationsource", forms.TEXT, "Classification source"),
                    forms.field_cell("ai_origin", "pvci_authoringorigin", forms.TEXT, "Authoring origin"))
        + forms.row(forms.field_cell("ai_orchestration", "pvci_orchestrationtype", forms.TEXT, "Orchestration type"),
                    forms.field_cell("ai_inventory", "pvci_inventorysource", forms.TEXT, "Inventory source")),
    )
    environment = forms.section(
        "ai_environment",
        "Environment and lineage",
        forms.row(forms.field_cell("ai_envname", "pvci_environmentname", forms.TEXT, "Environment"),
                  forms.field_cell("ai_envid", "pvci_environmentid", forms.TEXT, "Environment ID"))
        + forms.row(forms.field_cell("ai_envurl", "pvci_environmenturl", forms.TEXT, "Environment URL"),
                    forms.field_cell("ai_envtype", "pvci_environmenttype", forms.TEXT, "Environment type"))
        + forms.row(forms.field_cell("ai_location", "pvci_location", forms.TEXT, "Location"),
                    forms.field_cell("ai_tenant", "pvci_tenantid", forms.TEXT, "Tenant ID"))
        + forms.row(forms.field_cell("ai_created", "pvci_createdonsource", forms.DATE, "Agent created"),
                    forms.field_cell("ai_published_on", "pvci_publishedonsource", forms.DATE, "Agent published"))
        + forms.row(forms.field_cell("ai_auth", "pvci_authenticationmode", forms.TEXT, "Authentication mode"),
                    forms.field_cell("ai_env_lookup", "pvci_environmentinventoryid", forms.LOOKUP, "Environment inventory"))
        + forms.row(forms.field_cell("ai_synced", "pvci_lastsyncedon", forms.DATE, "Last synced"),
                    forms.field_cell("ai_key", "pvci_sourcekey", forms.TEXT, "Source key")),
    )
    evidence = forms.section(
        "ai_evidence",
        "Classification evidence",
        forms.row(forms.field_cell("ai_evidence_json", "pvci_evidencejson", forms.MEMO, "Evidence JSON",
                                   rowspan=28, pcf=True, depth=4, height=620)),
        columns="1",
    )
    return f"<form><tabs>{forms.tab('ai_summary', 'Summary', identity + classification + environment)}{forms.tab('ai_evidence_tab', 'Evidence', evidence)}</tabs>{forms.control_descriptions()}</form>"


def environment_form() -> str:
    identity = forms.section(
        "ei_identity",
        "Environment",
        forms.row(forms.field_cell("ei_name", "pvci_name", forms.TEXT, "Name"),
                  forms.field_cell("ei_display", "pvci_displayname", forms.TEXT, "Display name"))
        + forms.row(forms.field_cell("ei_id", "pvci_environmentid", forms.TEXT, "Environment ID"),
                    forms.field_cell("ei_tenant", "pvci_tenantid", forms.TEXT, "Tenant ID"))
        + forms.row(forms.field_cell("ei_url", "pvci_environmenturl", forms.TEXT, "Dataverse URL"),
                    forms.field_cell("ei_type", "pvci_environmenttype", forms.TEXT, "Environment type"))
        + forms.row(forms.field_cell("ei_geo", "pvci_geo", forms.TEXT, "Geo"),
                    forms.field_cell("ei_region", "pvci_azureregion", forms.TEXT, "Azure region"))
        + forms.row(forms.field_cell("ei_state", "pvci_state", forms.TEXT, "State"),
                    forms.field_cell("ei_managed", "pvci_ismanaged", forms.BOOL, "Managed environment"))
        + forms.row(forms.field_cell("ei_dataverse", "pvci_hasdataverse", forms.BOOL, "Has Dataverse"),
                    forms.field_cell("ei_detailed", "pvci_hasdetailedaccess", forms.BOOL, "Detailed access")),
    )
    lineage = forms.section(
        "ei_lineage",
        "Inventory lineage",
        forms.row(forms.field_cell("ei_source", "pvci_inventorysource", forms.TEXT, "Inventory source"),
                  forms.field_cell("ei_schema", "pvci_sourceschemaversion", forms.TEXT, "Schema version"))
        + forms.row(forms.field_cell("ei_synced", "pvci_lastsyncedon", forms.DATE, "Last synced"),
                    forms.field_cell("ei_key", "pvci_sourcekey", forms.TEXT, "Source key")),
    )
    raw = forms.section(
        "ei_raw",
        "Raw source record",
        forms.row(forms.field_cell("ei_raw_json", "pvci_rawjson", forms.MEMO, "Raw source JSON",
                                   rowspan=30, pcf=True, depth=4, height=650)),
        columns="1",
    )
    return f"<form><tabs>{forms.tab('ei_summary', 'Environment', identity + lineage)}{forms.tab('ei_raw_tab', 'Raw Source', raw)}</tabs>{forms.control_descriptions()}</form>"


def inventory_sync_form() -> str:
    run = forms.section(
        "is_run",
        "Inventory collector run",
        forms.row(forms.field_cell("is_name", "pvci_name", forms.TEXT, "Name"),
                  forms.field_cell("is_status", "pvci_status", forms.TEXT, "Status"))
        + forms.row(forms.field_cell("is_source", "pvci_source", forms.TEXT, "Source"),
                    forms.field_cell("is_schema", "pvci_schemaversion", forms.TEXT, "Schema version"))
        + forms.row(forms.field_cell("is_started", "pvci_startedon", forms.DATE, "Started"),
                    forms.field_cell("is_completed", "pvci_completedon", forms.DATE, "Completed"))
        + forms.row(forms.field_cell("is_envs", "pvci_environmentcount", forms.INT, "Environments"),
                    forms.field_cell("is_agents", "pvci_agentcount", forms.INT, "Agents"))
        + forms.row(forms.field_cell("is_created", "pvci_createdcount", forms.INT, "Created"),
                    forms.field_cell("is_updated", "pvci_updatedcount", forms.INT, "Updated"))
        + forms.row(forms.field_cell("is_rejected", "pvci_rejectedcount", forms.INT, "Rejected"),
                    forms.field_cell("is_key", "pvci_runkey", forms.TEXT, "Run key")),
    )
    error = forms.section(
        "is_error",
        "Bounded errors",
        forms.row(forms.field_cell("is_error_text", "pvci_error", forms.MEMO, "Error", rowspan=18)),
        columns="1",
    )
    return f"<form><tabs>{forms.tab('is_summary', 'Run', run)}{forms.tab('is_error_tab', 'Errors', error)}</tabs></form>"


def usage_form() -> str:
    billing = forms.section(
        "cu_billing",
        "Authoritative usage fact",
        forms.row(forms.field_cell("cu_name", "pvci_name", forms.TEXT, "Name"),
                  forms.field_cell("cu_agent", "pvci_agentid", forms.LOOKUP, "Agent inventory"))
        + forms.row(forms.field_cell("cu_agentname", "pvci_agentname", forms.TEXT, "Agent or resource"),
                    forms.field_cell("cu_feature", "pvci_featurename", forms.TEXT, "Feature"))
        + forms.row(forms.field_cell("cu_billed", "pvci_billedcredits", DECIMAL, "Billed Copilot Credits"),
                    forms.field_cell("cu_nonbilled", "pvci_nonbilledcredits", DECIMAL, "Non-billed Copilot Credits"))
        + forms.row(forms.field_cell("cu_unit", "pvci_sourceunit", forms.TEXT, "Source unit"),
                    forms.field_cell("cu_entitlement", "pvci_entitlementid", forms.TEXT, "Entitlement")),
    )
    scope = forms.section(
        "cu_scope",
        "Period and attribution",
        forms.row(forms.field_cell("cu_date", "pvci_usagedate", forms.DATE, "Usage date"),
                  forms.field_cell("cu_from", "pvci_fromdate", forms.DATE, "From date"))
        + forms.row(forms.field_cell("cu_to", "pvci_todate", forms.DATE, "To date"),
                    forms.field_cell("cu_imported", "pvci_importedon", forms.DATE, "Imported"))
        + forms.row(forms.field_cell("cu_harness", "pvci_harness", forms.TEXT, "Harness"),
                    forms.field_cell("cu_resolution", "pvci_resolutionstatus", forms.TEXT, "Resolution status"))
        + forms.row(forms.field_cell("cu_type", "pvci_resourcetype", forms.TEXT, "Resource type"),
                    forms.field_cell("cu_channel", "pvci_channelid", forms.TEXT, "Channel"))
        + forms.row(forms.field_cell("cu_model", "pvci_llmmodel", forms.TEXT, "LLM model"),
                    forms.field_cell("cu_users", "pvci_users", forms.MEMO, "Users")),
    )
    lineage = forms.section(
        "cu_lineage",
        "Source lineage",
        forms.row(forms.field_cell("cu_env", "pvci_environmentid", forms.TEXT, "Environment ID"),
                  forms.field_cell("cu_resource", "pvci_resourceid", forms.TEXT, "Resource ID"))
        + forms.row(forms.field_cell("cu_tenant", "pvci_tenantid", forms.TEXT, "Tenant ID"),
                    forms.field_cell("cu_key", "pvci_sourcekey", forms.TEXT, "Source key"))
        + forms.row(forms.field_cell("cu_api", "pvci_sourceapi", forms.TEXT, "Source API"),
                    forms.field_cell("cu_schema", "pvci_sourceschemaversion", forms.TEXT, "Schema version")),
    )
    drivers = forms.section(
        "cu_drivers",
        "Driver detail",
        forms.row(forms.field_cell("cu_tool", "pvci_toolinvoked", forms.MEMO, "Tool invoked", rowspan=6))
        + forms.row(forms.field_cell("cu_knowledge", "pvci_knowledgesources", forms.MEMO, "Knowledge sources", rowspan=6)),
        columns="1",
    )
    raw = forms.section(
        "cu_raw",
        "Raw source record",
        forms.row(forms.field_cell("cu_raw_json", "pvci_rawjson", forms.MEMO, "Raw source JSON",
                                   rowspan=30, pcf=True, depth=4, height=650)),
        columns="1",
    )
    tabs = forms.tab("cu_summary", "Usage", billing + scope + lineage) + forms.tab("cu_drivers_tab", "Drivers", drivers) + forms.tab("cu_raw_tab", "Raw Source", raw)
    return f"<form><tabs>{tabs}</tabs>{forms.control_descriptions()}</form>"


def capacity_form() -> str:
    amounts = forms.section(
        "cc_amounts",
        "Capacity position",
        forms.row(forms.field_cell("cc_name", "pvci_name", forms.TEXT, "Name"),
                  forms.field_cell("cc_status", "pvci_status", forms.TEXT, "Status"))
        + forms.row(forms.field_cell("cc_entitled", "pvci_entitled", DECIMAL, "Entitled"),
                    forms.field_cell("cc_allocated", "pvci_allocated", DECIMAL, "Allocated"))
        + forms.row(forms.field_cell("cc_consumed", "pvci_consumed", DECIMAL, "Consumed"),
                    forms.field_cell("cc_available", "pvci_available", DECIMAL, "Available"))
        + forms.row(forms.field_cell("cc_auto", "pvci_autoallocated", DECIMAL, "Auto-allocated"),
                    forms.field_cell("cc_asof", "pvci_asofdate", forms.DATE, "As of"))
        + forms.row(forms.field_cell("cc_paygoe", "pvci_paygoentitled", DECIMAL, "PAYG entitled"),
                    forms.field_cell("cc_paygoc", "pvci_paygoconsumed", DECIMAL, "PAYG consumed")),
    )
    policy = forms.section(
        "cc_policy",
        "Allocation policy",
        forms.row(forms.field_cell("cc_pool", "pvci_drawfromtenantpool", forms.BOOL, "Draw from tenant pool"),
                  forms.field_cell("cc_alert", "pvci_alertenabled", forms.BOOL, "Alert enabled"))
        + forms.row(forms.field_cell("cc_threshold", "pvci_alertthreshold", DECIMAL, "Alert threshold"),
                    forms.field_cell("cc_captured", "pvci_capturedon", forms.DATE, "Captured")),
    )
    lineage = forms.section(
        "cc_lineage",
        "Environment and lineage",
        forms.row(forms.field_cell("cc_envname", "pvci_environmentname", forms.TEXT, "Environment"),
                  forms.field_cell("cc_envid", "pvci_environmentid", forms.TEXT, "Environment ID"))
        + forms.row(forms.field_cell("cc_tenant", "pvci_tenantid", forms.TEXT, "Tenant ID"),
                    forms.field_cell("cc_entitlement", "pvci_entitlementid", forms.TEXT, "Entitlement"))
        + forms.row(forms.field_cell("cc_api", "pvci_sourceapi", forms.TEXT, "Source API"),
                    forms.field_cell("cc_key", "pvci_sourcekey", forms.TEXT, "Source key")),
    )
    raw = forms.section(
        "cc_raw",
        "Raw capacity record",
        forms.row(forms.field_cell("cc_raw_json", "pvci_rawjson", forms.MEMO, "Raw source JSON",
                                   rowspan=30, pcf=True, depth=5, height=650)),
        columns="1",
    )
    return f"<form><tabs>{forms.tab('cc_summary', 'Capacity', amounts + policy + lineage)}{forms.tab('cc_raw_tab', 'Raw Source', raw)}</tabs>{forms.control_descriptions()}</form>"


def sync_form() -> str:
    timing = forms.section(
        "cs_timing",
        "Collector run",
        forms.row(forms.field_cell("cs_name", "pvci_name", forms.TEXT, "Name"),
                  forms.field_cell("cs_status", "pvci_status", forms.TEXT, "Status"))
        + forms.row(forms.field_cell("cs_source", "pvci_source", forms.TEXT, "Source"),
                    forms.field_cell("cs_schema", "pvci_schemaversion", forms.TEXT, "Schema version"))
        + forms.row(forms.field_cell("cs_started", "pvci_startedon", forms.DATE, "Started"),
                    forms.field_cell("cs_completed", "pvci_completedon", forms.DATE, "Completed"))
        + forms.row(forms.field_cell("cs_from", "pvci_fromdate", forms.DATE, "From date"),
                    forms.field_cell("cs_to", "pvci_todate", forms.DATE, "To date")),
    )
    counts = forms.section(
        "cs_counts",
        "Import result",
        forms.row(forms.field_cell("cs_pages", "pvci_pagecount", forms.INT, "Pages"),
                  forms.field_cell("cs_source_count", "pvci_sourcecount", forms.INT, "Source rows"))
        + forms.row(forms.field_cell("cs_created", "pvci_createdcount", forms.INT, "Created"),
                    forms.field_cell("cs_updated", "pvci_updatedcount", forms.INT, "Updated"))
        + forms.row(forms.field_cell("cs_skipped", "pvci_skippedcount", forms.INT, "Skipped"),
                    forms.field_cell("cs_rejected", "pvci_rejectedcount", forms.INT, "Rejected"))
        + forms.row(forms.field_cell("cs_key", "pvci_runkey", forms.TEXT, "Run key")),
    )
    error = forms.section(
        "cs_error",
        "Bounded errors",
        forms.row(forms.field_cell("cs_error_text", "pvci_error", forms.MEMO, "Error", rowspan=18)),
        columns="1",
    )
    return f"<form><tabs>{forms.tab('cs_summary', 'Run', timing + counts)}{forms.tab('cs_error_tab', 'Errors', error)}</tabs>{forms.control_descriptions()}</form>"


def user_usage_form() -> str:
    usage = forms.section(
        "uu_usage",
        "User consumption",
        forms.row(forms.field_cell("uu_name", "pvci_name", forms.TEXT, "Displayed user"),
                  forms.field_cell("uu_userid", "pvci_userid", forms.TEXT, "Source user ID"))
        + forms.row(forms.field_cell("uu_date", "pvci_usagedate", forms.DATE, "Usage date"),
                    forms.field_cell("uu_status", "pvci_nameresolutionstatus", forms.TEXT, "Name status"))
        + forms.row(forms.field_cell("uu_billed", "pvci_billedcredits", DECIMAL, "Billed Copilot Credits"),
                    forms.field_cell("uu_nonbilled", "pvci_nonbilledcredits", DECIMAL, "Non-billed Copilot Credits"))
        + forms.row(forms.field_cell("uu_from", "pvci_fromdate", forms.DATE, "From date"),
                    forms.field_cell("uu_to", "pvci_todate", forms.DATE, "To date"))
        + forms.row(forms.field_cell("uu_unit", "pvci_sourceunit", forms.TEXT, "Source unit"),
                    forms.field_cell("uu_entitlement", "pvci_entitlementid", forms.TEXT, "Entitlement")),
    )
    identity = forms.section(
        "uu_identity",
        "Resolved identity (visible only after shared approval)",
        forms.row(forms.field_cell("uu_display", "pvci_userdisplayname", forms.TEXT, "Display name"),
                  forms.field_cell("uu_upn", "pvci_userprincipalname", forms.TEXT, "User principal name"))
        + forms.row(forms.field_cell("uu_system", "pvci_systemuserid", forms.TEXT, "Dataverse system user ID")),
    )
    lineage = forms.section(
        "uu_lineage",
        "Source and contributing resources",
        forms.row(forms.field_cell("uu_resources", "pvci_resources", forms.MEMO, "Contributing resources", rowspan=8))
        + forms.row(forms.field_cell("uu_source", "pvci_sourceapi", forms.TEXT, "Source API"),
                    forms.field_cell("uu_schema", "pvci_sourceschemaversion", forms.TEXT, "Schema version"))
        + forms.row(forms.field_cell("uu_key", "pvci_sourcekey", forms.TEXT, "Source key"),
                    forms.field_cell("uu_imported", "pvci_importedon", forms.DATE, "Imported")),
    )
    return f"<form><tabs>{forms.tab('uu_summary', 'Consumption', usage + identity)}{forms.tab('uu_lineage_tab', 'Lineage', lineage)}</tabs></form>"


def privacy_form() -> str:
    approval = forms.section(
        "ps_approval",
        "Shared user-name disclosure approval",
        forms.row(forms.field_cell("ps_name", "pvci_name", forms.TEXT, "Setting", disabled=True))
        + forms.row(forms.field_cell("ps_statement", "pvci_approvalstatement", forms.MEMO, "Approval statement", rowspan=10, disabled=True))
        + forms.row(forms.field_cell("ps_reveal", "pvci_revealusernames", forms.BOOL, "Reveal user names")),
        columns="1",
    )
    audit = forms.section(
        "ps_audit",
        "Approval audit",
        forms.row(forms.field_cell("ps_by", "pvci_approvedbyname", forms.TEXT, "Changed by", disabled=True),
              forms.field_cell("ps_byid", "pvci_approvedbyid", forms.TEXT, "Changed by user ID", disabled=True))
        + forms.row(forms.field_cell("ps_approved", "pvci_approvedon", forms.DATE, "Approved on", disabled=True),
                forms.field_cell("ps_revoked", "pvci_revokedon", forms.DATE, "Revoked on", disabled=True))
        + forms.row(forms.field_cell("ps_key", "pvci_settingkey", forms.TEXT, "Setting key", disabled=True)),
    )
    return f"<form><tabs>{forms.tab('ps_summary', 'Privacy Approval', approval + audit)}</tabs></form>"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    args = parser.parse_args()
    token, dv_url = get_token_from_config(args.config)
    base = f"{dv_url}/api/data/v9.1"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "OData-Version": "4.0",
        "OData-MaxVersion": "4.0",
    }
    solution_headers = dict(headers, **{"MSCRM.SolutionUniqueName": SOLUTION})

    with requests.Session() as session:
        control = session.get(
            f"{base}/customcontrols?$select=name&$filter=endswith(name,'{forms.PCF_SUFFIX}')&$top=1",
            headers=headers,
            timeout=60,
        )
        controls = control.json().get("value", []) if control.ok else []
        if controls:
            forms.PCF_NAME = controls[0]["name"]
        else:
            forms.PCF_NAME = ""
            print("WARNING: JSON viewer control not found; raw fields use standard memo controls.")

        builders = {
            "pvci_environmentinventory": environment_form,
            "pvci_inventorysyncrun": inventory_sync_form,
            "pvci_agentinventory": agent_form,
            "pvci_creditusage": usage_form,
            "pvci_creditcapacitysnapshot": capacity_form,
            "pvci_creditsyncrun": sync_form,
            "pvci_credituserusage": user_usage_form,
            "pvci_creditprivacysetting": privacy_form,
        }
        for entity, builder in builders.items():
            forms.reset_bindings()
            xml = builder()
            response = session.get(
                f"{base}/systemforms?$select=formid&$filter=objecttypecode eq '{entity}' and type eq 2&$top=1",
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()
            rows = response.json().get("value", [])
            if not rows:
                raise RuntimeError(f"No main form found for {entity}.")
            form_id = rows[0]["formid"]
            updated = session.patch(
                f"{base}/systemforms({form_id})",
                headers=solution_headers,
                json={"formxml": xml},
                timeout=180,
            )
            if not updated.ok:
                raise RuntimeError(f"{entity} form update failed: {updated.status_code} {updated.text[:600]}")
            print(f"{entity}: form updated ({len(xml)} chars, {len(forms._pcf_bindings)} JSON viewers)")

        publish = session.post(
            f"{base}/PublishXml",
            headers=headers,
            json={"ParameterXml": "<importexportxml><entities>" + "".join(
                f"<entity>{entity}</entity>" for entity in ENTITIES
            ) + "</entities></importexportxml>"},
            timeout=300,
        )
        if not publish.ok:
            raise RuntimeError(f"Publish failed: {publish.status_code} {publish.text[:600]}")
        print("publish: ok")


if __name__ == "__main__":
    main()