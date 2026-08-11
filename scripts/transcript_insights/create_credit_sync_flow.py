#!/usr/bin/env python3
"""Create the scheduled PPAC Copilot credit collector in the existing solution."""

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
HTTP_CONNECTOR = "/providers/Microsoft.PowerApps/apis/shared_webcontents"
DATAVERSE_CONNECTOR = "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps"
HTTP_REF_LOGICAL = "pvci_licensinghttp"
DATAVERSE_REF_LOGICAL = "pvci_dataversesync"
FLOW_NAME = "PVCI Collect Copilot Credit Usage (scheduled)"
API_NAME = "pvci_ImportCreditUsageBatch"
PAGE_SIZE = 100
MAX_PAGES = 20
SCHEMA_VERSION = "ppac-v2-resource-aggregate-v1"
TENANT_VARIABLE_SCHEMA = "pvci_CreditReportingTenantId"
TENANT_PARAMETER = f"{TENANT_VARIABLE_SCHEMA} ({TENANT_VARIABLE_SCHEMA})"


def build_definition(lookback_days: int = 7) -> dict[str, Any]:
    tenant_expression = f"parameters('{TENANT_PARAMETER}')"
    usage_url = (
        "@concat('/v2.0/tenants/',"
        + tenant_expression
        + ",'/entitlements/MCSMessages/resources?fromDate=',"
        f"formatDateTime(addDays(utcNow(), -{lookback_days}), 'yyyy-MM-dd'),"
        "'&toDate=',formatDateTime(utcNow(), 'yyyy-MM-dd'),"
        "'&pageNumber=',string(variables('PageNumber')),'&pageSize="
        + str(PAGE_SIZE)
        + "&searchRequest=&includeFields=users')"
    )
    capacity_url = (
        "@concat('/v2.0/tenants/',"
        + tenant_expression
        + ",'/environments/entitlementConsumptions/MCSMessages')"
    )
    users_url = (
        "@concat('/v2.0/tenants/',"
        + tenant_expression
        + ",'/entitlements/MCSMessages/users?fromDate=',"
        f"formatDateTime(addDays(utcNow(), -{lookback_days}), 'yyyy-MM-dd'),"
        "'&toDate=',formatDateTime(utcNow(), 'yyyy-MM-dd'))"
    )

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
                "recurrence": {"frequency": "Day", "interval": 1, "startTime": "2026-01-01T02:00:00Z"},
            }
        },
        "actions": {
            "Initialize_usage_pages": {
                "type": "InitializeVariable",
                "runAfter": {},
                "inputs": {"variables": [{"name": "UsagePages", "type": "array", "value": []}]},
            },
            "Initialize_page_number": {
                "type": "InitializeVariable",
                "runAfter": {"Initialize_usage_pages": ["Succeeded"]},
                "inputs": {"variables": [{"name": "PageNumber", "type": "integer", "value": 1}]},
            },
            "Initialize_has_more": {
                "type": "InitializeVariable",
                "runAfter": {"Initialize_page_number": ["Succeeded"]},
                "inputs": {"variables": [{"name": "HasMore", "type": "boolean", "value": True}]},
            },
            "Until_usage_complete": {
                "type": "Until",
                "runAfter": {"Initialize_has_more": ["Succeeded"]},
                "expression": "@equals(variables('HasMore'), false)",
                "limit": {"count": MAX_PAGES, "timeout": "PT1H"},
                "actions": {
                    "Get_usage_page": {
                        "type": "OpenApiConnection",
                        "runAfter": {},
                        "inputs": {
                            "host": {
                                "apiId": HTTP_CONNECTOR,
                                "connectionName": "shared_webcontents",
                                "operationId": "InvokeHttp",
                            },
                            "parameters": {"request/method": "GET", "request/url": usage_url},
                        },
                    },
                    "Append_usage_page": {
                        "type": "AppendToArrayVariable",
                        "runAfter": {"Get_usage_page": ["Succeeded"]},
                        "inputs": {"name": "UsagePages", "value": "@body('Get_usage_page')"},
                    },
                    "Set_has_more": {
                        "type": "SetVariable",
                        "runAfter": {"Append_usage_page": ["Succeeded"]},
                        "inputs": {
                            "name": "HasMore",
                            "value": (
                                "@equals(length(coalesce(first(body('Get_usage_page')?['value'])?['resources'], "
                                "createArray())), " + str(PAGE_SIZE) + ")"
                            ),
                        },
                    },
                    "Increment_page_number": {
                        "type": "IncrementVariable",
                        "runAfter": {"Set_has_more": ["Succeeded"]},
                        "inputs": {"name": "PageNumber", "value": 1},
                    },
                },
            },
            "Get_capacity": {
                "type": "OpenApiConnection",
                "runAfter": {"Get_user_usage": ["Succeeded"]},
                "inputs": {
                    "host": {
                        "apiId": HTTP_CONNECTOR,
                        "connectionName": "shared_webcontents",
                        "operationId": "InvokeHttp",
                    },
                    "parameters": {"request/method": "GET", "request/url": capacity_url},
                },
            },
            "Get_user_usage": {
                "type": "OpenApiConnection",
                "runAfter": {"Until_usage_complete": ["Succeeded"]},
                "inputs": {
                    "host": {
                        "apiId": HTTP_CONNECTOR,
                        "connectionName": "shared_webcontents",
                        "operationId": "InvokeHttp",
                    },
                    "parameters": {"request/method": "GET", "request/url": users_url},
                },
            },
            "Compose_import_payload": {
                "type": "Compose",
                "runAfter": {"Get_capacity": ["Succeeded"]},
                "inputs": {
                    "tenantId": f"@{tenant_expression}",
                    "ppacResourcePages": "@variables('UsagePages')",
                    "ppacUsers": "@body('Get_user_usage')",
                    "ppacCapacity": "@body('Get_capacity')",
                    "syncRun": {
                        "runKey": "@concat('ppac-', formatDateTime(utcNow(), 'yyyyMMddHHmmss'))",
                        "name": "@concat('PPAC credit collection - ', formatDateTime(utcNow(), 'yyyy-MM-dd HH:mm'))",
                        "source": "PPAC licensing API",
                        "startedOn": "@utcNow()",
                        "completedOn": "@utcNow()",
                        "fromDate": f"@formatDateTime(addDays(utcNow(), -{lookback_days}), 'yyyy-MM-dd')",
                        "toDate": "@formatDateTime(utcNow(), 'yyyy-MM-dd')",
                        "pageCount": "@sub(variables('PageNumber'), 1)",
                        "schemaVersion": SCHEMA_VERSION,
                    },
                },
            },
            "Import_credit_usage": {
                "type": "OpenApiConnection",
                "runAfter": {"Compose_import_payload": ["Succeeded"]},
                "inputs": {
                    "host": {
                        "apiId": DATAVERSE_CONNECTOR,
                        "connectionName": "shared_commondataserviceforapps",
                        "operationId": "PerformUnboundAction",
                    },
                    "parameters": {
                        "actionName": API_NAME,
                        "item/PayloadJson": "@string(outputs('Compose_import_payload'))",
                        "item/SourceSchemaVersion": SCHEMA_VERSION,
                        "item/DryRun": False,
                    },
                },
            },
        },
    }


def build_clientdata(lookback_days: int = 7) -> str:
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
                "definition": build_definition(lookback_days),
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
        print(f"connection reference exists: {logical_name}")
        return reference_id
    reference_id = dv.create(
        "connectionreferences",
        {
            "connectionreferencelogicalname": logical_name,
            "connectionreferencedisplayname": display_name,
            "connectorid": connector,
            "connectionid": connection_id,
            "description": f"Used by {FLOW_NAME}.",
        },
    )
    print(f"connection reference created: {reference_id}")
    return reference_id


def resolve_connection_id(provided: str | None, existing: dict[str, Any] | None) -> str:
    connection_id = provided or (existing or {}).get("connectionid")
    if not connection_id:
        raise SystemExit(
            f"Connected {HTTP_REF_LOGICAL} reference not found; supply --http-connection-id during deployment."
        )
    return connection_id


def ensure_tenant_variable_value(dv: Dv, tenant_id: str) -> str:
    definition = dv.find(
        "environmentvariabledefinitions",
        f"schemaname eq '{TENANT_VARIABLE_SCHEMA}'",
        "environmentvariabledefinitionid,schemaname",
    )
    if not definition:
        raise SystemExit(
            f"Environment variable {TENANT_VARIABLE_SCHEMA} was not found; provision the solution schema first."
        )
    definition_id = definition["environmentvariabledefinitionid"]
    current = dv.find(
        "environmentvariablevalues",
        f"_environmentvariabledefinitionid_value eq {definition_id}",
        "environmentvariablevalueid,value",
    )
    if current:
        response = dv.patch(
            "environmentvariablevalues",
            current["environmentvariablevalueid"],
            {"value": tenant_id},
            in_solution=False,
        )
        if not response.ok:
            raise RuntimeError(f"Unable to update {TENANT_VARIABLE_SCHEMA}: {response.status_code} {response.text[:400]}")
        print(f"environment variable current value updated: {TENANT_VARIABLE_SCHEMA}")
        return current["environmentvariablevalueid"]

    response = dv.s.post(
        f"{dv.base}/environmentvariablevalues",
        headers=dv.h,
        json={
            "value": tenant_id,
            "EnvironmentVariableDefinitionId@odata.bind": f"/environmentvariabledefinitions({definition_id})",
        },
        timeout=180,
    )
    if not response.ok:
        raise RuntimeError(f"Unable to create {TENANT_VARIABLE_SCHEMA}: {response.status_code} {response.text[:400]}")
    location = response.headers.get("OData-EntityId") or response.headers.get("odata-entityid") or ""
    print(f"environment variable current value created: {TENANT_VARIABLE_SCHEMA}")
    return location.split("(")[-1].split(")")[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--http-connection-id")
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    tenant_id = config["tenantId"]
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

    ensure_tenant_variable_value(dv, tenant_id)

    ensure_reference(
        dv,
        HTTP_REF_LOGICAL,
        "PVCI Licensing API",
        HTTP_CONNECTOR,
        http_connection_id,
    )

    clientdata = build_clientdata(args.lookback_days)
    flow = dv.find("workflows", f"name eq '{FLOW_NAME}'", "workflowid,name,statecode")
    if flow:
        flow_id = flow["workflowid"]
        if flow.get("statecode") == 1:
            raise SystemExit("Collector is active. Disable it before updating the definition.")
        response = dv.patch("workflows", flow_id, {"clientdata": clientdata})
        if not response.ok:
            raise RuntimeError(f"Unable to update flow: {response.status_code} {response.text[:600]}")
        print(f"flow updated: {flow_id}")
    else:
        flow_id = dv.create(
            "workflows",
            {
                "name": FLOW_NAME,
                "description": (
                    "Reads paged Copilot Credit usage and capacity from PPAC with a seven-day overlap, "
                    f"then imports through {API_NAME}."
                ),
                "category": 5,
                "type": 1,
                "primaryentity": "none",
                "statecode": 0,
                "clientdata": clientdata,
            },
        )
        print(f"flow created: {flow_id}")

    if args.activate:
        response = dv.patch("workflows", flow_id, {"statecode": 1, "statuscode": 2}, in_solution=False)
        if not response.ok:
            raise RuntimeError(f"Unable to activate flow: {response.status_code} {response.text[:600]}")
        print("activate: ok")

    print(
        json.dumps(
            {
                "status": "ok",
                "flowId": flow_id,
                "state": "active" if args.activate else "stopped",
                "solution": SOLUTION,
                "lookbackDays": args.lookback_days,
                "maxRows": PAGE_SIZE * MAX_PAGES,
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