#!/usr/bin/env python3
"""Create the standalone tenant environment and Copilot agent inventory flow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from create_sync_flow import Dv  # noqa: E402
from dv_token import get_token_from_config, require_authorized_config  # noqa: E402


SOLUTION = "pvConversationInsights"
FLOW_NAME = "PVCI Collect Tenant Agent Inventory (scheduled)"
API_NAME = "pvci_ImportCreditUsageBatch"
ADMIN_CONNECTOR = "/providers/Microsoft.PowerApps/apis/shared_powerplatformadminv2"
DATAVERSE_CONNECTOR = "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps"
ADMIN_REF_LOGICAL = "pvci_powerplatformadminv2"
DATAVERSE_REF_LOGICAL = "pvci_dataversesync"
ADMIN_API_VERSION = "2022-03-01-preview"
SCHEMA_VERSION = "power-platform-inventory-v1"
ENVIRONMENT_PAGE_SIZE = 100
MAX_ENVIRONMENT_PAGES = 100
MAX_RESOURCE_PAGES = 100


def admin_action(operation: str, parameters: dict[str, Any], run_after: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "type": "OpenApiConnection",
        "runAfter": run_after,
        "inputs": {
            "host": {
                "apiId": ADMIN_CONNECTOR,
                "connectionName": "shared_powerplatformadminv2",
                "operationId": operation,
            },
            "parameters": parameters,
        },
    }


def compose_action(payload: dict[str, Any], run_after: dict[str, list[str]]) -> dict[str, Any]:
    return {"type": "Compose", "runAfter": run_after, "inputs": payload}


def import_action(compose_name: str, run_after: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "type": "OpenApiConnection",
        "runAfter": run_after,
        "inputs": {
            "host": {
                "apiId": DATAVERSE_CONNECTOR,
                "connectionName": "shared_commondataserviceforapps",
                "operationId": "PerformUnboundAction",
            },
            "parameters": {
                "actionName": API_NAME,
                "item/PayloadJson": f"@string(outputs('{compose_name}'))",
                "item/SourceSchemaVersion": SCHEMA_VERSION,
                "item/DryRun": False,
            },
        },
    }


def increment(name: str, value: Any, run_after: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "type": "IncrementVariable",
        "runAfter": run_after,
        "inputs": {"name": name, "value": value},
    }


def build_definition() -> dict[str, Any]:
    environment_payload = {
        "adminEnvironments": "@body('List_environment_page')",
    }
    resource_payload = {
        "powerPlatformResourcePages": "@body('Query_agent_resources')",
    }
    resource_clauses = [
        {
            "$type": "where",
            "FieldName": "type",
            "Operator": "in~",
            "Values": ["'microsoft.copilotstudio/agents'"],
        }
    ]

    return {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "parameters": {
            "$connections": {"defaultValue": {}, "type": "Object"},
            "$authentication": {"defaultValue": {}, "type": "SecureObject"},
        },
        "triggers": {
            "Daily": {
                "type": "Recurrence",
                "recurrence": {"frequency": "Day", "interval": 1, "startTime": "2026-01-01T01:00:00Z"},
            }
        },
        "actions": {
            "Initialize_started_on": {
                "type": "InitializeVariable",
                "runAfter": {},
                "inputs": {"variables": [{"name": "StartedOn", "type": "string", "value": "@utcNow()"}]},
            },
            "Initialize_environment_skip": {
                "type": "InitializeVariable",
                "runAfter": {"Initialize_started_on": ["Succeeded"]},
                "inputs": {"variables": [{"name": "EnvironmentSkip", "type": "integer", "value": 0}]},
            },
            "Initialize_environment_has_more": {
                "type": "InitializeVariable",
                "runAfter": {"Initialize_environment_skip": ["Succeeded"]},
                "inputs": {"variables": [{"name": "EnvironmentHasMore", "type": "boolean", "value": True}]},
            },
            "Initialize_resource_skip_token": {
                "type": "InitializeVariable",
                "runAfter": {"Initialize_environment_has_more": ["Succeeded"]},
                "inputs": {"variables": [{"name": "ResourceSkipToken", "type": "string", "value": ""}]},
            },
            "Initialize_resource_has_more": {
                "type": "InitializeVariable",
                "runAfter": {"Initialize_resource_skip_token": ["Succeeded"]},
                "inputs": {"variables": [{"name": "ResourceHasMore", "type": "boolean", "value": True}]},
            },
            "Initialize_environment_count": {
                "type": "InitializeVariable",
                "runAfter": {"Initialize_resource_has_more": ["Succeeded"]},
                "inputs": {"variables": [{"name": "EnvironmentCount", "type": "integer", "value": 0}]},
            },
            "Initialize_agent_count": {
                "type": "InitializeVariable",
                "runAfter": {"Initialize_environment_count": ["Succeeded"]},
                "inputs": {"variables": [{"name": "AgentCount", "type": "integer", "value": 0}]},
            },
            "Initialize_created_count": {
                "type": "InitializeVariable",
                "runAfter": {"Initialize_agent_count": ["Succeeded"]},
                "inputs": {"variables": [{"name": "CreatedCount", "type": "integer", "value": 0}]},
            },
            "Initialize_updated_count": {
                "type": "InitializeVariable",
                "runAfter": {"Initialize_created_count": ["Succeeded"]},
                "inputs": {"variables": [{"name": "UpdatedCount", "type": "integer", "value": 0}]},
            },
            "Initialize_rejected_count": {
                "type": "InitializeVariable",
                "runAfter": {"Initialize_updated_count": ["Succeeded"]},
                "inputs": {"variables": [{"name": "RejectedCount", "type": "integer", "value": 0}]},
            },
            "Until_environment_pages_complete": {
                "type": "Until",
                "runAfter": {"Initialize_rejected_count": ["Succeeded"]},
                "expression": "@equals(variables('EnvironmentHasMore'), false)",
                "limit": {"count": MAX_ENVIRONMENT_PAGES, "timeout": "PT1H"},
                "actions": {
                    "List_environment_page": admin_action(
                        "ListEnvironmentsForUser",
                        {
                            "api-version": ADMIN_API_VERSION,
                            "$skip": "@variables('EnvironmentSkip')",
                        },
                        {},
                    ),
                    "Compose_environment_payload": compose_action(
                        environment_payload,
                        {"List_environment_page": ["Succeeded"]},
                    ),
                    "Import_environment_page": import_action(
                        "Compose_environment_payload",
                        {"Compose_environment_payload": ["Succeeded"]},
                    ),
                    "Increment_environment_count": increment(
                        "EnvironmentCount",
                        "@length(coalesce(body('List_environment_page')?['value'], createArray()))",
                        {"Import_environment_page": ["Succeeded"]},
                    ),
                    "Increment_environment_created": increment(
                        "CreatedCount",
                        "@int(coalesce(body('Import_environment_page')?['Created'], 0))",
                        {"Increment_environment_count": ["Succeeded"]},
                    ),
                    "Increment_environment_updated": increment(
                        "UpdatedCount",
                        "@int(coalesce(body('Import_environment_page')?['Updated'], 0))",
                        {"Increment_environment_created": ["Succeeded"]},
                    ),
                    "Increment_environment_rejected": increment(
                        "RejectedCount",
                        "@int(coalesce(body('Import_environment_page')?['Rejected'], 0))",
                        {"Increment_environment_updated": ["Succeeded"]},
                    ),
                    "Set_environment_has_more": {
                        "type": "SetVariable",
                        "runAfter": {"Increment_environment_rejected": ["Succeeded"]},
                        "inputs": {
                            "name": "EnvironmentHasMore",
                            "value": (
                                "@equals(length(coalesce(body('List_environment_page')?['value'], "
                                f"createArray())), {ENVIRONMENT_PAGE_SIZE})"
                            ),
                        },
                    },
                    "Increment_environment_skip": increment(
                        "EnvironmentSkip",
                        ENVIRONMENT_PAGE_SIZE,
                        {"Set_environment_has_more": ["Succeeded"]},
                    ),
                },
            },
            "Until_resource_pages_complete": {
                "type": "Until",
                "runAfter": {"Until_environment_pages_complete": ["Succeeded"]},
                "expression": "@equals(variables('ResourceHasMore'), false)",
                "limit": {"count": MAX_RESOURCE_PAGES, "timeout": "PT1H"},
                "actions": {
                    "Query_agent_resources": admin_action(
                        "QueryResources",
                        {
                            "api-version": ADMIN_API_VERSION,
                            "body/TableName": "PowerPlatformResources",
                            "body/Clauses": resource_clauses,
                            "body/Options/Top": 100,
                            "body/Options/SkipToken": "@variables('ResourceSkipToken')",
                        },
                        {},
                    ),
                    "Compose_agent_payload": compose_action(
                        resource_payload,
                        {"Query_agent_resources": ["Succeeded"]},
                    ),
                    "Import_agent_page": import_action(
                        "Compose_agent_payload",
                        {"Compose_agent_payload": ["Succeeded"]},
                    ),
                    "Increment_agent_count": increment(
                        "AgentCount",
                        "@length(coalesce(body('Query_agent_resources')?['data'], createArray()))",
                        {"Import_agent_page": ["Succeeded"]},
                    ),
                    "Increment_agent_created": increment(
                        "CreatedCount",
                        "@int(coalesce(body('Import_agent_page')?['Created'], 0))",
                        {"Increment_agent_count": ["Succeeded"]},
                    ),
                    "Increment_agent_updated": increment(
                        "UpdatedCount",
                        "@int(coalesce(body('Import_agent_page')?['Updated'], 0))",
                        {"Increment_agent_created": ["Succeeded"]},
                    ),
                    "Increment_agent_rejected": increment(
                        "RejectedCount",
                        "@int(coalesce(body('Import_agent_page')?['Rejected'], 0))",
                        {"Increment_agent_updated": ["Succeeded"]},
                    ),
                    "Set_resource_skip_token": {
                        "type": "SetVariable",
                        "runAfter": {"Increment_agent_rejected": ["Succeeded"]},
                        "inputs": {
                            "name": "ResourceSkipToken",
                            "value": "@coalesce(body('Query_agent_resources')?['skipToken'], '')",
                        },
                    },
                    "Set_resource_has_more": {
                        "type": "SetVariable",
                        "runAfter": {"Set_resource_skip_token": ["Succeeded"]},
                        "inputs": {
                            "name": "ResourceHasMore",
                            "value": "@not(empty(variables('ResourceSkipToken')))",
                        },
                    },
                },
            },
            "Compose_inventory_sync_payload": compose_action(
                {
                    "inventorySyncRun": {
                        "runKey": "@concat('inventory-', formatDateTime(utcNow(), 'yyyyMMddHHmmss'))",
                        "name": "@concat('Tenant inventory - ', formatDateTime(utcNow(), 'yyyy-MM-dd HH:mm'))",
                        "source": "Power Platform Admin V2 and One Inventory",
                        "startedOn": "@variables('StartedOn')",
                        "completedOn": "@utcNow()",
                        "environmentCount": "@variables('EnvironmentCount')",
                        "agentCount": "@variables('AgentCount')",
                        "createdCount": "@variables('CreatedCount')",
                        "updatedCount": "@variables('UpdatedCount')",
                        "rejectedCount": "@variables('RejectedCount')",
                        "schemaVersion": SCHEMA_VERSION,
                    },
                },
                {"Until_resource_pages_complete": ["Succeeded"]},
            ),
            "Finalize_inventory_sync": import_action(
                "Compose_inventory_sync_payload",
                {"Compose_inventory_sync_payload": ["Succeeded"]},
            ),
        },
    }


def build_clientdata() -> str:
    return json.dumps(
        {
            "properties": {
                "connectionReferences": {
                    "shared_powerplatformadminv2": {
                        "runtimeSource": "embedded",
                        "connection": {"connectionReferenceLogicalName": ADMIN_REF_LOGICAL},
                        "api": {"name": "shared_powerplatformadminv2"},
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


def resolve_connection_id(provided: str | None, existing: dict[str, Any] | None) -> str:
    connection_id = provided or (existing or {}).get("connectionid")
    if not connection_id:
        raise SystemExit(
            f"Connected {ADMIN_REF_LOGICAL} reference not found; supply --admin-connection-id during deployment."
        )
    return connection_id


def ensure_reference(dv: Dv, connection_id: str) -> str:
    existing = dv.find(
        "connectionreferences",
        f"connectionreferencelogicalname eq '{ADMIN_REF_LOGICAL}'",
        "connectionreferenceid,connectionid",
    )
    if existing:
        if existing.get("connectionid") != connection_id:
            response = dv.patch("connectionreferences", existing["connectionreferenceid"], {"connectionid": connection_id})
            if not response.ok:
                raise RuntimeError(f"Unable to bind {ADMIN_REF_LOGICAL}: {response.status_code} {response.text[:400]}")
        return existing["connectionreferenceid"]
    return dv.create(
        "connectionreferences",
        {
            "connectionreferencelogicalname": ADMIN_REF_LOGICAL,
            "connectionreferencedisplayname": "PVCI Power Platform Admin V2",
            "connectorid": ADMIN_CONNECTOR,
            "connectionid": connection_id,
            "description": f"Used by {FLOW_NAME}.",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--admin-connection-id")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    require_authorized_config(args.config)

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    token, dataverse_url = get_token_from_config(args.config)
    dv = Dv(f"{dataverse_url}/api/data/v9.1", token)
    dataverse_ref = dv.find(
        "connectionreferences",
        f"connectionreferencelogicalname eq '{DATAVERSE_REF_LOGICAL}' and connectionid ne null",
        "connectionreferenceid,connectionid",
    )
    if not dataverse_ref:
        raise SystemExit(f"Connected {DATAVERSE_REF_LOGICAL} reference not found.")
    existing_admin_ref = dv.find(
        "connectionreferences",
        f"connectionreferencelogicalname eq '{ADMIN_REF_LOGICAL}' and connectionid ne null",
        "connectionreferenceid,connectionid",
    )
    admin_connection_id = resolve_connection_id(args.admin_connection_id, existing_admin_ref)
    ensure_reference(dv, admin_connection_id)

    flow = dv.find("workflows", f"name eq '{FLOW_NAME}'", "workflowid,name,statecode")
    clientdata = build_clientdata()
    if flow:
        flow_id = flow["workflowid"]
        if flow.get("statecode") == 1:
            raise SystemExit("Inventory collector is active. Disable it before updating the definition.")
        response = dv.patch("workflows", flow_id, {"clientdata": clientdata})
        if not response.ok:
            raise RuntimeError(f"Unable to update flow: {response.status_code} {response.text[:600]}")
    else:
        flow_id = dv.create(
            "workflows",
            {
                "name": FLOW_NAME,
                "description": "Collects tenant environments and Copilot agents independently of credit activity.",
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
                "maxEnvironmentPages": MAX_ENVIRONMENT_PAGES,
                "maxResourcePages": MAX_RESOURCE_PAGES,
                "editUrl": f"https://make.powerautomate.com/environments/{config['environmentId']}/flows/{flow_id}/details",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()