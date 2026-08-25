#!/usr/bin/env python3
"""Create the privileged processor for audited Copilot Credit threshold requests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from create_credit_governance_flow import (  # noqa: E402
    DATAVERSE_CONNECTOR,
    DATAVERSE_REF_LOGICAL,
    HTTP_CONNECTOR,
    HTTP_REF_LOGICAL,
    TENANT_PARAMETER,
    ensure_reference,
    resolve_connection_id,
)
from create_sync_flow import Dv  # noqa: E402
from dv_token import get_token_from_config, require_authorized_config  # noqa: E402


SOLUTION = "pvConversationInsights"
FLOW_NAME = "PVCI Apply Credit Governance Requests (scheduled)"
REQUEST_TABLE = "pvci_thresholdchangerequests"
MAX_REQUESTS = 20


def dataverse_action(operation: str, parameters: dict[str, Any], run_after: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "type": "OpenApiConnection",
        "runAfter": run_after,
        "inputs": {
            "host": {
                "apiId": DATAVERSE_CONNECTOR,
                "connectionName": "shared_commondataserviceforapps",
                "operationId": operation,
            },
            "parameters": parameters,
        },
    }


def http_action(method: str, url: str, run_after: dict[str, list[str]], body: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters: dict[str, Any] = {"request/method": method, "request/url": url}
    if body is not None:
        parameters["request/body"] = body
    return {
        "type": "OpenApiConnection",
        "runAfter": run_after,
        "inputs": {
            "host": {
                "apiId": HTTP_CONNECTOR,
                "connectionName": "shared_webcontents",
                "operationId": "InvokeHttp",
            },
            "parameters": parameters,
        },
    }


def update_request(status: str, run_after: dict[str, list[str]], **fields: Any) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "entityName": REQUEST_TABLE,
        "recordId": "@items('Process_pending_requests')?['pvci_thresholdchangerequestid']",
        "item/pvci_status": status,
    }
    parameters.update({f"item/{key}": value for key, value in fields.items()})
    return dataverse_action("UpdateOnlyRecord", parameters, run_after)


def build_definition() -> dict[str, Any]:
    request = "items('Process_pending_requests')"
    current = "outputs('Compose_current_threshold')"
    tenant_expression = f"parameters('{TENANT_PARAMETER}')"
    threshold_url = f"@concat('/v1.0/tenants/', {tenant_expression}, '/entitlements/MCSMessages/resourceThresholds')"
    request_url = (
        "@concat('/licensing/environments/',"
        f"{request}?['pvci_environmentid'],"
        "'/entitlements/MCSMessages/resources/',"
        f"{request}?['pvci_resourceid'],"
        "'/threshold?api-version=2024-10-01')"
    )
    current_filter = (
        "@and("
        f"equals(toLower(item()?['environmentId']), toLower({request}?['pvci_environmentid'])),"
        f"equals(toLower(item()?['resourceId']), toLower({request}?['pvci_resourceid'])))"
    )
    expected_state = (
        "@and("
        f"equals({request}?['pvci_entitlementid'], 'MCSMessages'),"
        f"greaterOrEquals(length(trim(string(coalesce({request}?['pvci_justification'], '')))), 10),"
        f"greaterOrEquals(float({request}?['pvci_requestedlimit']), 0),"
        f"equals(float({request}?['pvci_requestedlimit']), float(formatNumber(float({request}?['pvci_requestedlimit']), '0', 'en-US'))),"
        f"greaterOrEquals(int({request}?['pvci_requestednotificationthreshold']), 0),"
        f"lessOrEquals(int({request}?['pvci_requestednotificationthreshold']), 100),"
        f"not(empty({current})),"
        f"equals(float(coalesce({current}?['limit'], 0)), float(coalesce({request}?['pvci_expectedlimit'], 0))),"
        f"equals(int(coalesce({current}?['notificationThreshold'], 0)), int(coalesce({request}?['pvci_expectednotificationthreshold'], 0))),"
        f"equals(bool(coalesce({current}?['notifyIfOverCapacity'], false)), bool(coalesce({request}?['pvci_expectednotifyifovercapacity'], false))),"
        f"equals(bool(coalesce({current}?['stopIfOverCapacity'], false)), bool(coalesce({request}?['pvci_expectedstopifovercapacity'], false))),"
        f"equals(bool(coalesce({current}?['stopResource'], false)), bool(coalesce({request}?['pvci_expectedstopresource'], false))))"
    )

    apply_scope = {
        "type": "Scope",
        "runAfter": {"Mark_processing": ["Succeeded"]},
        "actions": {
            "Get_current_thresholds": http_action("GET", threshold_url, {}),
            "Filter_current_threshold": {
                "type": "Query",
                "runAfter": {"Get_current_thresholds": ["Succeeded"]},
                "inputs": {"from": "@body('Get_current_thresholds')", "where": current_filter},
            },
            "Compose_current_threshold": {
                "type": "Compose",
                "runAfter": {"Filter_current_threshold": ["Succeeded"]},
                "inputs": "@first(body('Filter_current_threshold'))",
            },
            "Current_state_matches_request": {
                "type": "If",
                "runAfter": {"Compose_current_threshold": ["Succeeded"]},
                "expression": expected_state,
                "actions": {
                    "Apply_threshold": http_action(
                        "PUT",
                        request_url,
                        {},
                        {
                            "stopResource": f"@bool({request}?['pvci_requestedstopresource'])",
                            "limit": f"@int({request}?['pvci_requestedlimit'])",
                            "stopIfOverCapacity": f"@bool({request}?['pvci_requestedstopifovercapacity'])",
                            "notifyIfOverCapacity": f"@bool({request}?['pvci_requestednotifyifovercapacity'])",
                            "notificationThreshold": f"@int({request}?['pvci_requestednotificationthreshold'])",
                            "resourceConsumption": f"@float(coalesce({current}?['resourceConsumption'], 0))",
                        },
                    ),
                    "Get_thresholds_after": http_action("GET", threshold_url, {"Apply_threshold": ["Succeeded"]}),
                    "Filter_threshold_after": {
                        "type": "Query",
                        "runAfter": {"Get_thresholds_after": ["Succeeded"]},
                        "inputs": {"from": "@body('Get_thresholds_after')", "where": current_filter},
                    },
                    "Mark_succeeded": update_request(
                        "Succeeded",
                        {"Filter_threshold_after": ["Succeeded"]},
                        pvci_processedon="@utcNow()",
                        pvci_beforejson=f"@string({current})",
                        pvci_afterjson="@string(first(body('Filter_threshold_after')))",
                        pvci_error="",
                    ),
                },
                "else": {
                    "actions": {
                        "Mark_stale": update_request(
                            "Stale",
                            {},
                            pvci_processedon="@utcNow()",
                            pvci_beforejson=f"@string({current})",
                            pvci_error="Current threshold state or request validation no longer matches. Review and submit a new request.",
                        )
                    }
                },
            },
        },
    }

    return {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "parameters": {
            "$connections": {"defaultValue": {}, "type": "Object"},
            "$authentication": {"defaultValue": {}, "type": "SecureObject"},
            TENANT_PARAMETER: {
                "defaultValue": "",
                "type": "String",
                "metadata": {"schemaName": "pvci_CreditReportingTenantId"},
            },
        },
        "triggers": {
            "Every_minute": {
                "type": "Recurrence",
                "recurrence": {"frequency": "Minute", "interval": 1},
                "runtimeConfiguration": {"concurrency": {"runs": 1}},
            }
        },
        "actions": {
            "List_pending_requests": dataverse_action(
                "ListRecords",
                {
                    "entityName": REQUEST_TABLE,
                    "$select": (
                        "pvci_thresholdchangerequestid,pvci_environmentid,pvci_resourceid,pvci_entitlementid,"
                        "pvci_requestedlimit,pvci_requestednotificationthreshold,pvci_requestednotifyifovercapacity,"
                        "pvci_requestedstopifovercapacity,pvci_requestedstopresource,pvci_expectedlimit,"
                        "pvci_expectednotificationthreshold,pvci_expectednotifyifovercapacity,"
                        "pvci_expectedstopifovercapacity,pvci_expectedstopresource,pvci_justification"
                    ),
                    "$filter": "pvci_status eq 'Pending'",
                    "$orderby": "createdon asc",
                    "$top": MAX_REQUESTS,
                },
                {},
            ),
            "Process_pending_requests": {
                "type": "Foreach",
                "runAfter": {"List_pending_requests": ["Succeeded"]},
                "foreach": "@body('List_pending_requests')?['value']",
                "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
                "actions": {
                    "Mark_processing": update_request("Processing", {}),
                    "Apply_request": apply_scope,
                    "Mark_processor_failed": update_request(
                        "@if(equals(actions('Apply_threshold')?['status'], 'Skipped'), 'Failed', 'AppliedUnverified')",
                        {"Apply_request": ["Failed", "TimedOut"]},
                        pvci_processedon="@utcNow()",
                        pvci_error=(
                            "@concat(if(equals(actions('Apply_threshold')?['status'], 'Skipped'), "
                            "'Request processing failed before the threshold PUT. ', "
                            "'Threshold PUT was attempted but read-back or audit persistence failed. "
                            "Verify current platform state before resubmitting. '), string(result('Apply_request')))"
                        ),
                    ),
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--http-connection-id")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    require_authorized_config(args.config)

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
    connection_id = resolve_connection_id(args.http_connection_id, http_ref)
    ensure_reference(dv, HTTP_REF_LOGICAL, "PVCI Power Platform API", HTTP_CONNECTOR, connection_id)

    flow = dv.find("workflows", f"name eq '{FLOW_NAME}'", "workflowid,name,statecode")
    clientdata = build_clientdata()
    if flow:
        flow_id = flow["workflowid"]
        if flow.get("statecode") == 1:
            raise SystemExit("Processor is active. Disable it before updating the definition.")
        response = dv.patch("workflows", flow_id, {"clientdata": clientdata})
        if not response.ok:
            raise RuntimeError(f"Unable to update processor: {response.status_code} {response.text[:600]}")
    else:
        flow_id = dv.create(
            "workflows",
            {
                "name": FLOW_NAME,
                "description": "Applies validated threshold change requests and records before/after state.",
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
            raise RuntimeError(f"Unable to activate processor: {response.status_code} {response.text[:600]}")

    print(json.dumps({
        "status": "ok",
        "flowId": flow_id,
        "state": "active" if args.activate else "stopped",
        "maxRequests": MAX_REQUESTS,
        "editUrl": f"https://make.powerautomate.com/environments/{config['environmentId']}/flows/{flow_id}/details",
    }, indent=2))


if __name__ == "__main__":
    main()
