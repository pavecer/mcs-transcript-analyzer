#!/usr/bin/env python3
"""Create the scheduled cloud flow that drives pvci_SyncConversationTranscripts.

Creates a connection reference plus a recurrence flow that calls the Custom API in a
drain loop, so a backlog clears in one run instead of one batch per hour.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config, require_authorized_config  # noqa: E402

SOLUTION = "pvConversationInsights"
CONNECTOR_ID = "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps"
CONN_REF_LOGICAL = "pvci_dataversesync"
FLOW_NAME = "PVCI Sync Conversation Transcripts (scheduled)"
API_NAME = "pvci_SyncConversationTranscripts"
BATCH = 50


def build_clientdata(conn_ref_logical: str, frequency: str, interval: int) -> str:
    definition: dict[str, Any] = {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "parameters": {
            "$connections": {"defaultValue": {}, "type": "Object"},
            "$authentication": {"defaultValue": {}, "type": "SecureObject"},
        },
        "triggers": {
            "Recurrence": {
                "type": "Recurrence",
                "recurrence": {"frequency": frequency, "interval": interval},
                "metadata": {"operationMetadataId": "b1a0f0f1-0000-4000-8000-000000000001"},
            }
        },
        "actions": {
            "Initialise_batch_counter": {
                "type": "InitializeVariable",
                "runAfter": {},
                "inputs": {"variables": [{"name": "LastProcessed", "type": "integer", "value": BATCH}]},
            },
            "Until_backlog_drained": {
                "type": "Until",
                "runAfter": {"Initialise_batch_counter": ["Succeeded"]},
                # A short batch means nothing is left to read.
                "expression": f"@less(variables('LastProcessed'), {BATCH})",
                "limit": {"count": 12, "timeout": "PT1H"},
                "actions": {
                    "Sync_transcripts": {
                        "type": "OpenApiConnection",
                        "runAfter": {},
                        "inputs": {
                            "host": {
                                "apiId": CONNECTOR_ID,
                                "connectionName": "shared_commondataserviceforapps",
                                "operationId": "PerformUnboundAction",
                            },
                            "parameters": {
                                "actionName": API_NAME,
                                "item/MaxRecords": BATCH,
                                "item/FullSync": False,
                                "item/IncludeTraces": False,
                                "item/Reprocess": False,
                            },
                            "authentication": "@parameters('$authentication')",
                        },
                    },
                    "Record_batch_size": {
                        "type": "SetVariable",
                        "runAfter": {"Sync_transcripts": ["Succeeded"]},
                        "inputs": {
                            "name": "LastProcessed",
                            "value": "@body('Sync_transcripts')?['TranscriptsProcessed']",
                        },
                    },
                },
            },
        },
    }

    return json.dumps({
        "properties": {
            "connectionReferences": {
                "shared_commondataserviceforapps": {
                    "runtimeSource": "embedded",
                    "connection": {"connectionReferenceLogicalName": conn_ref_logical},
                    "api": {"name": "shared_commondataserviceforapps"},
                }
            },
            "definition": definition,
        },
        "schemaVersion": "1.0.0.0",
    })


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
        r.raise_for_status()
        vals = r.json().get("value", [])
        return vals[0] if vals else None

    def create(self, entity_set: str, payload: dict[str, Any]) -> str:
        r = self.s.post(f"{self.base}/{entity_set}", headers=self.hs, json=payload, timeout=180)
        if not r.ok:
            raise RuntimeError(f"POST {entity_set} -> {r.status_code} {r.text[:600]}")
        loc = r.headers.get("OData-EntityId") or r.headers.get("odata-entityid") or ""
        return loc.split("(")[-1].split(")")[0]

    def patch(self, entity_set: str, rid: str, payload: dict[str, Any], in_solution: bool = True) -> requests.Response:
        return self.s.patch(f"{self.base}/{entity_set}({rid})",
                            headers=self.hs if in_solution else self.h, json=payload, timeout=180)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/transcript_solution_config.dev.json")
    ap.add_argument("--connection-id", default=None,
                    help="Dataverse connection id to bind (default: auto-detect an existing one)")
    ap.add_argument("--frequency", default="Hour", choices=["Minute", "Hour", "Day"])
    ap.add_argument("--interval", type=int, default=1)
    ap.add_argument("--activate", action="store_true", help="Attempt to turn the flow on")
    args = ap.parse_args()
    require_authorized_config(args.config)

    token, dv_url = get_token_from_config(args.config)
    dv = Dv(f"{dv_url}/api/data/v9.1", token)

    connection_id = args.connection_id
    if not connection_id:
        existing = dv.find(
            "connectionreferences",
            f"connectorid eq '{CONNECTOR_ID}' and connectionid ne null",
            "connectionid,connectionreferencelogicalname",
        )
        if not existing:
            raise SystemExit("No connected Dataverse connection reference found. Pass --connection-id.")
        connection_id = existing["connectionid"]
        print(f"reusing connection: {connection_id}")

    ref = dv.find("connectionreferences",
                  f"connectionreferencelogicalname eq '{CONN_REF_LOGICAL}'",
                  "connectionreferenceid,connectionid")
    if ref:
        conn_ref_id = ref["connectionreferenceid"]
        print(f"connection reference exists: {CONN_REF_LOGICAL}")
    else:
        conn_ref_id = dv.create("connectionreferences", {
            "connectionreferencelogicalname": CONN_REF_LOGICAL,
            "connectionreferencedisplayname": "PVCI Dataverse (transcript sync)",
            "connectorid": CONNECTOR_ID,
            "connectionid": connection_id,
            "description": "Used by the scheduled transcript sync flow.",
        })
        print(f"connection reference created: {conn_ref_id}")

    clientdata = build_clientdata(CONN_REF_LOGICAL, args.frequency, args.interval)

    flow = dv.find("workflows", f"name eq '{FLOW_NAME}'", "workflowid,name,statecode")
    if flow:
        flow_id = flow["workflowid"]
        r = dv.patch("workflows", flow_id, {"clientdata": clientdata})
        print(f"flow updated: {flow_id} ({'ok' if r.ok else r.text[:300]})")
    else:
        flow_id = dv.create("workflows", {
            "name": FLOW_NAME,
            "description": f"Calls {API_NAME} every {args.interval} {args.frequency.lower()}(s), "
                           "looping until the backlog is drained.",
            "category": 5,        # Modern flow
            "type": 1,            # Definition
            "primaryentity": "none",
            "statecode": 0,       # Draft
            "clientdata": clientdata,
        })
        print(f"flow created: {flow_id}")

    if args.activate:
        r = dv.patch("workflows", flow_id, {"statecode": 1, "statuscode": 2}, in_solution=False)
        print("activate:", "ok" if r.ok else f"{r.status_code} {r.text[:400]}")

    print(json.dumps({
        "status": "ok",
        "flowId": flow_id,
        "connectionReference": CONN_REF_LOGICAL,
        "schedule": f"every {args.interval} {args.frequency.lower()}(s)",
        "editUrl": f"https://make.powerapps.com/environments/{json.loads(Path(args.config).read_text())['environmentId']}"
                   f"/flows/{flow_id}/details",
    }, indent=2))


if __name__ == "__main__":
    main()
