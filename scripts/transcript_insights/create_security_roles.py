#!/usr/bin/env python3
"""Create and validate the least-privilege PVCI application security roles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config, require_authorized_config  # noqa: E402


SOLUTION = "pvConversationInsights"
APP_UNIQUE = "pvci_conversationinsights"
GLOBAL_DEPTH = "Global"


def headers(token: str, solution: str | None = None) -> dict[str, str]:
    result = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "OData-Version": "4.0",
        "OData-MaxVersion": "4.0",
    }
    if solution:
        result["MSCRM.SolutionUniqueName"] = solution
    return result


def privilege_name(action: str, table_schema_name: str) -> str:
    return f"prv{action}{table_schema_name}"


def table_schema_names(definition: dict[str, Any]) -> dict[str, str]:
    return {table["schemaName"].lower(): table["schemaName"] for table in definition["tables"]}


def required_privilege_names(role: dict[str, Any], schemas: dict[str, str]) -> set[str]:
    names: set[str] = set()
    for table, actions in role["tablePrivileges"].items():
        if table == "systemuser":
            names.update("prvReadUser" if action == "Read" else privilege_name(action, "User") for action in actions)
        else:
            names.update(privilege_name(action, schemas[table]) for action in actions)
    return names


def entity_id(response: requests.Response) -> str:
    location = response.headers.get("OData-EntityId") or response.headers.get("odata-entityid") or ""
    return location.split("(")[-1].split(")")[0]


def get_one(session: requests.Session, url: str, token: str) -> dict[str, Any] | None:
    response = session.get(url, headers=headers(token), timeout=60)
    response.raise_for_status()
    rows = response.json().get("value", [])
    return rows[0] if rows else None


def role_privileges(session: requests.Session, base: str, token: str, role_id: str) -> list[dict[str, Any]]:
    response = session.get(
        f"{base}/RetrieveRolePrivilegesRole(RoleId={role_id})",
        headers=headers(token),
        timeout=60,
    )
    response.raise_for_status()
    return response.json().get("RolePrivileges", [])


def resolve_privileges(
    session: requests.Session,
    base: str,
    token: str,
    names: set[str],
) -> dict[str, dict[str, Any]]:
    if not names:
        return {}
    expression = " or ".join(f"name eq '{name}'" for name in sorted(names))
    response = session.get(
        f"{base}/privileges?$select=privilegeid,name&$filter={expression}",
        headers=headers(token),
        timeout=60,
    )
    response.raise_for_status()
    resolved = {row["name"]: row for row in response.json().get("value", [])}
    missing = names - set(resolved)
    if missing:
        raise RuntimeError(f"Dataverse privileges are missing: {sorted(missing)}")
    return resolved


def add_privileges(
    session: requests.Session,
    base: str,
    token: str,
    role_id: str,
    privileges: list[dict[str, Any]],
) -> None:
    if not privileges:
        return
    response = session.post(
        f"{base}/roles({role_id})/Microsoft.Dynamics.CRM.AddPrivilegesRole",
        headers=headers(token),
        json={"Privileges": privileges},
        timeout=120,
    )
    response.raise_for_status()


def ensure_role(
    session: requests.Session,
    base: str,
    token: str,
    business_unit_id: str,
    app_opener_privileges: list[dict[str, Any]],
    role_definition: dict[str, Any],
    schemas: dict[str, str],
) -> str:
    name = role_definition["name"]
    escaped_name = name.replace("'", "''")
    existing = get_one(
        session,
        f"{base}/roles?$select=roleid,name&$filter=name eq '{escaped_name}' "
        f"and _businessunitid_value eq {business_unit_id}&$top=1",
        token,
    )
    if existing:
        role_id = existing["roleid"]
    else:
        response = session.post(
            f"{base}/roles",
            headers=headers(token, SOLUTION),
            json={
                "name": name,
                "description": role_definition["description"],
                "businessunitid@odata.bind": f"/businessunits({business_unit_id})",
            },
            timeout=90,
        )
        response.raise_for_status()
        role_id = entity_id(response)

    current = role_privileges(session, base, token, role_id)
    current_ids = {str(privilege["PrivilegeId"]).lower() for privilege in current}
    baseline = [privilege for privilege in app_opener_privileges if str(privilege["PrivilegeId"]).lower() not in current_ids]
    add_privileges(session, base, token, role_id, baseline)

    requested_names = required_privilege_names(role_definition, schemas)
    resolved = resolve_privileges(session, base, token, requested_names)
    current = role_privileges(session, base, token, role_id)
    current_ids = {str(privilege["PrivilegeId"]).lower() for privilege in current}
    additions = [
        {
            "Depth": GLOBAL_DEPTH,
            "PrivilegeId": privilege["privilegeid"],
            "BusinessUnitId": business_unit_id,
            "PrivilegeName": name,
        }
        for name, privilege in sorted(resolved.items())
        if privilege["privilegeid"].lower() not in current_ids
    ]
    add_privileges(session, base, token, role_id, additions)
    return role_id


def associate_app_role(
    session: requests.Session,
    base: str,
    token: str,
    app_id: str,
    role_id: str,
) -> None:
    response = session.post(
        f"{base}/appmodules({app_id})/appmoduleroles_association/$ref",
        headers=headers(token),
        json={"@odata.id": f"{base}/roles({role_id})"},
        timeout=60,
    )
    if response.status_code not in (204, 409):
        response.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument(
        "--definition",
        default="solution/pvConversationInsights/solution-definition.json",
    )
    args = parser.parse_args()
    require_authorized_config(args.config)

    definition = json.loads(Path(args.definition).read_text(encoding="utf-8"))
    token, dataverse_url = get_token_from_config(args.config)
    base = f"{dataverse_url}/api/data/v9.1"
    schemas = table_schema_names(definition)

    with requests.Session() as session:
        business_unit = get_one(
            session,
            f"{base}/businessunits?$select=businessunitid&$filter=_parentbusinessunitid_value eq null&$top=1",
            token,
        )
        if not business_unit:
            raise RuntimeError("Root business unit was not found.")
        business_unit_id = business_unit["businessunitid"]
        app_opener = get_one(
            session,
            f"{base}/roles?$select=roleid&$filter=name eq 'App Opener' "
            f"and _businessunitid_value eq {business_unit_id}&$top=1",
            token,
        )
        if not app_opener:
            raise RuntimeError("Built-in App Opener role was not found in the root business unit.")
        app_opener_privileges = role_privileges(session, base, token, app_opener["roleid"])
        app = get_one(
            session,
            f"{base}/appmodules?$select=appmoduleid&$filter=uniquename eq '{APP_UNIQUE}'&$top=1",
            token,
        )
        if not app:
            raise RuntimeError(f"Model-driven app {APP_UNIQUE} was not found.")

        result: dict[str, str] = {}
        for role_definition in definition["securityRoles"]:
            role_id = ensure_role(
                session,
                base,
                token,
                business_unit_id,
                app_opener_privileges,
                role_definition,
                schemas,
            )
            associate_app_role(session, base, token, app["appmoduleid"], role_id)
            result[role_definition["name"]] = role_id

    print(json.dumps({"status": "ok", "roles": result}, indent=2))


if __name__ == "__main__":
    main()