#!/usr/bin/env python3
"""Create the packaged processor for source-managed transcript access verification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from create_central_transcript_flow import (  # noqa: E402
    COLLECTOR_REFERENCE,
    DATAVERSE_CONNECTOR,
    ensure_flow_in_core_solution,
)
from dv_token import get_token_from_config  # noqa: E402
from register_plugin import Dv  # noqa: E402


FLOW_NAME = "PVCI Verify Transcript Source Access (scheduled)"
REQUEST_TABLE = "pvci_transcriptaccessrequests"
INVENTORY_TABLE = "pvci_environmentinventories"
MAX_REQUESTS = 20


def dataverse_action(
    operation: str,
    parameters: dict[str, Any],
    run_after: dict[str, list[str]],
) -> dict[str, Any]:
    return {
        "type": "OpenApiConnection",
        "runAfter": run_after,
        "inputs": {
            "host": {
                "apiId": DATAVERSE_CONNECTOR,
                "connectionName": COLLECTOR_REFERENCE,
                "operationId": operation,
            },
            "parameters": parameters,
        },
    }


def update_request(status: str, run_after: dict[str, list[str]], **fields: Any) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "entityName": REQUEST_TABLE,
        "recordId": "@items('Process_verification_requests')?['pvci_transcriptaccessrequestid']",
        "item/pvci_status": status,
    }
    parameters.update({f"item/{name}": value for name, value in fields.items()})
    return dataverse_action("UpdateOnlyRecord", parameters, run_after)


def update_inventory(run_after: dict[str, list[str]], **fields: Any) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "entityName": INVENTORY_TABLE,
        "recordId": "@items('Process_verification_requests')?['_pvci_environmentinventoryid_value']",
    }
    parameters.update({f"item/{name}": value for name, value in fields.items()})
    return dataverse_action("UpdateOnlyRecord", parameters, run_after)


def build_definition() -> dict[str, Any]:
    request = "items('Process_verification_requests')"
    access_status = (
        "@if(empty(body('Probe_source_transcript_access')?['value']),"
        "'readable_empty','readable_with_rows')"
    )
    references = {
        COLLECTOR_REFERENCE: {
            "runtimeSource": "embedded",
            "connection": {"connectionReferenceLogicalName": COLLECTOR_REFERENCE},
            "api": {"name": "shared_commondataserviceforapps"},
        }
    }
    probe_scope = {
        "type": "Scope",
        "runAfter": {"Mark_processing": ["Succeeded"]},
        "actions": {
            "Probe_source_transcript_access": dataverse_action(
                "ListRecordsWithOrganization",
                {
                    "organization": f"@{request}?['pvci_environmenturl']",
                    "entityName": "conversationtranscripts",
                    "$select": "conversationtranscriptid",
                    "$top": 1,
                },
                {},
            )
        },
    }
    actions: dict[str, Any] = {
        "List_pending_verification_requests": dataverse_action(
            "ListRecords",
            {
                "entityName": REQUEST_TABLE,
                "$select": (
                    "pvci_transcriptaccessrequestid,pvci_environmentid,pvci_environmenturl,"
                    "pvci_action,pvci_requestedmode,pvci_status,_pvci_environmentinventoryid_value"
                ),
                "$filter": "pvci_status eq 'Pending' and pvci_action eq 'Verify'",
                "$orderby": "createdon asc",
                "$top": MAX_REQUESTS,
            },
            {},
        ),
        "Process_verification_requests": {
            "type": "Foreach",
            "runAfter": {"List_pending_verification_requests": ["Succeeded"]},
            "foreach": "@body('List_pending_verification_requests')?['value']",
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
            "actions": {
                "Mark_processing": update_request(
                    "Processing",
                    {},
                    pvci_processor=FLOW_NAME,
                    pvci_error="",
                ),
                "Probe_source_access": probe_scope,
                "Mark_verified": update_request(
                    "Verified",
                    {"Probe_source_access": ["Succeeded"]},
                    pvci_processedon="@utcNow()",
                    pvci_accessstatus=access_status,
                    pvci_roleverified=False,
                    pvci_elevationcleanupverified=False,
                    pvci_evidence=(
                        "@concat('One-row ID-only Dataverse probe succeeded; sampleCount=',"
                        "string(length(body('Probe_source_transcript_access')?['value'])))"
                    ),
                    pvci_error="",
                ),
                "Project_verified_access": update_inventory(
                    {"Mark_verified": ["Succeeded"]},
                    pvci_transcriptonboardingmode=f"@{request}?['pvci_requestedmode']",
                    pvci_transcriptonboardingstatus="Verified",
                    pvci_transcriptaccessstatus=access_status,
                    pvci_transcriptaccessreason="",
                    pvci_transcriptprobeon="@utcNow()",
                    pvci_transcriptaccesslastverifiedon="@utcNow()",
                    pvci_transcriptsamplecount=(
                        "@length(body('Probe_source_transcript_access')?['value'])"
                    ),
                    pvci_transcriptaccessroleverified=False,
                    pvci_transcriptelevationcleanupverified=False,
                    pvci_transcriptonboardinglasterror="",
                ),
                "Handle_verification_failure": {
                    "type": "Scope",
                    "runAfter": {"Probe_source_access": ["Failed", "TimedOut"]},
                    "actions": {
                        "Mark_verification_failed": update_request(
                            "Failed",
                            {},
                            pvci_processedon="@utcNow()",
                            pvci_accessstatus="access_denied",
                            pvci_roleverified=False,
                            pvci_elevationcleanupverified=False,
                            pvci_evidence="One-row ID-only Dataverse probe failed or timed out.",
                            pvci_error="Collector identity cannot read conversation transcripts in the source environment.",
                        ),
                        "Project_denied_access": update_inventory(
                            {"Mark_verification_failed": ["Succeeded"]},
                            pvci_transcriptonboardingmode=f"@{request}?['pvci_requestedmode']",
                            pvci_transcriptonboardingstatus="Failed",
                            pvci_transcriptaccessstatus="access_denied",
                            pvci_transcriptaccessreason="dataverse_read_not_available",
                            pvci_transcriptprobeon="@utcNow()",
                            pvci_transcriptsamplecount=0,
                            pvci_transcriptaccessroleverified=False,
                            pvci_transcriptelevationcleanupverified=False,
                            pvci_transcriptcollectorenabled=False,
                            pvci_transcriptonboardinglasterror=(
                                "Collector identity cannot read conversation transcripts in the source environment."
                            ),
                        ),
                    },
                },
                "Complete_verification_request": {
                    "type": "Compose",
                    "runAfter": {
                        "Project_verified_access": ["Succeeded", "Skipped"],
                        "Handle_verification_failure": ["Succeeded", "Skipped"],
                    },
                    "inputs": f"@{request}?['pvci_transcriptaccessrequestid']",
                },
            },
        },
    }
    return {
        "name": FLOW_NAME,
        "references": references,
        "definition": {
            "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
            "contentVersion": "1.0.0.0",
            "parameters": {
                "$connections": {"defaultValue": {}, "type": "Object"},
                "$authentication": {"defaultValue": {}, "type": "SecureObject"},
            },
            "triggers": {
                "Every_minute": {
                    "type": "Recurrence",
                    "recurrence": {"frequency": "Minute", "interval": 1},
                    "runtimeConfiguration": {"concurrency": {"runs": 1}},
                }
            },
            "actions": actions,
        },
    }


def build_clientdata(result: dict[str, Any]) -> str:
    return json.dumps(
        {
            "properties": {
                "connectionReferences": result["references"],
                "definition": result["definition"],
            },
            "schemaVersion": "1.0.0.0",
        }
    )


def build_solution_workflow(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "properties": {
            "connectionReferences": result["references"],
            "definition": result["definition"],
            "templateName": None,
        },
        "schemaVersion": "1.0.0.0",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/transcript-access-verification-flow.json")
    parser.add_argument("--solution-output", help="Also write the core solution workflow artifact")
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--deploy", action="store_true")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()

    result = build_definition()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    response: dict[str, Any] = {"status": "ok", "output": str(output)}
    if args.solution_output:
        solution_output = Path(args.solution_output)
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        solution_output.write_text(
            json.dumps(build_solution_workflow(result), indent=2) + "\n",
            encoding="utf-8",
        )
        response["solutionOutput"] = str(solution_output)

    if args.deploy:
        token, dataverse_url = get_token_from_config(args.config)
        dv = Dv(f"{dataverse_url}/api/data/v9.1", token)
        reference = dv.find(
            "connectionreferences",
            f"connectionreferencelogicalname eq '{COLLECTOR_REFERENCE}' and connectionid ne null",
            "connectionreferenceid,connectionid",
        )
        if not reference:
            raise RuntimeError(f"Connected {COLLECTOR_REFERENCE} reference was not found.")
        clientdata = build_clientdata(result)
        flow = dv.find("workflows", f"name eq '{FLOW_NAME}'", "workflowid,name,statecode")
        if flow:
            flow_id = flow["workflowid"]
            update = dv.s.patch(
                f"{dv.base}/workflows({flow_id})",
                headers=dv.hs,
                json={"clientdata": clientdata},
                timeout=180,
            )
            if not update.ok:
                raise RuntimeError(f"Flow update failed: {update.status_code} {update.text[:600]}")
        else:
            flow_id = dv.create(
                "workflows",
                {
                    "name": FLOW_NAME,
                    "description": "Verifies source-managed transcript access and records audited request results.",
                    "category": 5,
                    "type": 1,
                    "primaryentity": "none",
                    "statecode": 0,
                    "clientdata": clientdata,
                },
            )
        added_to_solution = ensure_flow_in_core_solution(dv, flow_id)
        if args.activate:
            activation = dv.s.patch(
                f"{dv.base}/workflows({flow_id})",
                headers=dv.h,
                json={"statecode": 1, "statuscode": 2},
                timeout=180,
            )
            if not activation.ok:
                raise RuntimeError(
                    f"Flow activation failed: {activation.status_code} {activation.text[:600]}"
                )
        response.update(
            {
                "flowId": flow_id,
                "activated": bool(args.activate),
                "addedToCoreSolution": added_to_solution,
            }
        )
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()