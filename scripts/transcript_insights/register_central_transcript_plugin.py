#!/usr/bin/env python3
"""Register the bounded central transcript batch-import Custom API."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config  # noqa: E402
from register_plugin import ASSEMBLY_NAME, BOOLEAN, INTEGER, STRING, Dv  # noqa: E402


PLUGIN_TYPE = "PvciTranscripts.ImportCentralTranscriptBatch"
API_UNIQUE = "pvci_ImportCentralTranscriptBatch"

REQUEST_PARAMS = [
    ("PayloadJson", "Dataverse transcript List rows response", STRING, False),
    ("SourceTenantId", "Source tenant ID", STRING, False),
    ("SourceEnvironmentId", "Source Power Platform environment ID", STRING, False),
    ("SourceEnvironmentName", "Source environment display name", STRING, False),
    ("SourceDataverseUrl", "Source Dataverse organization URL", STRING, False),
    ("SourceSchemaVersion", "Source schema version", STRING, True),
    ("DryRun", "Validate without writing", BOOLEAN, True),
    ("IncludeTraces", "Include trace activities", BOOLEAN, True),
    ("Reprocess", "Rewrite already imported transcripts", BOOLEAN, True),
]

RESPONSE_PROPS = [
    ("Created", "Sessions created", INTEGER),
    ("Updated", "Sessions updated", INTEGER),
    ("Skipped", "Sessions skipped", INTEGER),
    ("TurnsCreated", "Turns created", INTEGER),
    ("Status", "Import status", STRING),
    ("Watermark", "Source watermark", STRING),
    ("Errors", "Bounded import errors", STRING),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--assembly", default="plugin/bin/Release/net462/plugin.dll")
    args = parser.parse_args()

    token, dv_url = get_token_from_config(args.config)
    dv = Dv(f"{dv_url}/api/data/v9.1", token)
    assembly = dv.find("pluginassemblies", f"name eq '{ASSEMBLY_NAME}'", "pluginassemblyid,name")
    if not assembly:
        raise SystemExit("Plugin assembly is not registered; run register_plugin.py first.")
    assembly_id = assembly["pluginassemblyid"]
    assembly_path = Path(args.assembly)
    if not assembly_path.exists():
        raise SystemExit(f"Assembly not found: {assembly_path}")
    dv.update(
        "pluginassemblies",
        assembly_id,
        {"content": base64.b64encode(assembly_path.read_bytes()).decode("ascii")},
    )
    print(f"pluginassembly updated: {assembly_id}")

    existing_type = dv.find("plugintypes", f"typename eq '{PLUGIN_TYPE}'", "plugintypeid,typename")
    if existing_type:
        plugin_type_id = existing_type["plugintypeid"]
    else:
        plugin_type_id = dv.create("plugintypes", {
            "typename": PLUGIN_TYPE,
            "friendlyname": "Import Central Transcript Batch",
            "name": PLUGIN_TYPE,
            "pluginassemblyid@odata.bind": f"/pluginassemblies({assembly_id})",
        })
    print(f"plugintype: {plugin_type_id}")

    existing_api = dv.find("customapis", f"uniquename eq '{API_UNIQUE}'", "customapiid,uniquename")
    if existing_api:
        api_id = existing_api["customapiid"]
    else:
        api_id = dv.create("customapis", {
            "uniquename": API_UNIQUE,
            "name": API_UNIQUE,
            "displayname": "Import Central Transcript Batch",
            "description": "Imports a bounded source-environment transcript batch with composite idempotency.",
            "bindingtype": 0,
            "isfunction": False,
            "isprivate": False,
            "allowedcustomprocessingsteptype": 0,
            "PluginTypeId@odata.bind": f"/plugintypes({plugin_type_id})",
        })
    print(f"customapi: {api_id}")

    for unique, display, parameter_type, optional in REQUEST_PARAMS:
        found = dv.find(
            "customapirequestparameters",
            f"uniquename eq '{unique}' and _customapiid_value eq {api_id}",
            "customapirequestparameterid,uniquename",
        )
        if not found:
            dv.create("customapirequestparameters", {
                "uniquename": unique,
                "name": unique,
                "displayname": display,
                "type": parameter_type,
                "isoptional": optional,
                "CustomAPIId@odata.bind": f"/customapis({api_id})",
            })
        print(f"  parameter: {unique}")

    for unique, display, property_type in RESPONSE_PROPS:
        found = dv.find(
            "customapiresponseproperties",
            f"uniquename eq '{unique}' and _customapiid_value eq {api_id}",
            "customapiresponsepropertyid,uniquename",
        )
        if not found:
            dv.create("customapiresponseproperties", {
                "uniquename": unique,
                "name": unique,
                "displayname": display,
                "type": property_type,
                "CustomAPIId@odata.bind": f"/customapis({api_id})",
            })
        print(f"  response: {unique}")

    print(json.dumps({
        "status": "ok",
        "pluginType": plugin_type_id,
        "customApi": api_id,
        "invoke": f"POST {dv_url}/api/data/v9.1/{API_UNIQUE}",
    }, indent=2))


if __name__ == "__main__":
    main()