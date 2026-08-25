#!/usr/bin/env python3
"""Provision transcript analytics solution using Dataverse Web API.

Creates publisher, solution, and custom tables with core columns.
Idempotent where possible.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token, require_authorized_tenant  # noqa: E402


@dataclass
class Config:
    tenant_id: str
    client_id: str
    dataverse_url: str
    dataverse_scope: str
    solution_unique: str
    solution_display: str
    solution_version: str
    publisher_unique: str
    publisher_display: str
    publisher_prefix: str


def label(text: str) -> dict[str, Any]:
    return {
        "@odata.type": "Microsoft.Dynamics.CRM.Label",
        "LocalizedLabels": [
            {
                "@odata.type": "Microsoft.Dynamics.CRM.LocalizedLabel",
                "Label": text,
                "LanguageCode": 1033,
            }
        ],
    }


def load_config(path: Path, definition_path: Path) -> Config:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    definition = json.loads(definition_path.read_text(encoding="utf-8"))

    dv_url = cfg["dataverseUrl"].rstrip("/")
    dataverse_scope = cfg["oauth"].get("dataverseScope", f"{dv_url}/.default")

    s = definition["solution"]
    return Config(
        tenant_id=cfg["tenantId"],
        client_id=cfg["oauth"]["clientId"],
        dataverse_url=dv_url,
        dataverse_scope=dataverse_scope,
        solution_unique=s["uniqueName"],
        solution_display=s["displayName"],
        solution_version=s["version"],
        publisher_unique=s["publisher"]["uniqueName"],
        publisher_display=s["publisher"]["displayName"],
        publisher_prefix=s["publisher"]["prefix"],
    )


def acquire(cfg: Config) -> str:
    return get_token(cfg.tenant_id, cfg.client_id, cfg.dataverse_scope)


def dv_headers(token: str, solution_unique: str | None = None) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "OData-Version": "4.0",
        "OData-MaxVersion": "4.0",
    }
    if solution_unique:
        h["MSCRM.SolutionUniqueName"] = solution_unique
    return h


def query_one(session: requests.Session, url: str, headers: dict[str, str]) -> dict[str, Any] | None:
    r = session.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    vals = r.json().get("value", [])
    return vals[0] if vals else None


def ensure_publisher(session: requests.Session, cfg: Config, token: str) -> str:
    base = f"{cfg.dataverse_url}/api/data/v9.1"
    h = dv_headers(token)
    existing = query_one(
        session,
        f"{base}/publishers?$select=publisherid,uniquename&$filter=uniquename eq '{cfg.publisher_unique}'&$top=1",
        h,
    )
    if existing:
        return existing["publisherid"]

    payload = {
        "uniquename": cfg.publisher_unique,
        "friendlyname": cfg.publisher_display,
        "customizationprefix": cfg.publisher_prefix,
        "description": "Publisher for transcript analytics",
    }
    r = session.post(f"{base}/publishers", headers=h, json=payload, timeout=60)
    r.raise_for_status()
    entity_url = r.headers.get("OData-EntityId") or r.headers.get("odata-entityid")
    if not entity_url:
        lookup = query_one(
            session,
            f"{base}/publishers?$select=publisherid&$filter=uniquename eq '{cfg.publisher_unique}'&$top=1",
            h,
        )
        if not lookup:
            raise RuntimeError("Publisher creation succeeded but lookup failed")
        return lookup["publisherid"]

    return entity_url.split("(")[-1].split(")")[0]


def ensure_solution(session: requests.Session, cfg: Config, token: str, publisher_id: str) -> None:
    base = f"{cfg.dataverse_url}/api/data/v9.1"
    h = dv_headers(token)
    existing = query_one(
        session,
        f"{base}/solutions?$select=solutionid,uniquename&$filter=uniquename eq '{cfg.solution_unique}'&$top=1",
        h,
    )
    if existing:
        return

    payload = {
        "uniquename": cfg.solution_unique,
        "friendlyname": cfg.solution_display,
        "version": cfg.solution_version,
        "publisherid@odata.bind": f"/publishers({publisher_id})",
    }
    r = session.post(f"{base}/solutions", headers=h, json=payload, timeout=60)
    r.raise_for_status()


def ensure_environment_variable(
    session: requests.Session,
    cfg: Config,
    token: str,
    variable: dict[str, Any],
) -> str:
    base = f"{cfg.dataverse_url}/api/data/v9.1"
    schema_name = variable["schemaName"]
    existing = query_one(
        session,
        f"{base}/environmentvariabledefinitions?$select=environmentvariabledefinitionid"
        f"&$filter=schemaname eq '{schema_name}'&$top=1",
        dv_headers(token),
    )
    if existing:
        return existing["environmentvariabledefinitionid"]

    if variable.get("type", "string") != "string":
        raise ValueError(f"Unsupported environment variable type for {schema_name}")
    payload: dict[str, Any] = {
        "schemaname": schema_name,
        "displayname": variable.get("displayName", schema_name),
        "description": variable.get("description", ""),
        "type": 100000000,
        "isrequired": bool(variable.get("required", False)),
    }
    if variable.get("defaultValue") is not None:
        payload["defaultvalue"] = str(variable["defaultValue"])
    response = session.post(
        f"{base}/environmentvariabledefinitions",
        headers=dv_headers(token, cfg.solution_unique),
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    entity_url = response.headers.get("OData-EntityId") or response.headers.get("odata-entityid") or ""
    return entity_url.split("(")[-1].split(")")[0]


def ensure_entity(
    session: requests.Session,
    cfg: Config,
    token: str,
    table: dict[str, Any],
) -> str:
    meta_base = f"{cfg.dataverse_url}/api/data/v9.1"
    schema_name = table["schemaName"]
    display_name = table.get("displayName", schema_name)
    display_collection_name = table.get("displayCollectionName", display_name + "s")
    logical_name = schema_name.lower()
    entity_payload = {
        "@odata.type": "Microsoft.Dynamics.CRM.EntityMetadata",
        "SchemaName": schema_name,
        "DisplayName": label(display_name),
        "DisplayCollectionName": label(display_collection_name),
        "Description": label(display_name),
        "OwnershipType": table.get("ownershipType", "UserOwned"),
        "HasActivities": False,
        "HasNotes": True,
        "IsActivity": False,
        "PrimaryNameAttribute": "pvci_name",
        "Attributes": [
            {
                "@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata",
                "SchemaName": "pvci_Name",
                "DisplayName": label("Name"),
                "RequiredLevel": {"Value": "ApplicationRequired"},
                "MaxLength": 200,
                "IsPrimaryName": True,
            }
        ],
    }

    r = session.post(
        f"{meta_base}/EntityDefinitions",
        headers=dv_headers(token, cfg.solution_unique),
        json=entity_payload,
        timeout=90,
    )
    if not r.ok:
        body = r.text.lower()
        if "already exists" not in body and "duplicate" not in body:
            r.raise_for_status()
    return logical_name


def add_attribute(
    session: requests.Session,
    cfg: Config,
    token: str,
    entity_logical: str,
    schema_name: str,
    column: str | dict[str, Any],
) -> None:
    base = f"{cfg.dataverse_url}/api/data/v9.1"
    spec = {"type": column} if isinstance(column, str) else column
    col_type = spec["type"]
    display_name = spec.get("displayName", schema_name)

    if col_type in ("string",):
        payload = {
            "@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata",
            "SchemaName": schema_name,
            "DisplayName": label(display_name),
            "MaxLength": spec.get("maxLength", 1000),
            "RequiredLevel": {"Value": "None"},
        }
    elif col_type in ("text",):
        payload = {
            "@odata.type": "Microsoft.Dynamics.CRM.MemoAttributeMetadata",
            "SchemaName": schema_name,
            "DisplayName": label(display_name),
            "MaxLength": 1048576,
            "Format": "TextArea",
            "RequiredLevel": {"Value": "None"},
        }
    elif col_type in ("datetime",):
        payload = {
            "@odata.type": "Microsoft.Dynamics.CRM.DateTimeAttributeMetadata",
            "SchemaName": schema_name,
            "DisplayName": label(display_name),
            "Format": "DateAndTime",
            "ImeMode": "Auto",
            "RequiredLevel": {"Value": "None"},
        }
    elif col_type in ("int", "integer"):
        payload = {
            "@odata.type": "Microsoft.Dynamics.CRM.IntegerAttributeMetadata",
            "SchemaName": schema_name,
            "DisplayName": label(display_name),
            "MinValue": -2147483648,
            "MaxValue": 2147483647,
            "RequiredLevel": {"Value": "None"},
        }
    elif col_type in ("bool", "boolean"):
        payload = {
            "@odata.type": "Microsoft.Dynamics.CRM.BooleanAttributeMetadata",
            "SchemaName": schema_name,
            "DisplayName": label(display_name),
            "RequiredLevel": {"Value": "None"},
            "DefaultValue": False,
            "OptionSet": {
                "@odata.type": "Microsoft.Dynamics.CRM.BooleanOptionSetMetadata",
                "TrueOption": {"Value": 1, "Label": label("Yes")},
                "FalseOption": {"Value": 0, "Label": label("No")},
            },
        }
    elif col_type in ("decimal",):
        payload = {
            "@odata.type": "Microsoft.Dynamics.CRM.DecimalAttributeMetadata",
            "SchemaName": schema_name,
            "DisplayName": label(display_name),
            "MinValue": spec.get("minValue", -100000000000.0),
            "MaxValue": spec.get("maxValue", 100000000000.0),
            "Precision": spec.get("precision", 4),
            "RequiredLevel": {"Value": "None"},
        }
    else:
        payload = {
            "@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata",
            "SchemaName": schema_name,
            "DisplayName": label(display_name),
            "MaxLength": 1000,
            "RequiredLevel": {"Value": "None"},
        }

    r = session.post(
        f"{base}/EntityDefinitions(LogicalName='{entity_logical}')/Attributes",
        headers=dv_headers(token, cfg.solution_unique),
        json=payload,
        timeout=90,
    )
    if not r.ok:
        body = r.text.lower()
        if "already exists" not in body and "duplicate" not in body:
            r.raise_for_status()


def add_alternate_key(
    session: requests.Session,
    cfg: Config,
    token: str,
    entity_logical: str,
    key: dict[str, Any],
) -> str:
    base = f"{cfg.dataverse_url}/api/data/v9.1"
    payload = {
        "@odata.type": "Microsoft.Dynamics.CRM.EntityKeyMetadata",
        "SchemaName": key["schemaName"],
        "DisplayName": label(key.get("displayName", key["schemaName"])),
        "KeyAttributes": key["columns"],
    }
    r = session.post(
        f"{base}/EntityDefinitions(LogicalName='{entity_logical}')/Keys",
        headers=dv_headers(token, cfg.solution_unique),
        json=payload,
        timeout=120,
    )
    if r.ok:
        return "created"
    body = r.text.lower()
    if "already exists" in body or "duplicate" in body or "0x80048d0b" in body:
        return "exists"
    return f"failed: {r.status_code} {r.text[:200]}"


def add_lookup(
    session: requests.Session,
    cfg: Config,
    token: str,
    referencing_entity: str,
    lookup: dict[str, Any],
) -> str:
    base = f"{cfg.dataverse_url}/api/data/v9.1"
    payload = {
        "@odata.type": "Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata",
        "SchemaName": lookup["relationshipName"],
        "ReferencedEntity": lookup["referencedTable"],
        "ReferencingEntity": referencing_entity,
        "Lookup": {
            "@odata.type": "Microsoft.Dynamics.CRM.LookupAttributeMetadata",
            "SchemaName": lookup["schemaName"],
            "DisplayName": label(lookup["displayName"]),
            "RequiredLevel": {"Value": "None"},
        },
    }
    r = session.post(
        f"{base}/RelationshipDefinitions",
        headers=dv_headers(token, cfg.solution_unique),
        json=payload,
        timeout=120,
    )
    if r.ok:
        return "created"
    body = r.text.lower()
    if "already exists" in body or "duplicate" in body or "navigationpropertyname" in body and "not unique" in body:
        return "exists"
    return f"failed: {r.status_code} {r.text[:200]}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument(
        "--definition",
        default="solution/pvConversationInsights/solution-definition.json",
    )
    args = parser.parse_args()

    cfg = load_config(Path(args.config), Path(args.definition))
    require_authorized_tenant(cfg.tenant_id)
    definition = json.loads(Path(args.definition).read_text(encoding="utf-8"))
    token = acquire(cfg)

    with requests.Session() as session:
        publisher_id = ensure_publisher(session, cfg, token)
        ensure_solution(session, cfg, token, publisher_id)

        for variable in definition.get("environmentVariables", []):
            variable_id = ensure_environment_variable(session, cfg, token, variable)
            print(f"environment variable {variable['schemaName']}: {variable_id}")

        created_tables = []
        for table in definition.get("tables", []):
            logical = ensure_entity(session, cfg, token, table)
            for col_name, col_type in table.get("columns", {}).items():
                add_attribute(session, cfg, token, logical, col_name, col_type)
            created_tables.append({"schemaName": table["schemaName"], "logicalName": logical})

        for table in definition.get("tables", []):
            logical = table["schemaName"].lower()
            for key in table.get("alternateKeys", []):
                state = add_alternate_key(session, cfg, token, logical, key)
                print(f"alternate key {key['schemaName']} on {logical}: {state}")

        for table in definition.get("tables", []):
            logical = table["schemaName"].lower()
            for lk in table.get("lookups", []):
                state = add_lookup(session, cfg, token, logical, lk)
                print(f"lookup {lk['schemaName']} on {logical}: {state}")

    print(
        json.dumps(
            {
                "status": "ok",
                "solution": cfg.solution_unique,
                "publisher": cfg.publisher_unique,
                "tables": created_tables,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
