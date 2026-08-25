#!/usr/bin/env python3
"""Register the Copilot credit batch-import Custom API in the existing solution."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config, require_authorized_config  # noqa: E402
from register_plugin import BOOLEAN, INTEGER, STRING, ASSEMBLY_NAME, Dv  # noqa: E402


SOLUTION = "pvConversationInsights"
PLUGIN_TYPE = "PvciTranscripts.ImportCreditUsageBatch"
DISCLOSURE_PLUGIN_TYPE = "PvciTranscripts.CreditUserDisclosure"
REQUEST_GUARD_PLUGIN_TYPE = "PvciTranscripts.ThresholdChangeRequestGuard"
API_UNIQUE = "pvci_ImportCreditUsageBatch"
PRIVACY_SETTING_KEY = "credit-user-disclosure"
PRIVACY_STATEMENT = (
    "Enabling this setting resolves stored Copilot Credit source user IDs to Dataverse user names "
    "for authorized reporting users. The approval is shared by the code app and model-driven app, "
    "is audited, and can be revoked to remove resolved names."
)

REQUEST_PARAMS = [
    ("PayloadJson", "Normalized credit usage payload", STRING, False),
    ("SourceSchemaVersion", "Source schema version", STRING, True),
    ("DryRun", "Validate without writing", BOOLEAN, True),
]

RESPONSE_PROPS = [
    ("Created", "Records created", INTEGER),
    ("Updated", "Records updated", INTEGER),
    ("Skipped", "Records skipped", INTEGER),
    ("Rejected", "Records rejected", INTEGER),
    ("Status", "Import status", STRING),
    ("Errors", "Bounded import errors", STRING),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--assembly", default="plugin/bin/Release/net462/plugin.dll")
    args = parser.parse_args()
    require_authorized_config(args.config)

    token, dv_url = get_token_from_config(args.config)
    dv = Dv(f"{dv_url}/api/data/v9.1", token)

    assembly = dv.find("pluginassemblies", f"name eq '{ASSEMBLY_NAME}'", "pluginassemblyid,name")
    if not assembly:
        raise SystemExit("Plugin assembly is not registered; run register_plugin.py first.")
    assembly_id = assembly["pluginassemblyid"]
    assembly_path = Path(args.assembly)
    if not assembly_path.exists():
        raise SystemExit(f"Assembly not found: {assembly_path} (run the Release build first).")
    dv.update(
        "pluginassemblies",
        assembly_id,
        {"content": base64.b64encode(assembly_path.read_bytes()).decode("ascii")},
    )
    print(f"pluginassembly updated: {assembly_id}")

    existing = dv.find("plugintypes", f"typename eq '{PLUGIN_TYPE}'", "plugintypeid,typename")
    if existing:
        plugin_type_id = existing["plugintypeid"]
        print(f"plugintype exists: {plugin_type_id}")
    else:
        plugin_type_id = dv.create(
            "plugintypes",
            {
                "typename": PLUGIN_TYPE,
                "friendlyname": "Import Copilot Credit Usage Batch",
                "name": PLUGIN_TYPE,
                "pluginassemblyid@odata.bind": f"/pluginassemblies({assembly_id})",
            },
        )
        print(f"plugintype created: {plugin_type_id}")

    disclosure = dv.find("plugintypes", f"typename eq '{DISCLOSURE_PLUGIN_TYPE}'", "plugintypeid,typename")
    if disclosure:
        disclosure_type_id = disclosure["plugintypeid"]
        print(f"disclosure plugintype exists: {disclosure_type_id}")
    else:
        disclosure_type_id = dv.create(
            "plugintypes",
            {
                "typename": DISCLOSURE_PLUGIN_TYPE,
                "friendlyname": "Apply Credit User Name Disclosure",
                "name": DISCLOSURE_PLUGIN_TYPE,
                "pluginassemblyid@odata.bind": f"/pluginassemblies({assembly_id})",
            },
        )
        print(f"disclosure plugintype created: {disclosure_type_id}")

    request_guard = dv.find("plugintypes", f"typename eq '{REQUEST_GUARD_PLUGIN_TYPE}'", "plugintypeid,typename")
    if request_guard:
        request_guard_type_id = request_guard["plugintypeid"]
        print(f"request guard plugintype exists: {request_guard_type_id}")
    else:
        request_guard_type_id = dv.create(
            "plugintypes",
            {
                "typename": REQUEST_GUARD_PLUGIN_TYPE,
                "friendlyname": "Guard Threshold Change Request Create",
                "name": REQUEST_GUARD_PLUGIN_TYPE,
                "pluginassemblyid@odata.bind": f"/pluginassemblies({assembly_id})",
            },
        )
        print(f"request guard plugintype created: {request_guard_type_id}")

    existing = dv.find("customapis", f"uniquename eq '{API_UNIQUE}'", "customapiid,uniquename")
    if existing:
        api_id = existing["customapiid"]
        print(f"customapi exists: {api_id}")
    else:
        api_id = dv.create(
            "customapis",
            {
                "uniquename": API_UNIQUE,
                "name": API_UNIQUE,
                "displayname": "Import Copilot Credit Usage Batch",
                "description": "Validates and idempotently imports normalized Copilot credit reporting facts.",
                "bindingtype": 0,
                "isfunction": False,
                "isprivate": False,
                "allowedcustomprocessingsteptype": 0,
                "PluginTypeId@odata.bind": f"/plugintypes({plugin_type_id})",
            },
        )
        print(f"customapi created: {api_id}")

    for unique, display, parameter_type, optional in REQUEST_PARAMS:
        found = dv.find(
            "customapirequestparameters",
            f"uniquename eq '{unique}' and _customapiid_value eq {api_id}",
            "customapirequestparameterid,uniquename",
        )
        if found:
            print(f"  param exists: {unique}")
            continue
        dv.create(
            "customapirequestparameters",
            {
                "uniquename": unique,
                "name": unique,
                "displayname": display,
                "type": parameter_type,
                "isoptional": optional,
                "CustomAPIId@odata.bind": f"/customapis({api_id})",
            },
        )
        print(f"  param created: {unique}")

    for unique, display, property_type in RESPONSE_PROPS:
        found = dv.find(
            "customapiresponseproperties",
            f"uniquename eq '{unique}' and _customapiid_value eq {api_id}",
            "customapiresponsepropertyid,uniquename",
        )
        if found:
            print(f"  response exists: {unique}")
            continue
        dv.create(
            "customapiresponseproperties",
            {
                "uniquename": unique,
                "name": unique,
                "displayname": display,
                "type": property_type,
                "CustomAPIId@odata.bind": f"/customapis({api_id})",
            },
        )
        print(f"  response created: {unique}")

    update_message = dv.find("sdkmessages", "name eq 'Update'", "sdkmessageid,name")
    if not update_message:
        raise SystemExit("Dataverse Update SDK message was not found.")
    update_filter = dv.find(
        "sdkmessagefilters",
        f"_sdkmessageid_value eq {update_message['sdkmessageid']} and primaryobjecttypecode eq 'pvci_creditprivacysetting'",
        "sdkmessagefilterid,primaryobjecttypecode",
    )
    if not update_filter:
        raise SystemExit("Update message filter for pvci_creditprivacysetting was not found; publish the table first.")
    step_name = "PVCI Apply Credit User Name Disclosure"
    step = dv.find("sdkmessageprocessingsteps", f"name eq '{step_name}'", "sdkmessageprocessingstepid,name")
    if step:
        print(f"disclosure step exists: {step['sdkmessageprocessingstepid']}")
    else:
        step_id = dv.create(
            "sdkmessageprocessingsteps",
            {
                "name": step_name,
                "description": "Resolves or clears credit user names after the shared approval changes.",
                "mode": 0,
                "rank": 1,
                "stage": 40,
                "supporteddeployment": 0,
                "filteringattributes": "pvci_revealusernames",
                "eventhandler_plugintype@odata.bind": f"/plugintypes({disclosure_type_id})",
                "sdkmessageid@odata.bind": f"/sdkmessages({update_message['sdkmessageid']})",
                "sdkmessagefilterid@odata.bind": f"/sdkmessagefilters({update_filter['sdkmessagefilterid']})",
            },
        )
        print(f"disclosure step created: {step_id}")

    create_message = dv.find("sdkmessages", "name eq 'Create'", "sdkmessageid,name")
    if not create_message:
        raise SystemExit("Dataverse Create SDK message was not found.")
    create_filter = dv.find(
        "sdkmessagefilters",
        f"_sdkmessageid_value eq {create_message['sdkmessageid']} and primaryobjecttypecode eq 'pvci_thresholdchangerequest'",
        "sdkmessagefilterid,primaryobjecttypecode",
    )
    if not create_filter:
        raise SystemExit("Create message filter for pvci_thresholdchangerequest was not found; publish the table first.")
    guard_step_name = "PVCI Guard Threshold Change Request Create"
    guard_step = dv.find("sdkmessageprocessingsteps", f"name eq '{guard_step_name}'", "sdkmessageprocessingstepid,name")
    if guard_step:
        print(f"request guard step exists: {guard_step['sdkmessageprocessingstepid']}")
    else:
        guard_step_id = dv.create(
            "sdkmessageprocessingsteps",
            {
                "name": guard_step_name,
                "description": "Validates request inputs and reserves status and audit fields for the privileged processor.",
                "mode": 0,
                "rank": 1,
                "stage": 20,
                "supporteddeployment": 0,
                "eventhandler_plugintype@odata.bind": f"/plugintypes({request_guard_type_id})",
                "sdkmessageid@odata.bind": f"/sdkmessages({create_message['sdkmessageid']})",
                "sdkmessagefilterid@odata.bind": f"/sdkmessagefilters({create_filter['sdkmessagefilterid']})",
            },
        )
        print(f"request guard step created: {guard_step_id}")

    privacy = dv.find(
        "pvci_creditprivacysettings",
        f"pvci_settingkey eq '{PRIVACY_SETTING_KEY}'",
        "pvci_creditprivacysettingid,pvci_revealusernames",
    )
    if privacy:
        print(f"privacy setting exists: {privacy['pvci_creditprivacysettingid']}")
    else:
        privacy_id = dv.create(
            "pvci_creditprivacysettings",
            {
                "pvci_name": "Credit user name disclosure",
                "pvci_settingkey": PRIVACY_SETTING_KEY,
                "pvci_revealusernames": False,
                "pvci_approvalstatement": PRIVACY_STATEMENT,
            },
        )
        print(f"privacy setting created: {privacy_id}")

    print(
        json.dumps(
            {
                "status": "ok",
                "pluginType": plugin_type_id,
                "customApi": api_id,
                "disclosurePluginType": disclosure_type_id,
                "requestGuardPluginType": request_guard_type_id,
                "privacySettingKey": PRIVACY_SETTING_KEY,
                "invoke": f"POST {dv_url}/api/data/v9.1/{API_UNIQUE}",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()