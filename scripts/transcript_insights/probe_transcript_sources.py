#!/usr/bin/env python3
"""Probe tenant environments for central conversation transcript collection.

The input is the read-only environment inventory returned by ``pac admin list --json``
or the Power Platform for Admins V2 connector. The probe checks Dataverse access to
``conversationtranscripts`` with an organization-scoped token and emits a safe source
registry without transcript content or record identifiers.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token  # noqa: E402


def load_inventory(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("value"), list):
        return payload["value"]
    raise ValueError("Environment inventory must be a JSON array or an object with a value array.")


def run_pac_admin_list(output: Path) -> None:
    result = subprocess.run(
        ["pac", "admin", "list", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    output.write_text(result.stdout, encoding="utf-8")


def classify_response(response: requests.Response) -> tuple[str, str | None, int | None]:
    if response.status_code == 200:
        try:
            count = len(response.json().get("value", []))
        except (ValueError, AttributeError):
            return "error", "invalid_json", None
        return ("readable_with_rows" if count else "readable_empty"), None, count
    if response.status_code in (401, 403):
        return "access_denied", "dataverse_read_not_available", None
    if response.status_code in (404, 410):
        return "unavailable", "dataverse_not_available", None
    return "error", f"http_{response.status_code}", None


def probe_environment(
    environment: dict[str, Any],
    tenant_id: str,
    client_id: str,
    timeout: int,
) -> dict[str, Any]:
    environment_id = str(environment.get("EnvironmentId") or environment.get("id") or "")
    environment_url = str(environment.get("EnvironmentUrl") or environment.get("url") or "").rstrip("/")
    display_name = str(environment.get("DisplayName") or environment.get("displayName") or environment_id)
    result: dict[str, Any] = {
        "tenantId": tenant_id,
        "environmentId": environment_id,
        "environmentName": display_name,
        "dataverseUrl": environment_url,
        "enabled": False,
        "status": "invalid_configuration",
    }
    if not environment_id or not environment_url:
        result["reason"] = "missing_environment_identity"
        return result

    try:
        token = get_token(tenant_id, client_id, f"{environment_url}/.default", allow_interactive=False)
        response = requests.get(
            f"{environment_url}/api/data/v9.1/conversationtranscripts",
            params={"$select": "conversationtranscriptid", "$top": "1"},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "OData-Version": "4.0",
                "OData-MaxVersion": "4.0",
            },
            timeout=timeout,
        )
        status, reason, sample_count = classify_response(response)
        result["status"] = status
        result["enabled"] = status in ("readable_with_rows", "readable_empty")
        if reason:
            result["reason"] = reason
        if sample_count is not None:
            result["sampleCount"] = sample_count
    except requests.RequestException as exc:
        result["status"] = "error"
        result["reason"] = type(exc).__name__
    except RuntimeError as exc:
        result["status"] = "auth_error"
        result["reason"] = str(exc)[:200]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--inventory", type=Path, help="JSON from pac admin list --json")
    parser.add_argument("--output", type=Path, default=Path("output/transcript-source-registry.json"))
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    inventory_path = args.inventory or Path("output/test-tenant-admin-environments.json")
    if not inventory_path.exists():
        run_pac_admin_list(inventory_path)

    environments = load_inventory(inventory_path)
    generated = datetime.now(timezone.utc).isoformat()
    registry = {
        "schemaVersion": "transcript-source-registry-v1",
        "generatedUtc": generated,
        "tenantId": config["tenantId"],
        "collectorEnvironmentId": config["environmentId"],
        "sources": [
            probe_environment(
                environment,
                config["tenantId"],
                config["oauth"]["clientId"],
                args.timeout,
            )
            for environment in environments
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "output": str(args.output),
        "sources": len(registry["sources"]),
        "enabled": sum(1 for source in registry["sources"] if source["enabled"]),
        "accessDenied": sum(1 for source in registry["sources"] if source["status"] == "access_denied"),
    }, indent=2))


if __name__ == "__main__":
    main()