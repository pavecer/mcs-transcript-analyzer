#!/usr/bin/env python3
"""Verify a tenant-local central transcript collector runtime and its source health."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config  # noqa: E402
from register_plugin import Dv  # noqa: E402


FLOW_NAME = "PVCI Collect Central Transcripts (scheduled)"


def query_values(dv: Dv, path: str) -> list[dict[str, object]]:
    response = dv.s.get(f"{dv.base}/{path}", headers=dv.h, timeout=90)
    if not response.ok:
        raise RuntimeError(f"GET {path} failed: {response.status_code} {response.text[:600]}")
    return response.json().get("value", [])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--source-environment-id", required=True)
    args = parser.parse_args()

    token, dv_url = get_token_from_config(args.config)
    dv = Dv(f"{dv_url}/api/data/v9.1", token)
    source_id = args.source_environment_id
    reference_name = "pvci_centralcollector"

    flow = dv.find(
        "workflows",
        f"name eq '{FLOW_NAME}'",
        "workflowid,name,statecode,statuscode,modifiedon",
    )
    reference = dv.find(
        "connectionreferences",
        f"connectionreferencelogicalname eq '{reference_name}'",
        "connectionreferenceid,connectionreferencelogicalname,connectionid",
    )
    environment = dv.find(
        "pvci_environmentinventories",
        f"pvci_environmentid eq '{source_id}'",
        (
            "pvci_environmentinventoryid,pvci_displayname,pvci_transcriptaccessstatus,"
            "pvci_transcriptcollectorenabled,pvci_transcriptlastcollectedon,"
            "pvci_transcriptlastcollectionstatus,pvci_transcriptlastbatchcount,"
            "pvci_transcriptlastcollectionerror"
        ),
    )
    sessions = query_values(
        dv,
        "pvci_transcriptsessions?$select=pvci_transcriptsessionid,pvci_transcriptid,"
        "pvci_environmentid,pvci_environmentname,pvci_transcriptcreatedon,pvci_ingestedon"
        f"&$filter=pvci_environmentid eq '{source_id}'&$orderby=pvci_ingestedon desc&$top=5",
    )

    recent_runs: list[dict[str, object]] = []
    if flow:
        recent_runs = query_values(
            dv,
            "flowruns?$select=flowrunid,name,status,starttime,endtime,workflowid,"
            "errorcode,errormessage"
            f"&$filter=workflowid eq '{flow['workflowid']}'&$orderby=starttime desc&$top=5",
        )

    result = {
        "status": "ok",
        "collectorUrl": dv_url,
        "flow": flow,
        "collectorConnectionReference": reference,
        "sourceEnvironment": environment,
        "recentSessions": sessions,
        "recentFlowRuns": recent_runs,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()