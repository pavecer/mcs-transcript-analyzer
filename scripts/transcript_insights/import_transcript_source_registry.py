#!/usr/bin/env python3
"""Persist transcript source probe results into the collector environment inventory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config, require_authorized_config  # noqa: E402
from register_plugin import Dv  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--registry", default="output/transcript-source-registry.json")
    parser.add_argument(
        "--collector-environment-id",
        action="append",
        default=[],
        help="Environment with a bound source connection; repeat for each enabled collector source",
    )
    parser.add_argument("--disable-all-collectors", action="store_true")
    args = parser.parse_args()
    require_authorized_config(args.config)

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    token, dv_url = get_token_from_config(args.config)
    dv = Dv(f"{dv_url}/api/data/v9.1", token)
    created = 0
    updated = 0
    collector_environment_ids = {value.lower() for value in args.collector_environment_id}

    for source in registry.get("sources", []):
        environment_id = source["environmentId"]
        existing = dv.find(
            "pvci_environmentinventories",
            f"pvci_environmentid eq '{environment_id}'",
            "pvci_environmentinventoryid,pvci_environmentid",
        )
        payload = {
            "pvci_name": source["environmentName"],
            "pvci_sourcekey": f"{registry['tenantId']}:{environment_id}".lower(),
            "pvci_tenantid": registry["tenantId"],
            "pvci_environmentid": environment_id,
            "pvci_displayname": source["environmentName"],
            "pvci_environmenturl": source.get("dataverseUrl"),
            "pvci_hasdataverse": bool(source.get("dataverseUrl")),
            "pvci_transcriptaccessstatus": source["status"],
            "pvci_transcriptaccessreason": source.get("reason"),
            "pvci_transcriptprobeon": registry["generatedUtc"],
            "pvci_transcriptsamplecount": source.get("sampleCount", 0),
            "pvci_transcriptcollectorenabled": False if args.disable_all_collectors else (
                environment_id.lower() in collector_environment_ids
                if collector_environment_ids else bool(source.get("enabled"))
            ),
            "pvci_inventorysource": "transcript-source-probe",
            "pvci_sourceschemaversion": registry["schemaVersion"],
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        if existing:
            dv.update("pvci_environmentinventories", existing["pvci_environmentinventoryid"], payload)
            updated += 1
        else:
            dv.create("pvci_environmentinventories", payload, in_solution=False)
            created += 1

    print(json.dumps({"status": "ok", "created": created, "updated": updated}, indent=2))


if __name__ == "__main__":
    main()