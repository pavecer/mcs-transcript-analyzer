#!/usr/bin/env python3
"""Validate a fresh three-package managed installation in a target environment."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "transcript_solution_config.dev.json"
RELEASE_CONFIG = ROOT / "config" / "release-packages.json"
DEFAULT_CONTRACT = ROOT / "config" / "clean-install-contract.json"
KNOWN_RELEASE_KEYS = ("core", "credits", "codeApp")
EXPECTED_CLEANUP_COMPLETION_CRITERIA = {
    "allRequired": True,
    "targetAbsentFromTenantInventory": True,
    "targetDataverseNoLongerResolves": True,
}
EXPECTED_CLEANUP_CONVERGENCE = {
    "operationNotStartableAfterSuccessfulDelete": "deletion-in-progress",
    "activeLifecycleCanInitiateDeleteFalse": "deletion-in-progress",
    "pacAdminStatusAuthoritative": False,
    "repeatDeleteWhileConvergingAllowed": False,
    "concurrentDeletesAllowed": False,
    "verificationMode": "one-later-verification",
}


def _require_object(value: object, location: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"clean-install contract {location} must be an object")
    return value


def _require_string_list(value: object, location: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ValueError(f"clean-install contract {location} must be a non-empty string array")
    return value


def _release_values(release: dict, paths: list[str], location: str) -> set[str]:
    values: set[str] = set()
    for path in paths:
        current: object = release
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                raise ValueError(
                    f"clean-install contract {location} references missing release path {path}"
                )
            current = current[part]
        values.update(_require_string_list(current, f"release path {path}"))
    return values


def validate_contract(contract: dict, release: dict) -> None:
    if contract.get("schemaVersion") != 1:
        raise ValueError("clean-install contract schemaVersion must be 1")

    policy_categories = _require_object(contract.get("policyCategories"), "policyCategories")
    if set(policy_categories) != {"mandatory", "conditional"}:
        raise ValueError(
            "clean-install contract policyCategories must define mandatory and conditional"
        )

    artifacts = _require_object(contract.get("artifacts"), "artifacts")
    if artifacts.get("releaseConfig") != "config/release-packages.json":
        raise ValueError(
            "clean-install contract artifacts.releaseConfig must be config/release-packages.json"
        )
    order = artifacts.get("order")
    if not isinstance(order, list) or any(not isinstance(item, dict) for item in order):
        raise ValueError("clean-install contract artifacts.order must be an object array")
    release_keys = [item.get("releaseKey") for item in order]
    if release_keys != list(KNOWN_RELEASE_KEYS) or set(release_keys) != set(release):
        raise ValueError(
            "clean-install contract artifact order must be exactly core, credits, codeApp "
            "and match release-packages.json"
        )
    if [item.get("optional") for item in order] != [False, True, True]:
        raise ValueError(
            "clean-install contract artifact optionality must be core required and credits/codeApp optional"
        )

    requirements = _require_object(
        artifacts.get("requirementsFromReleaseConfig"),
        "artifacts.requirementsFromReleaseConfig",
    )
    required_requirement_keys = {
        "tables",
        "roles",
        "workflows",
        "connectionReferences",
        "environmentVariables",
    }
    if set(requirements) != required_requirement_keys:
        raise ValueError(
            "clean-install contract release requirements must define tables, roles, workflows, "
            "connectionReferences, and environmentVariables"
        )
    for key in sorted(required_requirement_keys):
        paths = _require_string_list(requirements[key], f"release requirements {key}")
        _release_values(release, paths, f"release requirements {key}")

    prerequisites = _require_object(contract.get("prerequisites"), "prerequisites")
    code_apps = _require_object(prerequisites.get("codeApps"), "prerequisites.codeApps")
    if (
        code_apps.get("policyCategory") != "mandatory"
        or code_apps.get("defaultValue") != "Off"
        or code_apps.get("requiredValue") != "On"
        or code_apps.get("requiredBefore") != "codeApp import"
    ):
        raise ValueError(
            "clean-install contract Code Apps prerequisite must require On before codeApp import"
        )
    _require_string_list(code_apps.get("settingsPath"), "prerequisites.codeApps.settingsPath")
    official_api = _require_object(
        code_apps.get("officialApi"), "prerequisites.codeApps.officialApi"
    )
    permissions = _require_object(
        official_api.get("delegatedPermissions"),
        "prerequisites.codeApps.officialApi.delegatedPermissions",
    )
    if (
        official_api.get("property") != "powerApps_AllowCodeApps"
        or official_api.get("apiVersion") != "2024-10-01"
        or permissions.get("read") != "EnvironmentManagement.Settings.Read"
        or permissions.get("readWrite") != "EnvironmentManagement.Settings.ReadWrite"
    ):
        raise ValueError("clean-install contract official Code Apps API settings are invalid")

    structural = _require_object(
        contract.get("structuralRequirements"), "structuralRequirements"
    )
    _require_string_list(
        structural.get("coreConnectionReferences"),
        "structuralRequirements.coreConnectionReferences",
    )
    _require_string_list(structural.get("customApis"), "structuralRequirements.customApis")
    code_app = _require_object(
        structural.get("codeApp"), "structuralRequirements.codeApp"
    )
    if (
        code_app.get("componentType") != 300
        or code_app.get("expectedComponentCount") != 1
        or code_app.get("requiredComponentState") != 0
        or code_app.get("resolveTargetGeneratedApp") is not True
        or code_app.get("sourceAppIdPortable") is not False
    ):
        raise ValueError("clean-install contract code-app structural requirements are invalid")

    installation_acceptance = _require_object(
        contract.get("installationAcceptance"), "installationAcceptance"
    )
    if installation_acceptance.get("required") is not True:
        raise ValueError("clean-install contract installation acceptance must be required")
    _require_string_list(
        installation_acceptance.get("criteria"), "installationAcceptance.criteria"
    )

    browser = _require_object(contract.get("browserValidation"), "browserValidation")
    if browser.get("requiredForInstallationAcceptance") is not False:
        raise ValueError(
            "clean-install contract browser validation must not be required for installation acceptance"
        )
    launch_runtime = _require_object(
        browser.get("launchAuthorizationAndRuntimeDelivery"),
        "browserValidation.launchAuthorizationAndRuntimeDelivery",
    )
    if launch_runtime.get("independentGate") is not True:
        raise ValueError(
            "clean-install contract launch authorization and runtime delivery must be an independent gate"
        )
    _require_string_list(
        launch_runtime.get("criteria"),
        "browserValidation.launchAuthorizationAndRuntimeDelivery.criteria",
    )
    authenticated_smoke = _require_object(
        browser.get("authenticatedFunctionalSmoke"),
        "browserValidation.authenticatedFunctionalSmoke",
    )
    if authenticated_smoke.get("independentGate") is not True:
        raise ValueError(
            "clean-install contract authenticated functional smoke must be an independent gate"
        )
    _require_string_list(
        authenticated_smoke.get("criteria"),
        "browserValidation.authenticatedFunctionalSmoke.criteria",
    )
    direct_runtime = _require_object(
        browser.get("directRuntime"), "browserValidation.directRuntime"
    )
    if direct_runtime.get("diagnosticOnly") is not True:
        raise ValueError("clean-install contract direct runtime must be diagnostic only")

    evidence = _require_object(contract.get("evidence"), "evidence")
    cleanup = _require_object(evidence.get("cleanup"), "evidence.cleanup")
    if cleanup.get("required") is not True:
        raise ValueError("clean-install contract disposable-environment cleanup must be required")
    completion_criteria = _require_object(
        cleanup.get("completionCriteria"), "evidence.cleanup.completionCriteria"
    )
    if completion_criteria != EXPECTED_CLEANUP_COMPLETION_CRITERIA:
        raise ValueError(
            "clean-install contract cleanup completion requires target absence from tenant "
            "inventory and target Dataverse no longer resolving"
        )
    convergence = _require_object(
        cleanup.get("convergence"), "evidence.cleanup.convergence"
    )
    if convergence != EXPECTED_CLEANUP_CONVERGENCE:
        raise ValueError(
            "clean-install contract cleanup convergence must retain deletion-in-progress, "
            "non-authoritative status, one-later-verification, and no-repeat/no-concurrent-delete rules"
        )


def load_contract(path: Path, release: dict) -> dict:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to load clean-install contract {path}: {exc}") from exc
    contract = _require_object(contract, "root")
    validate_contract(contract, release)
    return contract


def token_tenant_id(token: str) -> str | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("access token is not a readable JWT") from exc
    tenant_id = claims.get("tid")
    return tenant_id if isinstance(tenant_id, str) else None


def environment_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("environment URL must be an HTTPS origin without a path")
    return f"https://{parsed.netloc}"


class DataverseReader:
    def __init__(self, target: str, token: str) -> None:
        self.target = target
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self.session = requests.Session()
        self.session.mount(
            "https://",
            HTTPAdapter(
                max_retries=Retry(
                    total=3,
                    connect=3,
                    read=3,
                    status=3,
                    status_forcelist=(429, 500, 502, 503, 504),
                )
            ),
        )

    def get_all(self, path: str, params: dict[str, str] | None = None) -> list[dict]:
        response = self.session.get(
            f"{self.target}/api/data/v9.2/{path}",
            params=params,
            headers=self.headers,
            timeout=90,
        )
        response.raise_for_status()
        body = response.json()
        rows = body.get("value", [])
        next_link = body.get("@odata.nextLink")
        while next_link:
            response = self.session.get(next_link, headers=self.headers, timeout=90)
            response.raise_for_status()
            body = response.json()
            rows.extend(body.get("value", []))
            next_link = body.get("@odata.nextLink")
        return rows


def validate(reader: DataverseReader, release: dict, contract: dict) -> dict:
    release_requirements = contract["artifacts"]["requirementsFromReleaseConfig"]
    structural_requirements = contract["structuralRequirements"]
    products = {
        settings["solutionUniqueName"]: settings["version"]
        for settings in release.values()
    }
    organizations = reader.get_all(
        "organizations",
        {"$select": "organizationid"},
    )
    if len(organizations) != 1:
        raise RuntimeError(f"Expected one organization row, found {len(organizations)}")

    solutions = reader.get_all(
        "solutions",
        {"$select": "solutionid,uniquename,version,ismanaged", "$top": "5000"},
    )
    installed = {row["uniquename"]: row for row in solutions if row.get("uniquename") in products}
    if set(installed) != set(products):
        raise RuntimeError(f"Installed product set mismatch: {sorted(installed)}")
    for name, version in products.items():
        row = installed[name]
        if row.get("version") != version or row.get("ismanaged") is not True:
            raise RuntimeError(f"Unexpected solution identity for {name}: {row}")

    entity_definitions = {
        row.get("LogicalName")
        for row in reader.get_all("EntityDefinitions", {"$select": "LogicalName"})
    }
    expected_tables = _release_values(
        release, release_requirements["tables"], "release requirements tables"
    )
    missing_tables = sorted(expected_tables - entity_definitions)
    if missing_tables:
        raise RuntimeError(f"Missing required tables: {missing_tables}")

    roles = {
        row.get("name")
        for row in reader.get_all("roles", {"$select": "name", "$top": "5000"})
    }
    expected_roles = _release_values(
        release, release_requirements["roles"], "release requirements roles"
    )
    if not expected_roles.issubset(roles):
        raise RuntimeError(f"Missing roles: {sorted(expected_roles - roles)}")

    workflows = reader.get_all(
        "workflows",
        {"$select": "name,statecode,statuscode,category", "$top": "5000"},
    )
    expected_workflows = _release_values(
        release, release_requirements["workflows"], "release requirements workflows"
    )
    workflow_rows = [row for row in workflows if row.get("name") in expected_workflows]
    found_workflows = {row.get("name") for row in workflow_rows}
    if found_workflows != expected_workflows:
        raise RuntimeError(f"Missing workflows: {sorted(expected_workflows - found_workflows)}")

    references = reader.get_all(
        "connectionreferences",
        {
            "$select": "connectionreferencelogicalname,connectionid,statecode,statuscode",
            "$top": "5000",
        },
    )
    expected_references = set(structural_requirements["coreConnectionReferences"]) | _release_values(
        release,
        release_requirements["connectionReferences"],
        "release requirements connectionReferences",
    )
    reference_rows = [
        row for row in references if row.get("connectionreferencelogicalname") in expected_references
    ]
    found_references = {row.get("connectionreferencelogicalname") for row in reference_rows}
    if found_references != expected_references:
        raise RuntimeError(f"Missing connection references: {sorted(expected_references - found_references)}")

    custom_apis = {
        row.get("uniquename")
        for row in reader.get_all("customapis", {"$select": "uniquename", "$top": "5000"})
    }
    expected_custom_apis = set(structural_requirements["customApis"])
    if not expected_custom_apis.issubset(custom_apis):
        raise RuntimeError(f"Missing Custom APIs: {sorted(expected_custom_apis - custom_apis)}")

    component_counts: dict[str, int] = {}
    code_app_components: list[dict] = []
    for name, row in installed.items():
        components = reader.get_all(
            "solutioncomponents",
            {
                "$select": "componenttype,objectid",
                "$filter": f"_solutionid_value eq {row['solutionid']}",
                "$top": "5000",
            },
        )
        component_counts[name] = len(components)
        if name == release["codeApp"]["solutionUniqueName"]:
            code_app_components = [
                item
                for item in components
                if item.get("componenttype")
                == structural_requirements["codeApp"]["componentType"]
            ]
    if len(code_app_components) != structural_requirements["codeApp"]["expectedComponentCount"]:
        raise RuntimeError(f"Expected one code-app component, got {code_app_components}")

    code_app_id = code_app_components[0]["objectid"]
    code_apps = reader.get_all(
        "canvasapps",
        {
            "$select": "canvasappid,name,displayname,appopenuri,componentstate",
            "$filter": f"canvasappid eq {code_app_id}",
        },
    )
    if len(code_apps) != 1:
        raise RuntimeError(f"Expected one target-generated code-app row, got {code_apps}")
    code_app = code_apps[0]
    if (
        code_app.get("componentstate")
        != structural_requirements["codeApp"]["requiredComponentState"]
    ):
        raise RuntimeError(f"Code app is not an active managed component: {code_app}")

    variable_definitions = {
        row.get("schemaname")
        for row in reader.get_all(
            "environmentvariabledefinitions",
            {"$select": "schemaname", "$top": "5000"},
        )
    }
    expected_variables = _release_values(
        release,
        release_requirements["environmentVariables"],
        "release requirements environmentVariables",
    )
    if not expected_variables.issubset(variable_definitions):
        raise RuntimeError(
            f"Missing environment variable definitions: {sorted(expected_variables - variable_definitions)}"
        )

    return {
        "status": "ok",
        "environment": reader.target,
        "organization": organizations[0],
        "solutions": {
            name: {"version": row["version"], "managed": row["ismanaged"]}
            for name, row in installed.items()
        },
        "componentCounts": component_counts,
        "requiredTables": len(expected_tables),
        "requiredRoles": sorted(expected_roles),
        "workflows": [
            {
                "name": row["name"],
                "statecode": row.get("statecode"),
                "statuscode": row.get("statuscode"),
            }
            for row in workflow_rows
        ],
        "connectionReferences": [
            {
                "name": row["connectionreferencelogicalname"],
                "configured": bool(row.get("connectionid")),
            }
            for row in reference_rows
        ],
        "customApis": sorted(expected_custom_apis),
        "codeApp": {
            key: code_app.get(key)
            for key in ("canvasappid", "name", "displayname", "appopenuri", "componentstate")
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment-url", required=True, type=environment_url)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "scripts" / "transcript_insights"))
    from dv_token import get_token, require_authorized_config

    config_path = args.config.resolve()
    require_authorized_config(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    release = json.loads(RELEASE_CONFIG.read_text(encoding="utf-8"))
    contract = load_contract(args.contract.resolve(), release)
    token = get_token(
        config["tenantId"],
        config["oauth"]["clientId"],
        f"{args.environment_url}/.default",
    )
    if token_tenant_id(token) != config["tenantId"]:
        raise RuntimeError("Target access token tenant does not match the authorized configuration")
    result = validate(DataverseReader(args.environment_url, token), release, contract)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()