#!/usr/bin/env python3
"""Read a bounded source transcript batch and invoke the central collector Custom API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token, get_token_from_config, require_authorized_config  # noqa: E402


API_NAME = "pvci_ImportCentralTranscriptBatch"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--registry", default="output/transcript-source-registry.json")
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    require_authorized_config(args.config)

    if args.limit < 1 or args.limit > 25:
        raise SystemExit("--limit must be from 1 to 25")

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    source = next(
        (item for item in registry.get("sources", []) if item["environmentId"].lower() == args.environment_id.lower()),
        None,
    )
    if not source or not source.get("enabled"):
        raise SystemExit("The selected environment is not an enabled transcript source.")

    source_token = get_token(
        config["tenantId"],
        config["oauth"]["clientId"],
        f"{source['dataverseUrl']}/.default",
        allow_interactive=False,
    )
    source_response = requests.get(
        f"{source['dataverseUrl']}/api/data/v9.1/conversationtranscripts",
        params={
            "$select": "conversationtranscriptid,metadata,content,createdon",
            "$orderby": "createdon desc",
            "$top": str(args.limit),
        },
        headers={"Authorization": f"Bearer {source_token}", "Accept": "application/json"},
        timeout=90,
    )
    source_response.raise_for_status()
    rows = source_response.json().get("value", [])
    if not rows:
        raise SystemExit("The selected environment returned no transcript rows.")

    collector_token, collector_url = get_token_from_config(args.config)
    import_response = requests.post(
        f"{collector_url}/api/data/v9.1/{API_NAME}",
        headers={
            "Authorization": f"Bearer {collector_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={
            "PayloadJson": json.dumps({"value": rows}),
            "SourceTenantId": registry["tenantId"],
            "SourceEnvironmentId": source["environmentId"],
            "SourceEnvironmentName": source["environmentName"],
            "SourceDataverseUrl": source["dataverseUrl"],
            "SourceSchemaVersion": "central-transcript-v1",
            "DryRun": args.dry_run,
            "IncludeTraces": False,
            "Reprocess": False,
        },
        timeout=180,
    )
    if not import_response.ok:
        raise RuntimeError(f"{API_NAME} failed: {import_response.status_code} {import_response.text[:1000]}")
    result = import_response.json()
    print(json.dumps({
        "status": "ok",
        "sourceEnvironment": source["environmentName"],
        "sourceRows": len(rows),
        "import": result,
    }, indent=2))


if __name__ == "__main__":
    main()