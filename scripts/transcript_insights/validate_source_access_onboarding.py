#!/usr/bin/env python3
"""Validate least-privilege transcript source onboarding in a disposable environment."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import msal
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token  # noqa: E402


AUTHORIZED_TENANT_ID = "1938ee32-a258-454c-b8db-3a928341bd69"
DISPOSABLE_NAME_PREFIX = "PVCI Onboarding E2E "
BASELINE_ROLE = "PVCI Transcript Collector Baseline"
COLLECTOR_ROLE = "PVCI Transcript Collector"
TRANSCRIPT_PRIVILEGE = "prvReadconversationtranscript"
GLOBAL_DEPTH = "Global"


def headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "OData-Version": "4.0",
        "OData-MaxVersion": "4.0",
    }


def get_one(session: requests.Session, url: str, token: str) -> dict[str, Any] | None:
    response = session.get(url, headers=headers(token), timeout=60)
    response.raise_for_status()
    rows = response.json().get("value", [])
    return rows[0] if rows else None


def entity_id(response: requests.Response) -> str:
    location = response.headers.get("OData-EntityId") or response.headers.get("odata-entityid") or ""
    match = re.search(r"\(([0-9a-f-]{36})\)$", location, re.IGNORECASE)
    if not match:
        raise RuntimeError("Dataverse did not return the created role identifier.")
    return match.group(1)


def ensure_role(
    session: requests.Session,
    base_url: str,
    token: str,
    business_unit_id: str,
    role_name: str,
    privilege_id: str | None = None,
) -> str:
    escaped_name = role_name.replace("'", "''")
    role = get_one(
        session,
        f"{base_url}/roles?$select=roleid&$filter=name eq '{escaped_name}' "
        f"and _businessunitid_value eq {business_unit_id}&$top=1",
        token,
    )
    if role:
        role_id = role["roleid"]
    else:
        response = session.post(
            f"{base_url}/roles",
            headers=headers(token),
            json={
                "name": role_name,
                "description": "Disposable PVCI source-access onboarding validation role.",
                "businessunitid@odata.bind": f"/businessunits({business_unit_id})",
            },
            timeout=60,
        )
        response.raise_for_status()
        role_id = entity_id(response)

    if privilege_id:
        current = session.get(
            f"{base_url}/RetrieveRolePrivilegesRole(RoleId={role_id})",
            headers=headers(token),
            timeout=60,
        )
        current.raise_for_status()
        current_ids = {
            str(item["PrivilegeId"]).lower()
            for item in current.json().get("RolePrivileges", [])
        }
        if privilege_id.lower() not in current_ids:
            response = session.post(
                f"{base_url}/roles({role_id})/Microsoft.Dynamics.CRM.AddPrivilegesRole",
                headers=headers(token),
                json={
                    "Privileges": [
                        {
                            "Depth": GLOBAL_DEPTH,
                            "PrivilegeId": privilege_id,
                            "BusinessUnitId": business_unit_id,
                            "PrivilegeName": TRANSCRIPT_PRIVILEGE,
                        }
                    ]
                },
                timeout=60,
            )
            response.raise_for_status()
    return role_id


def prepare_roles(session: requests.Session, environment_url: str, token: str) -> None:
    base_url = f"{environment_url}/api/data/v9.2"
    business_unit = get_one(
        session,
        f"{base_url}/businessunits?$select=businessunitid&$filter=_parentbusinessunitid_value eq null&$top=1",
        token,
    )
    privilege = get_one(
        session,
        f"{base_url}/privileges?$select=privilegeid&$filter=name eq '{TRANSCRIPT_PRIVILEGE}'&$top=1",
        token,
    )
    if not business_unit or not privilege:
        raise RuntimeError("The root business unit or transcript privilege was not found.")
    business_unit_id = business_unit["businessunitid"]
    ensure_role(session, base_url, token, business_unit_id, BASELINE_ROLE)
    ensure_role(
        session,
        base_url,
        token,
        business_unit_id,
        COLLECTOR_ROLE,
        privilege["privilegeid"],
    )


def parse_service_principal(output: str) -> tuple[str, str]:
    app_match = re.search(
        r"(?:Application|App|Client)\s*(?:Id|ID)\s*(?::|=)?\s*([0-9a-f-]{36})",
        output,
        re.IGNORECASE,
    )
    secret_match = re.search(
        r"(?:Client\s*)?Secret(?:\s*Value)?\s*(?::|=)?\s*(\S+)",
        output,
        re.IGNORECASE,
    )
    if not app_match or not secret_match:
        raise RuntimeError("PAC output did not contain the expected application credentials.")
    return app_match.group(1), secret_match.group(1)


def run_pac(*arguments: str, capture_output: bool = False) -> str:
    result = subprocess.run(
        ["pac", *arguments],
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        raise RuntimeError(f"PAC command failed with exit code {result.returncode}.")
    return output if capture_output else ""


def parse_service_principal_ids(output: str) -> set[str]:
    return {
        match.lower()
        for match in re.findall(
            r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            output,
        )
    }


def list_service_principal_ids(application_name: str) -> set[str]:
    output = run_pac(
        "admin",
        "list-service-principal",
        "--filter",
        application_name,
        "--max",
        "100",
        capture_output=True,
    )
    return parse_service_principal_ids(output)


def assert_disposable_environment(environment_id: str, environment_url: str) -> None:
    output = run_pac("admin", "list", "--json", capture_output=True)
    inventory = json.loads(output.strip())
    normalized_url = environment_url.rstrip("/").lower()
    matches = [
        environment
        for environment in inventory
        if str(environment.get("EnvironmentId", "")).lower() == environment_id.lower()
        and str(environment.get("EnvironmentUrl", "")).rstrip("/").lower() == normalized_url
    ]
    if len(matches) != 1:
        raise RuntimeError("The environment ID and URL do not identify one tenant environment.")
    environment = matches[0]
    if environment.get("Type") != "Sandbox" or not str(environment.get("DisplayName", "")).startswith(
        DISPOSABLE_NAME_PREFIX
    ):
        raise RuntimeError("Refusing to run outside a named PVCI onboarding E2E sandbox.")


def acquire_app_token(tenant_id: str, app_id: str, secret: str, environment_url: str) -> str:
    app = msal.ConfidentialClientApplication(
        app_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=secret,
    )
    result = app.acquire_token_for_client(scopes=[f"{environment_url}/.default"])
    token = result.get("access_token")
    if not token:
        raise RuntimeError(f"Application token acquisition failed: {result.get('error', 'unknown_error')}")
    return token


def probe_transcripts(session: requests.Session, environment_url: str, token: str) -> int:
    response = session.get(
        f"{environment_url}/api/data/v9.2/conversationtranscripts",
        params={"$select": "conversationtranscriptid", "$top": "1"},
        headers=headers(token),
        timeout=60,
    )
    return response.status_code


def application_user_role_names(
    session: requests.Session,
    environment_url: str,
    token: str,
    app_id: str,
) -> set[str]:
    response = session.get(
        f"{environment_url}/api/data/v9.2/systemusers",
        params={
            "$select": "systemuserid",
            "$filter": f"applicationid eq {app_id}",
            "$expand": "systemuserroles_association($select=name)",
            "$top": "1",
        },
        headers=headers(token),
        timeout=60,
    )
    response.raise_for_status()
    rows = response.json().get("value", [])
    if not rows:
        raise RuntimeError("The Dataverse application user was not found.")
    return {
        role["name"]
        for role in rows[0].get("systemuserroles_association", [])
    }


def validate(args: argparse.Namespace) -> dict[str, Any]:
    if args.tenant_id != AUTHORIZED_TENANT_ID:
        raise RuntimeError("Refusing to write outside the authorized development/test tenant.")
    environment_url = args.environment_url.rstrip("/")
    assert_disposable_environment(args.environment_id, environment_url)
    admin_token = get_token(
        args.tenant_id,
        args.public_client_id,
        f"{environment_url}/.default",
        allow_interactive=False,
    )
    app_id: str | None = None
    initial_app_ids = list_service_principal_ids(args.application_name)
    result: dict[str, Any] = {"environmentUrl": environment_url}
    with requests.Session() as session:
        prepare_roles(session, environment_url, admin_token)
        try:
            output = run_pac(
                "admin",
                "create-service-principal",
                "--environment",
                environment_url,
                "--name",
                args.application_name,
                "--role",
                BASELINE_ROLE,
                capture_output=True,
            )
            app_id, secret = parse_service_principal(output)
            app_token = acquire_app_token(args.tenant_id, app_id, secret, environment_url)
            baseline_status = probe_transcripts(session, environment_url, app_token)
            result["baselineStatus"] = baseline_status
            if baseline_status not in (401, 403):
                raise RuntimeError(f"Expected baseline denial, received HTTP {baseline_status}.")

            run_pac(
                "admin",
                "assign-user",
                "--environment",
                environment_url,
                "--user",
                app_id,
                "--role",
                COLLECTOR_ROLE,
                "--application-user",
            )
            app_token = acquire_app_token(args.tenant_id, app_id, secret, environment_url)
            granted_status = probe_transcripts(session, environment_url, app_token)
            result["grantedStatus"] = granted_status
            if granted_status != 200:
                raise RuntimeError(f"Expected successful transcript read, received HTTP {granted_status}.")
            role_names = application_user_role_names(
                session,
                environment_url,
                admin_token,
                app_id,
            )
            if "System Administrator" in role_names:
                raise RuntimeError("The collector application user received System Administrator.")
            expected_roles = {BASELINE_ROLE, COLLECTOR_ROLE}
            if not expected_roles.issubset(role_names):
                raise RuntimeError("The collector application user is missing an expected test role.")
            result["systemAdministratorAssigned"] = False
            result["assignedRoles"] = sorted(role_names)
            result["status"] = "passed"
            return result
        finally:
            cleanup_ids = ({app_id.lower()} if app_id else set()) | (
                list_service_principal_ids(args.application_name) - initial_app_ids
            )
            for cleanup_id in cleanup_ids:
                run_pac("admin", "application", "unregister", "--application-id", cleanup_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--environment-url", required=True)
    parser.add_argument("--public-client-id", required=True)
    parser.add_argument("--application-name", default="PVCI Collector E2E 20260821")
    args = parser.parse_args()
    print(json.dumps(validate(args), indent=2))


if __name__ == "__main__":
    main()