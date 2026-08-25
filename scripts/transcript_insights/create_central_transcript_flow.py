#!/usr/bin/env python3
"""Create the tenant-neutral central transcript collector inside the core solution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config, require_authorized_config  # noqa: E402
from register_plugin import Dv  # noqa: E402


SOLUTION = "pvConversationInsights"
DATAVERSE_CONNECTOR = "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps"
COLLECTOR_REFERENCE = "pvci_centralcollector"
IMPORT_API = "pvci_ImportCentralTranscriptBatch"
FLOW_NAME = "PVCI Collect Central Transcripts (scheduled)"
SCHEMA_VERSION = "central-transcript-v1"
BATCH_SIZE = 25


def build_definition(frequency: str = "Hour", interval: int = 1) -> dict[str, Any]:
    references = {
        COLLECTOR_REFERENCE: {
            "runtimeSource": "embedded",
            "connection": {"connectionReferenceLogicalName": COLLECTOR_REFERENCE},
            "api": {"name": "shared_commondataserviceforapps"},
        }
    }
    actions: dict[str, Any] = {
        "List_transcript_sources": {
            "type": "OpenApiConnection",
            "runAfter": {},
            "inputs": {
                "host": {
                    "apiId": DATAVERSE_CONNECTOR,
                    "connectionName": COLLECTOR_REFERENCE,
                    "operationId": "ListRecords",
                },
                "parameters": {
                    "entityName": "pvci_environmentinventories",
                    "$select": (
                        "pvci_environmentinventoryid,pvci_tenantid,pvci_environmentid,"
                        "pvci_displayname,pvci_environmenturl,pvci_transcriptcollectorenabled,"
                        "pvci_transcriptlastcollectedon"
                    ),
                    "$filter": (
                        "pvci_hasdataverse eq true and pvci_environmenturl ne null and "
                        "pvci_transcriptcollectorenabled eq true"
                    ),
                    "$orderby": "pvci_displayname asc",
                    "$top": 500,
                },
            },
        },
        "Process_transcript_sources": {
            "type": "Foreach",
            "runAfter": {"List_transcript_sources": ["Succeeded"]},
            "foreach": "@body('List_transcript_sources')?['value']",
            "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
            "actions": {
                "Probe_source_access": {
                    "type": "Scope",
                    "runAfter": {},
                    "actions": {
                        "Probe_source_transcript_access": {
                            "type": "OpenApiConnection",
                            "runAfter": {},
                            "inputs": {
                                "host": {
                                    "apiId": DATAVERSE_CONNECTOR,
                                    "connectionName": COLLECTOR_REFERENCE,
                                    "operationId": "ListRecordsWithOrganization",
                                },
                                "parameters": {
                                    "organization": "@items('Process_transcript_sources')?['pvci_environmenturl']",
                                    "entityName": "conversationtranscripts",
                                    "$select": "conversationtranscriptid",
                                    "$top": 1,
                                },
                            },
                        },
                    },
                },
                "Collect_source_transcripts": {
                    "type": "Scope",
                    "runAfter": {"Probe_source_access": ["Succeeded"]},
                    "actions": {
                        "Read_source_transcripts": {
                            "type": "OpenApiConnection",
                            "runAfter": {},
                            "inputs": {
                                "host": {
                                    "apiId": DATAVERSE_CONNECTOR,
                                    "connectionName": COLLECTOR_REFERENCE,
                                    "operationId": "ListRecordsWithOrganization",
                                },
                                "parameters": {
                                    "organization": "@items('Process_transcript_sources')?['pvci_environmenturl']",
                                    "entityName": "conversationtranscripts",
                                    "$select": "conversationtranscriptid,metadata,content,createdon",
                                    "$filter": (
                                        "@concat('createdon ge ',coalesce(items('Process_transcript_sources')?"
                                        "['pvci_transcriptlastcollectedon'],'1900-01-01T00:00:00Z'))"
                                    ),
                                    "$orderby": "createdon asc",
                                    "$top": BATCH_SIZE,
                                },
                            },
                        },
                        "Mark_source_readable": {
                            "type": "OpenApiConnection",
                            "runAfter": {"Read_source_transcripts": ["Succeeded"]},
                            "inputs": {
                                "host": {
                                    "apiId": DATAVERSE_CONNECTOR,
                                    "connectionName": COLLECTOR_REFERENCE,
                                    "operationId": "UpdateOnlyRecord",
                                },
                                "parameters": {
                                    "entityName": "pvci_environmentinventories",
                                    "recordId": "@items('Process_transcript_sources')?['pvci_environmentinventoryid']",
                                    "item/pvci_transcriptaccessstatus": (
                                        "@if(empty(body('Read_source_transcripts')?['value']),"
                                        "'readable_empty','readable_with_rows')"
                                    ),
                                    "item/pvci_transcriptaccessreason": "",
                                    "item/pvci_transcriptprobeon": "@utcNow()",
                                    "item/pvci_transcriptsamplecount": "@length(body('Read_source_transcripts')?['value'])",
                                },
                            },
                        },
                        "Import_source_batch": {
                            "type": "OpenApiConnection",
                            "runAfter": {"Mark_source_readable": ["Succeeded"]},
                            "inputs": {
                                "host": {
                                    "apiId": DATAVERSE_CONNECTOR,
                                    "connectionName": COLLECTOR_REFERENCE,
                                    "operationId": "PerformUnboundAction",
                                },
                                "parameters": {
                                    "actionName": IMPORT_API,
                                    "item/PayloadJson": "@string(body('Read_source_transcripts'))",
                                    "item/SourceTenantId": "@items('Process_transcript_sources')?['pvci_tenantid']",
                                    "item/SourceEnvironmentId": "@items('Process_transcript_sources')?['pvci_environmentid']",
                                    "item/SourceEnvironmentName": "@items('Process_transcript_sources')?['pvci_displayname']",
                                    "item/SourceDataverseUrl": "@items('Process_transcript_sources')?['pvci_environmenturl']",
                                    "item/SourceSchemaVersion": SCHEMA_VERSION,
                                    "item/DryRun": False,
                                    "item/IncludeTraces": False,
                                    "item/Reprocess": False,
                                },
                            },
                        },
                    },
                },
                "Handle_source_access_failure": {
                    "type": "Scope",
                    "runAfter": {"Probe_source_access": ["Failed", "TimedOut"]},
                    "actions": {
                        "Mark_source_unavailable": {
                            "type": "OpenApiConnection",
                            "runAfter": {},
                            "inputs": {
                                "host": {
                                    "apiId": DATAVERSE_CONNECTOR,
                                    "connectionName": COLLECTOR_REFERENCE,
                                    "operationId": "UpdateOnlyRecord",
                                },
                                "parameters": {
                                    "entityName": "pvci_environmentinventories",
                                    "recordId": "@items('Process_transcript_sources')?['pvci_environmentinventoryid']",
                                    "item/pvci_transcriptaccessstatus": "access_denied",
                                    "item/pvci_transcriptaccessreason": "dataverse_read_not_available",
                                    "item/pvci_transcriptprobeon": "@utcNow()",
                                    "item/pvci_transcriptsamplecount": 0,
                                    "item/pvci_transcriptcollectorenabled": False,
                                    "item/pvci_transcriptlastcollectionstatus": "skipped_access_denied",
                                    "item/pvci_transcriptlastcollectionerror": (
                                        "Source access probe failed or timed out. Collection was disabled. "
                                        "Verify source access, tenant isolation, DLP, and connection state, "
                                        "then re-enable the source."
                                    ),
                                },
                            },
                        },
                    },
                },
                "Complete_source_iteration": {
                    "type": "Compose",
                    "runAfter": {
                        "Collect_source_transcripts": ["Succeeded", "Skipped"],
                        "Handle_source_access_failure": ["Succeeded", "Skipped"],
                    },
                    "inputs": "@items('Process_transcript_sources')?['pvci_environmentid']",
                },
            },
        },
    }
    definition = {
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
            }
        },
        "actions": actions,
    }
    return {
        "name": FLOW_NAME,
        "schemaVersion": SCHEMA_VERSION,
        "references": references,
        "definition": definition,
    }


def build_solution_workflow(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "properties": {
            "connectionReferences": result["references"],
            "definition": result["definition"],
            "templateName": None,
        },
        "schemaVersion": "1.0.0.0",
    }


def ensure_flow_in_core_solution(dv: Dv, flow_id: str) -> bool:
    solution = dv.find(
        "solutions",
        f"uniquename eq '{SOLUTION}'",
        "solutionid,uniquename",
    )
    if not solution:
        raise RuntimeError(f"Core solution {SOLUTION} was not found.")
    existing = dv.find(
        "solutioncomponents",
        (
            f"_solutionid_value eq {solution['solutionid']} and "
            f"objectid eq {flow_id} and componenttype eq 29"
        ),
        "solutioncomponentid,objectid,componenttype",
    )
    if existing:
        return False
    response = dv.s.post(
        f"{dv.base}/AddSolutionComponent",
        headers=dv.h,
        json={
            "ComponentId": flow_id,
            "ComponentType": 29,
            "SolutionUniqueName": SOLUTION,
            "AddRequiredComponents": False,
            "DoNotIncludeSubcomponents": True,
            "IncludedComponentSettingsValues": [],
        },
        timeout=180,
    )
    if not response.ok:
        raise RuntimeError(
            f"AddSolutionComponent failed: {response.status_code} {response.text[:600]}"
        )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/central-transcript-flow.json")
    parser.add_argument("--solution-output", help="Also write the core solution workflow artifact")
    parser.add_argument("--frequency", choices=["Minute", "Hour", "Day"], default="Hour")
    parser.add_argument("--interval", type=int, default=1)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--connection-id", help="Physical Dataverse connection ID to bind")
    parser.add_argument("--deploy", action="store_true", help="Create or update the core solution flow")
    parser.add_argument("--activate", action="store_true", help="Activate the deployed flow")
    args = parser.parse_args()

    result = build_definition(args.frequency, args.interval)
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
        require_authorized_config(args.config)
        token, dv_url = get_token_from_config(args.config)
        dv = Dv(f"{dv_url}/api/data/v9.1", token)
        reference = dv.find(
            "connectionreferences",
            f"connectionreferencelogicalname eq '{COLLECTOR_REFERENCE}'",
            "connectionreferenceid,connectionid",
        )
        if not reference:
            reference_id = dv.create("connectionreferences", {
                "connectionreferencelogicalname": COLLECTOR_REFERENCE,
                "connectionreferencedisplayname": "PVCI Central Transcript Collector",
                "connectorid": DATAVERSE_CONNECTOR,
                "description": "Used by the packaged cross-environment transcript collector.",
                **({"connectionid": args.connection_id} if args.connection_id else {}),
            })
            reference = {"connectionreferenceid": reference_id, "connectionid": args.connection_id}
        elif args.connection_id and reference.get("connectionid") != args.connection_id:
            update_reference = dv.s.patch(
                f"{dv.base}/connectionreferences({reference['connectionreferenceid']})",
                headers=dv.h,
                json={"connectionid": args.connection_id},
                timeout=180,
            )
            if not update_reference.ok:
                raise RuntimeError(
                    f"Connection reference update failed: {update_reference.status_code} "
                    f"{update_reference.text[:600]}"
                )

        clientdata = json.dumps({
            "properties": {
                "connectionReferences": result["references"],
                "definition": result["definition"],
            },
            "schemaVersion": "1.0.0.0",
        })
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
            flow_id = dv.create("workflows", {
                "name": FLOW_NAME,
                "description": (
                    "Probes tenant environment inventory and imports bounded transcript batches "
                    "from explicitly enabled readable environments."
                ),
                "category": 5,
                "type": 1,
                "primaryentity": "none",
                "statecode": 0,
                "clientdata": clientdata,
            })

        added_to_solution = ensure_flow_in_core_solution(dv, flow_id)

        if args.activate:
            activation = dv.s.patch(
                f"{dv.base}/workflows({flow_id})",
                headers=dv.h,
                json={"statecode": 1, "statuscode": 2},
                timeout=180,
            )
            if not activation.ok:
                raise RuntimeError(f"Flow activation failed: {activation.status_code} {activation.text[:600]}")
        response.update({
            "flowId": flow_id,
            "activated": bool(args.activate),
            "addedToCoreSolution": added_to_solution,
        })

    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()
