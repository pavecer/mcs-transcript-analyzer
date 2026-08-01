#!/usr/bin/env python3
"""Register the transcript sync plugin and its Custom API in Dataverse.

Creates (idempotently, into the solution):
  pluginassembly -> plugintype -> customapi -> request parameters -> response properties
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config  # noqa: E402

SOLUTION = "pvConversationInsights"
ASSEMBLY_NAME = "plugin"
PLUGIN_TYPE = "PvciTranscripts.SyncConversationTranscripts"
API_UNIQUE = "pvci_SyncConversationTranscripts"

# customapirequestparameter / customapiresponseproperty type codes
BOOLEAN, INTEGER, STRING = 0, 7, 10

REQUEST_PARAMS = [
    ("FullSync", "Full sync (ignore watermark)", BOOLEAN, True),
    ("MaxRecords", "Max records", INTEGER, True),
    ("IncludeTraces", "Include traces", BOOLEAN, True),
    ("Reprocess", "Rewrite already-ingested transcripts", BOOLEAN, True),
    ("SinceOverride", "Since override (ISO)", STRING, True),
]

RESPONSE_PROPS = [
    ("TranscriptsProcessed", "Transcripts processed", INTEGER),
    ("SessionsCreated", "Sessions created", INTEGER),
    ("SessionsUpdated", "Sessions updated", INTEGER),
    ("SessionsSkipped", "Sessions skipped (already ingested)", INTEGER),
    ("TurnsCreated", "Turns created", INTEGER),
    ("UsersResolved", "Users resolved", INTEGER),
    ("Anomalies", "Anomalies", INTEGER),
    ("Status", "Status", STRING),
    ("Watermark", "Watermark", STRING),
    ("Errors", "Errors", STRING),
]


class Dv:
    def __init__(self, base: str, token: str) -> None:
        self.base = base
        self.s = requests.Session()
        self.h = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "OData-Version": "4.0",
            "OData-MaxVersion": "4.0",
        }
        self.hs = dict(self.h, **{"MSCRM.SolutionUniqueName": SOLUTION})

    def find(self, entity_set: str, filt: str, select: str) -> dict[str, Any] | None:
        r = self.s.get(f"{self.base}/{entity_set}?$select={select}&$filter={filt}&$top=1", headers=self.h, timeout=90)
        if not r.ok:
            raise RuntimeError(f"GET {entity_set} -> {r.status_code} {r.text[:300]}")
        vals = r.json().get("value", [])
        return vals[0] if vals else None

    def create(self, entity_set: str, payload: dict[str, Any], in_solution: bool = True) -> str:
        r = self.s.post(f"{self.base}/{entity_set}", headers=self.hs if in_solution else self.h,
                        json=payload, timeout=180)
        if not r.ok:
            raise RuntimeError(f"POST {entity_set} -> {r.status_code} {r.text[:600]}")
        loc = r.headers.get("OData-EntityId") or r.headers.get("odata-entityid") or ""
        return loc.split("(")[-1].split(")")[0]

    def update(self, entity_set: str, rid: str, payload: dict[str, Any]) -> None:
        r = self.s.patch(f"{self.base}/{entity_set}({rid})", headers=self.hs, json=payload, timeout=180)
        if not r.ok:
            raise RuntimeError(f"PATCH {entity_set}({rid}) -> {r.status_code} {r.text[:600]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/transcript_solution_config.dev.json")
    ap.add_argument("--assembly", default="plugin/bin/Release/net462/plugin.dll")
    args = ap.parse_args()

    token, dv_url = get_token_from_config(args.config)
    dv = Dv(f"{dv_url}/api/data/v9.1", token)

    dll = Path(args.assembly)
    if not dll.exists():
        raise SystemExit(f"Assembly not found: {dll} (run: dotnet build -c Release in plugin/)")
    content = base64.b64encode(dll.read_bytes()).decode("ascii")
    print(f"assembly: {dll.name} ({dll.stat().st_size:,} bytes)")

    existing = dv.find("pluginassemblies", f"name eq '{ASSEMBLY_NAME}'", "pluginassemblyid,name,version")
    if existing:
        assembly_id = existing["pluginassemblyid"]
        dv.update("pluginassemblies", assembly_id, {"content": content})
        print(f"pluginassembly updated: {assembly_id}")
    else:
        assembly_id = dv.create("pluginassemblies", {
            "name": ASSEMBLY_NAME,
            "content": content,
            "isolationmode": 2,   # sandbox
            "sourcetype": 0,      # database
        })
        print(f"pluginassembly created: {assembly_id}")

    existing = dv.find("plugintypes", f"typename eq '{PLUGIN_TYPE}'", "plugintypeid,typename")
    if existing:
        plugin_type_id = existing["plugintypeid"]
        print(f"plugintype exists: {plugin_type_id}")
    else:
        plugin_type_id = dv.create("plugintypes", {
            "typename": PLUGIN_TYPE,
            "friendlyname": "Sync Conversation Transcripts",
            "name": PLUGIN_TYPE,
            "pluginassemblyid@odata.bind": f"/pluginassemblies({assembly_id})",
        })
        print(f"plugintype created: {plugin_type_id}")

    existing = dv.find("customapis", f"uniquename eq '{API_UNIQUE}'", "customapiid,uniquename")
    if existing:
        api_id = existing["customapiid"]
        print(f"customapi exists: {api_id}")
    else:
        api_id = dv.create("customapis", {
            "uniquename": API_UNIQUE,
            "name": API_UNIQUE,
            "displayname": "Sync Conversation Transcripts",
            "description": "Reads conversationtranscript rows and upserts transcript analytics tables.",
            "bindingtype": 0,                    # Global
            "isfunction": False,
            "isprivate": False,
            "allowedcustomprocessingsteptype": 0,  # None
            "PluginTypeId@odata.bind": f"/plugintypes({plugin_type_id})",
        })
        print(f"customapi created: {api_id}")

    for unique, display, ptype, optional in REQUEST_PARAMS:
        found = dv.find("customapirequestparameters",
                        f"uniquename eq '{unique}' and _customapiid_value eq {api_id}",
                        "customapirequestparameterid,uniquename")
        if found:
            print(f"  param exists: {unique}")
            continue
        dv.create("customapirequestparameters", {
            "uniquename": unique,
            "name": unique,
            "displayname": display,
            "type": ptype,
            "isoptional": optional,
            "CustomAPIId@odata.bind": f"/customapis({api_id})",
        })
        print(f"  param created: {unique}")

    for unique, display, ptype in RESPONSE_PROPS:
        found = dv.find("customapiresponseproperties",
                        f"uniquename eq '{unique}' and _customapiid_value eq {api_id}",
                        "customapiresponsepropertyid,uniquename")
        if found:
            print(f"  response exists: {unique}")
            continue
        dv.create("customapiresponseproperties", {
            "uniquename": unique,
            "name": unique,
            "displayname": display,
            "type": ptype,
            "CustomAPIId@odata.bind": f"/customapis({api_id})",
        })
        print(f"  response created: {unique}")

    print(json.dumps({
        "status": "ok",
        "assembly": assembly_id,
        "pluginType": plugin_type_id,
        "customApi": api_id,
        "invoke": f"POST {dv_url}/api/data/v9.1/{API_UNIQUE}",
    }, indent=2))


if __name__ == "__main__":
    main()
