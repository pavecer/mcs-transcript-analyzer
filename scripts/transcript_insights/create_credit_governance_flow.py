#!/usr/bin/env python3
"""Create the read-only Copilot Credit governance snapshot flow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from create_sync_flow import Dv  # noqa: E402
from dv_token import get_token_from_config  # noqa: E402


SOLUTION = "pvConversationInsights"
FLOW_NAME = "PVCI Collect Credit Governance (scheduled)"
API_NAME = "pvci_ImportCreditUsageBatch"
HTTP_CONNECTOR = "/providers/Microsoft.PowerApps/apis/shared_webcontents"
DATAVERSE_CONNECTOR = "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps"
HTTP_REF_LOGICAL = "pvci_powerplatformapi"
DATAVERSE_REF_LOGICAL = "pvci_dataversesync"
TENANT_VARIABLE_SCHEMA = "pvci_CreditReportingTenantId"
TENANT_PARAMETER = f"{TENANT_VARIABLE_SCHEMA} ({TENANT_VARIABLE_SCHEMA})"
SCHEMA_VERSION = "power-platform-resource-threshold-v1"
THRESHOLD_PATH = "/v1.0/tenants/{tenantId}/entitlements/MCSMessages/resourceThresholds"


def build_definition() -> dict[str, Any]:
    tenant_expression = f"parameters('{TENANT_PARAMETER}')"
    threshold_url = f"@concat('/v1.0/tenants/', {tenant_expression}, '/entitlements/MCSMessages/resourceThresholds')"
    return {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "parameters": {
            "$connections": {"defaultValue": {}, "type": "Object"},
            "$authentication": {"defaultValue": {}, "type": "SecureObject"},
            TENANT_PARAMETER: {
                "defaultValue": "",
                "type": "String",
                "metadata": {"schemaName": TENANT_VARIABLE_SCHEMA},
            },
        },
        "triggers": {
            "Daily": {
                "type": "Recurrence",
                "recurrence": {"frequency": "Day", "interval": 1, "startTime": "2026-01-01T03:00:00Z"},
            }
        },
        "actions": {
            "Initialize_started_on": {
                "type": "InitializeVariable",
                "runAfter": {},
                "inputs": {"variables": [{"name": "StartedOn", "type": "string", "value": "@utcNow()"}]},
            },
            "Get_resource_thresholds": {
                "type": "OpenApiConnection",
                "runAfter": {"Initialize_started_on": ["Succeeded"]},
                "inputs": {
                    "host": {
                        "apiId": HTTP_CONNECTOR,
                        "connectionName": "shared_webcontents",
                        "operationId": "InvokeHttp",
                    },
                    "parameters": {"request/method": "GET", "request/url": threshold_url},
                },
            },
            "Compose_governance_payload": {
                "type": "Compose",
                "runAfter": {"Get_resource_thresholds": ["Succeeded"]},
                "inputs": {
                    "tenantId": f"@{tenant_expression}",
                    "resourceThresholds": "@body('Get_resource_thresholds')",
                    "governanceSyncRun": {
                        "runKey": "@concat('governance-', formatDateTime(utcNow(), 'yyyyMMddHHmmss'))",
                        "name": "@concat('Credit governance - ', formatDateTime(utcNow(), 'yyyy-MM-dd HH:mm'))",
                        "source": "Power Platform resource thresholds",
                        "startedOn": "@variables('StartedOn')",
                        "completedOn": "@utcNow()",
                        "thresholdCount": "@length(body('Get_resource_thresholds'))",
                        "schemaVersion": SCHEMA_VERSION,
                    },
                },
            },
            "Import_governance_snapshot": {
                "type": "OpenApiConnection",
                "runAfter": {"Compose_governance_payload": ["Succeeded"]},
                "inputs": {
                    "host": {
                        "apiId": DATAVERSE_CONNECTOR,
                        "connectionName": "shared_commondataserviceforapps",
                        "operationId": "PerformUnboundAction",
                    },
                    "parameters": {
                        "actionName": API_NAME,
                        "item/PayloadJson": "@string(outputs('Compose_governance_payload'))",
                        "item/SourceSchemaVersion": SCHEMA_VERSION,
                        "item/DryRun": False,
                    },
                },
            },
        },
    }


def build_clientdata() -> str:
    return json.dumps(
        {
            "properties": {
                "connectionReferences": {
                    "shared_webcontents": {
                        "runtimeSource": "embedded",
                        "connection": {"connectionReferenceLogicalName": HTTP_REF_LOGICAL},
                        "api": {"name": "shared_webcontents"},
                    },
                    "shared_commondataserviceforapps": {
                        "runtimeSource": "embedded",
                        "connection": {"connectionReferenceLogicalName": DATAVERSE_REF_LOGICAL},
                        "api": {"name": "shared_commondataserviceforapps"},
                    },
                },
                "definition": build_definition(),
            },
            "schemaVersion": "1.0.0.0",
        }
    )


def ensure_reference(dv: Dv, logical_name: str, display_name: str, connector: str, connection_id: str) -> str:
    existing = dv.find(
        "connectionreferences",
        f"connectionreferencelogicalname eq '{logical_name}'",
        "connectionreferenceid,connectionid",
    )
    if existing:
        reference_id = existing["connectionreferenceid"]
        if existing.get("connectionid") != connection_id:
            response = dv.patch("connectionreferences", reference_id, {"connectionid": connection_id})
            if not response.ok:
                raise RuntimeError(f"Unable to bind {logical_name}: {response.status_code} {response.text[:400]}")
        return reference_id
    return dv.create(
        "connectionreferences",
        {
            "connectionreferencelogicalname": logical_name,
            "connectionreferencedisplayname": display_name,
            "connectorid": connector,
            "connectionid": connection_id,
            "description": f"Used by {FLOW_NAME}.",
        },
    )


def resolve_connection_id(provided: str | None, existing: dict[str, Any] | None) -> str:
    connection_id = provided or (existing or {}).get("connectionid")
    if not connection_id:
        raise SystemExit(
            f"Connected {HTTP_REF_LOGICAL} reference not found; supply --http-connection-id during deployment."
        )
    return connection_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--http-connection-id")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    token, dv_url = get_token_from_config(args.config)
    dv = Dv(f"{dv_url}/api/data/v9.1", token)

    dataverse_ref = dv.find(
        "connectionreferences",
        f"connectionreferencelogicalname eq '{DATAVERSE_REF_LOGICAL}' and connectionid ne null",
        "connectionreferenceid,connectionid",
    )
    if not dataverse_ref:
        raise SystemExit(f"Connected {DATAVERSE_REF_LOGICAL} reference not found.")

    http_ref = dv.find(
        "connectionreferences",
        f"connectionreferencelogicalname eq '{HTTP_REF_LOGICAL}' and connectionid ne null",
        "connectionreferenceid,connectionid",
    )
    http_connection_id = resolve_connection_id(args.http_connection_id, http_ref)
    ensure_reference(dv, HTTP_REF_LOGICAL, "PVCI Power Platform API", HTTP_CONNECTOR, http_connection_id)

    flow = dv.find("workflows", f"name eq '{FLOW_NAME}'", "workflowid,name,statecode")
    clientdata = build_clientdata()
    if flow:
        flow_id = flow["workflowid"]
        if flow.get("statecode") == 1:
            raise SystemExit("Collector is active. Disable it before updating the definition.")
        response = dv.patch("workflows", flow_id, {"clientdata": clientdata})
        if not response.ok:
            raise RuntimeError(f"Unable to update flow: {response.status_code} {response.text[:600]}")
    else:
        flow_id = dv.create(
            "workflows",
            {
                "name": FLOW_NAME,
                "description": "Reads Copilot Credit agent thresholds without changing licensing controls.",
                "category": 5,
                "type": 1,
                "primaryentity": "none",
                "statecode": 0,
                "clientdata": clientdata,
            },
        )

    if args.activate:
        response = dv.patch("workflows", flow_id, {"statecode": 1, "statuscode": 2}, in_solution=False)
        if not response.ok:
            raise RuntimeError(f"Unable to activate flow: {response.status_code} {response.text[:600]}")

    print(
        json.dumps(
            {
                "status": "ok",
                "flowId": flow_id,
                "state": "active" if args.activate else "stopped",
                "solution": SOLUTION,
                "editUrl": (
                    f"https://make.powerautomate.com/environments/{config['environmentId']}"
                    f"/flows/{flow_id}/details"
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()