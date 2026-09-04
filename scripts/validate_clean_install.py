#!/usr/bin/env python3
"""Validate a fresh three-package managed installation in a target environment."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
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
ENVIRONMENT_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


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
    enablement_paths = _require_object(
        code_apps.get("enablementPaths"), "prerequisites.codeApps.enablementPaths"
    )
    group_rule = _require_object(
        code_apps.get("environmentGroupRule"),
        "prerequisites.codeApps.environmentGroupRule",
    )
    if (
        set(enablement_paths) != {"direct", "environmentGroup"}
        or not isinstance(code_apps.get("preflightCommand"), str)
        or "--preflight-only" not in code_apps["preflightCommand"]
        or not isinstance(code_apps.get("enableAndVerifyCommand"), str)
        or "--enable-code-apps" not in code_apps["enableAndVerifyCommand"]
        or group_rule
        != {
            "catalogNumber": 23,
            "name": "Power Apps code apps",
            "ruleSetId": "CodeAppsFeature",
            "environmentApiVersion": "2024-10-01",
            "policyApiVersion": "2021-10-01-preview",
            "publishedRulesEnforced": True,
            "locksEnvironmentSetting": True,
            "canSatisfyPerEnvironmentEnablement": (
                "Only after the group rule is applied to the member and the exact "
                "environment setting API returns true."
            ),
        }
    ):
        raise ValueError("clean-install contract Code Apps enablement paths are invalid")
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


def environment_id(value: str) -> str:
    if not ENVIRONMENT_ID_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError("environment ID must be a GUID")
    return value.lower()


def extract_access_token(output: str) -> str:
    match = JWT_PATTERN.search(output)
    if not match:
        raise RuntimeError("PAC did not return a Power Platform access token")
    return match.group(0)


def get_pac_power_platform_token() -> str:
    try:
        result = subprocess.run(
            ["pac", "auth", "token"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("PAC token acquisition failed") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"PAC token acquisition failed: {detail}")
    return extract_access_token(result.stdout)


def _case_insensitive_value(row: dict, key: str) -> object:
    normalized = key.lower()
    for candidate, value in row.items():
        if candidate.lower() == normalized:
            return value
    return None


class PowerPlatformSettingsReader:
    def __init__(self, token: str) -> None:
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

    def get_settings(self, target_environment_id: str, api_version: str, setting: str) -> dict:
        response = self.session.get(
            f"https://api.powerplatform.com/environmentmanagement/environments/{target_environment_id}/settings",
            params={"$select": f"id,{setting}", "api-version": api_version},
            headers=self.headers,
            timeout=90,
        )
        response.raise_for_status()
        return response.json()

    def update_settings(
        self,
        target_environment_id: str,
        api_version: str,
        settings: dict[str, object],
    ) -> dict:
        response = self.session.patch(
            f"https://api.powerplatform.com/environmentmanagement/environments/{target_environment_id}/settings",
            params={"api-version": api_version},
            json=settings,
            headers=self.headers,
            timeout=90,
        )
        response.raise_for_status()
        return response.json()

    def get_environment(self, target_environment_id: str, api_version: str) -> dict:
        response = self.session.get(
            "https://api.powerplatform.com/environmentmanagement/environments",
            params={
                "$filter": f"id eq '{target_environment_id}'",
                "$select": "id,environmentGroupId,protectionLevel,state",
                "api-version": api_version,
            },
            headers=self.headers,
            timeout=90,
        )
        response.raise_for_status()
        return response.json()

    def get_group_policies(self, group_id: str, api_version: str) -> dict:
        response = self.session.get(
            f"https://api.powerplatform.com/governance/environmentGroups/{group_id}/ruleBasedPolicies",
            params={"api-version": api_version, "includeCustomerContent": "true"},
            headers=self.headers,
            timeout=90,
        )
        response.raise_for_status()
        return response.json()


def validate_code_apps_preflight(
    reader: PowerPlatformSettingsReader,
    target_environment_id: str,
    code_apps_contract: dict,
    expected_tenant_id: str | None = None,
) -> dict:
    official_api = code_apps_contract["officialApi"]
    setting = official_api["property"]
    response = reader.get_settings(
        target_environment_id,
        official_api["apiVersion"],
        setting,
    )
    rows = response.get("objectResult")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise RuntimeError("Code Apps preflight did not return exactly one environment setting row")
    row = rows[0]
    returned_id = _case_insensitive_value(row, "id")
    if not isinstance(returned_id, str) or returned_id.lower() != target_environment_id.lower():
        raise RuntimeError("Code Apps preflight response environment does not match the target")
    effective_value = _case_insensitive_value(row, setting)
    if effective_value is True:
        return {
            "status": "ok",
            "environmentId": returned_id,
            "setting": setting,
            "effectiveValue": True,
            "enablementSource": "environment",
            "source": "Power Platform Environment Management Settings API",
        }
    if effective_value is False:
        raise RuntimeError(
            "Code Apps effective setting is not On; set it directly or add the managed "
            "environment to a group with the published Power Apps code apps rule"
        )
    group_rule = code_apps_contract["environmentGroupRule"]
    environment_response = reader.get_environment(
        target_environment_id,
        group_rule["environmentApiVersion"],
    )
    environments = environment_response.get("value")
    if not isinstance(environments, list) or len(environments) != 1 or not isinstance(environments[0], dict):
        raise RuntimeError("Code Apps inherited preflight did not return exactly one target environment")
    environment = environments[0]
    grouped_environment_id = _case_insensitive_value(environment, "id")
    if (
        not isinstance(grouped_environment_id, str)
        or grouped_environment_id.lower() != target_environment_id.lower()
    ):
        raise RuntimeError("Code Apps inherited preflight environment does not match the target")
    group_id = _case_insensitive_value(environment, "environmentGroupId")
    if not isinstance(group_id, str) or not ENVIRONMENT_ID_PATTERN.fullmatch(group_id):
        raise RuntimeError("Code Apps setting is unresolved and the target has no environment group")
    if _case_insensitive_value(environment, "protectionLevel") != "Standard":
        raise RuntimeError("Code Apps environment-group target is not a Managed Environment")
    policies_response = reader.get_group_policies(group_id, group_rule["policyApiVersion"])
    policies = policies_response.get("value")
    if not isinstance(policies, list):
        raise RuntimeError("Code Apps environment-group policies are unavailable")
    matching_rule_sets: list[dict] = []
    for policy in policies:
        if not isinstance(policy, dict):
            continue
        policy_tenant_id = _case_insensitive_value(policy, "tenantId")
        if (
            expected_tenant_id
            and isinstance(policy_tenant_id, str)
            and policy_tenant_id.lower() != expected_tenant_id.lower()
        ):
            raise RuntimeError("Code Apps environment-group policy tenant does not match")
        rule_sets = _case_insensitive_value(policy, "ruleSets")
        if not isinstance(rule_sets, list):
            continue
        matching_rule_sets.extend(
            rule_set
            for rule_set in rule_sets
            if isinstance(rule_set, dict)
            and _case_insensitive_value(rule_set, "id") == group_rule["ruleSetId"]
        )
    if len(matching_rule_sets) != 1:
        raise RuntimeError("Code Apps environment-group policy is missing or ambiguous")
    inputs = _case_insensitive_value(matching_rule_sets[0], "inputs")
    inherited_value = (
        _case_insensitive_value(inputs, setting) if isinstance(inputs, dict) else None
    )
    if inherited_value is not True:
        raise RuntimeError("Code Apps environment-group policy does not enable code apps")
    raise RuntimeError(
        "Code Apps group policy is published On but has not materialized on the target; "
        "apply the group rules after adding the environment, then rerun preflight until "
        "the exact environment setting API returns true"
    )


def enable_code_apps(
    reader: PowerPlatformSettingsReader,
    target_environment_id: str,
    code_apps_contract: dict,
) -> None:
    official_api = code_apps_contract["officialApi"]
    setting = official_api["property"]
    response = reader.update_settings(
        target_environment_id,
        official_api["apiVersion"],
        {setting: True},
    )
    errors = response.get("errors")
    if errors:
        raise RuntimeError(f"Code Apps enable operation returned errors: {errors}")


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
    parser.add_argument("--environment-url", type=environment_url)
    parser.add_argument("--environment-id", type=environment_id)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--enable-code-apps", action="store_true")
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
    if args.enable_code_apps and not args.preflight_only:
        parser.error("--enable-code-apps requires --preflight-only")
    if args.preflight_only:
        if not args.environment_id:
            parser.error("--preflight-only requires --environment-id")
        token = get_pac_power_platform_token()
        if token_tenant_id(token) != config["tenantId"]:
            raise RuntimeError(
                "PAC Power Platform token tenant does not match the authorized configuration; "
                "select the authorized PAC profile before preflight"
            )
        settings_reader = PowerPlatformSettingsReader(token)
        if args.enable_code_apps:
            enable_code_apps(
                settings_reader,
                args.environment_id,
                contract["prerequisites"]["codeApps"],
            )
        result = validate_code_apps_preflight(
            settings_reader,
            args.environment_id,
            contract["prerequisites"]["codeApps"],
            config["tenantId"],
        )
        result["enableRequested"] = args.enable_code_apps
        print(json.dumps(result, indent=2))
        return
    if not args.environment_url:
        parser.error("--environment-url is required unless --preflight-only is used")
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