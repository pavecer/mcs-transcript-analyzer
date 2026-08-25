#!/usr/bin/env python3
"""Queue or inspect a source-managed transcript access verification request."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config, require_authorized_config  # noqa: E402
from register_plugin import Dv  # noqa: E402


def get_config(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def create_request(dv: Dv, config: dict[str, Any]) -> dict[str, str]:
    environment_id = config["environmentId"]
    environment_url = config["dataverseUrl"].rstrip("/")
    inventory = dv.find(
        "pvci_environmentinventories",
        f"pvci_environmentid eq '{environment_id}'",
        "pvci_environmentinventoryid,pvci_environmentid,pvci_environmenturl",
    )
    if not inventory:
        raise RuntimeError(f"Environment Inventory row {environment_id} was not found.")
    request_key = f"transcript-verify-smoke-{uuid.uuid4()}"
    request_id = dv.create(
        "pvci_transcriptaccessrequests",
        {
            "pvci_name": "Verification smoke - PVE Dev",
            "pvci_requestkey": request_key,
            "pvci_environmentid": environment_id,
            "pvci_environmenturl": environment_url,
            "pvci_action": "Verify",
            "pvci_requestedmode": "SourceManaged",
            "pvci_status": "Pending",
            "pvci_requestedon": datetime.now(timezone.utc).isoformat(),
            "pvci_EnvironmentInventoryId@odata.bind": (
                f"/pvci_environmentinventories({inventory['pvci_environmentinventoryid']})"
            ),
        },
        in_solution=False,
    )
    return {
        "requestId": request_id,
        "requestKey": request_key,
        "inventoryId": inventory["pvci_environmentinventoryid"],
    }


def request_status(dv: Dv, request_key: str) -> dict[str, Any]:
    request = dv.find(
        "pvci_transcriptaccessrequests",
        f"pvci_requestkey eq '{request_key}'",
        (
            "pvci_transcriptaccessrequestid,pvci_requestkey,pvci_status,pvci_accessstatus,"
            "pvci_roleverified,pvci_elevationcleanupverified,pvci_evidence,pvci_error,"
            "pvci_processedon,_pvci_environmentinventoryid_value"
        ),
    )
    if not request:
        raise RuntimeError(f"Verification request {request_key} was not found.")
    inventory_id = request.get("_pvci_environmentinventoryid_value")
    inventory = None
    if inventory_id:
        inventory = dv.find(
            "pvci_environmentinventories",
            f"pvci_environmentinventoryid eq {inventory_id}",
            (
                "pvci_environmentinventoryid,pvci_transcriptonboardingmode,"
                "pvci_transcriptonboardingstatus,pvci_transcriptaccessstatus,"
                "pvci_transcriptaccessroleverified,pvci_transcriptelevationcleanupverified,"
                "pvci_transcriptcollectorenabled,pvci_transcriptaccesslastverifiedon,"
                "pvci_transcriptonboardinglasterror"
            ),
        )
    return {"request": request, "inventory": inventory}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--request-key")
    args = parser.parse_args()

    token, dataverse_url = get_token_from_config(args.config)
    dv = Dv(f"{dataverse_url}/api/data/v9.1", token)
    if not args.request_key:
        require_authorized_config(args.config)
    result = (
        request_status(dv, args.request_key)
        if args.request_key
        else create_request(dv, get_config(args.config))
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()