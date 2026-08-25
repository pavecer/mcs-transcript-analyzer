#!/usr/bin/env python3
"""Invoke pvci_ImportCreditUsageBatch with a normalized JSON payload."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config, require_authorized_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload_file")
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    require_authorized_config(args.config)

    payload_text = Path(args.payload_file).read_text(encoding="utf-8")
    payload = json.loads(payload_text)
    schema_version = str((payload.get("syncRun") or {}).get("schemaVersion") or "1")
    token, dv_url = get_token_from_config(args.config)
    response = requests.post(
        f"{dv_url}/api/data/v9.1/pvci_ImportCreditUsageBatch",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "OData-Version": "4.0",
            "OData-MaxVersion": "4.0",
        },
        json={
            "PayloadJson": payload_text,
            "SourceSchemaVersion": schema_version,
            "DryRun": args.dry_run,
        },
        timeout=180,
    )
    if not response.ok:
        raise SystemExit(f"Import failed: {response.status_code} {response.text[:1200]}")
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()