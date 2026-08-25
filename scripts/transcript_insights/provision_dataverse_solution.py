#!/usr/bin/env python3
"""Provision Dataverse solution and custom tables for transcript analytics.

This script creates:
- Publisher
- Solution
- Tables required for dual-endpoint transcript ingestion

Requires Dataverse SDK and a valid DATAVERSE_URL connection.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from azure.identity import InteractiveBrowserCredential

from dv_token import require_authorized_tenant


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--definition",
        default="solution/pvConversationInsights/solution-definition.json",
        help="Path to solution definition JSON",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env containing DATAVERSE_URL and auth-related settings",
    )
    args = parser.parse_args()

    load_env_file(Path(args.env_file))

    dataverse_url = os.environ.get("DATAVERSE_URL")
    if not dataverse_url:
        raise RuntimeError("DATAVERSE_URL is required. Set it in .env or environment variables.")
    tenant_id = os.environ.get("POWER_PLATFORM_TENANT_ID")
    if not tenant_id:
        raise RuntimeError("POWER_PLATFORM_TENANT_ID is required for write authorization.")
    require_authorized_tenant(tenant_id)

    from PowerPlatform.Dataverse.client import DataverseClient

    definition = json.loads(Path(args.definition).read_text(encoding="utf-8"))
    solution_def = definition["solution"]

    credential = None
    try:
        from auth import get_credential  # type: ignore

        credential = get_credential()
    except Exception:
        credential = InteractiveBrowserCredential()

    client = DataverseClient(dataverse_url, credential)

    publisher_unique = solution_def["publisher"]["uniqueName"]
    publisher_prefix = solution_def["publisher"]["prefix"]
    publisher_display = solution_def["publisher"]["displayName"]

    pub_pages = client.records.get(
        "publisher",
        filter=f"uniquename eq '{publisher_unique}'",
        select=["publisherid", "uniquename"],
        top=1,
    )
    pub_rows = [r for p in pub_pages for r in p]

    if pub_rows:
        publisher_id = pub_rows[0]["publisherid"]
        print(f"Publisher exists: {publisher_unique}")
    else:
        publisher_id = client.records.create(
            "publisher",
            {
                "uniquename": publisher_unique,
                "friendlyname": publisher_display,
                "customizationprefix": publisher_prefix,
                "description": "Publisher for transcript analytics solution",
            },
        )
        print(f"Created publisher: {publisher_unique}")

    solution_unique = solution_def["uniqueName"]
    solution_display = solution_def["displayName"]
    solution_version = solution_def["version"]

    sol_pages = client.records.get(
        "solution",
        filter=f"uniquename eq '{solution_unique}'",
        select=["solutionid", "uniquename"],
        top=1,
    )
    sol_rows = [r for p in sol_pages for r in p]

    if sol_rows:
        print(f"Solution exists: {solution_unique}")
    else:
        client.records.create(
            "solution",
            {
                "uniquename": solution_unique,
                "friendlyname": solution_display,
                "version": solution_version,
                "publisherid@odata.bind": f"/publishers({publisher_id})",
            },
        )
        print(f"Created solution: {solution_unique}")

    for table in definition.get("tables", []):
        schema_name = table["schemaName"]
        primary_column = table["primaryColumn"]
        columns = table["columns"]

        # Attempt create; if already exists, continue with add_columns.
        try:
            client.tables.create(
                schema_name,
                columns,
                solution=solution_unique,
                primary_column=primary_column,
            )
            print(f"Created table: {schema_name}")
        except Exception as exc:
            print(f"Create table skipped or failed for {schema_name}: {exc}")
            try:
                created = client.tables.add_columns(schema_name, columns)
                print(f"Added/validated columns for {schema_name}: {created}")
            except Exception as add_exc:
                print(f"Add columns failed for {schema_name}: {add_exc}")

    print("Provisioning completed.")


if __name__ == "__main__":
    main()
