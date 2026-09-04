import argparse
import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_clean_install import (
    DEFAULT_CONTRACT,
    RELEASE_CONFIG,
    environment_url,
    environment_id,
    extract_access_token,
    load_contract,
    token_tenant_id,
    validate_code_apps_preflight,
)


class SettingsReader:
    def __init__(self, response: dict):
        self.response = response
        self.calls = []

    def get_settings(self, target_environment_id: str, api_version: str, setting: str) -> dict:
        self.calls.append((target_environment_id, api_version, setting))
        return self.response


class ValidateCleanInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release = json.loads(RELEASE_CONFIG.read_text(encoding="utf-8"))
        cls.contract = json.loads(DEFAULT_CONTRACT.read_text(encoding="utf-8"))

    def write_contract(self, contract: dict) -> Path:
        temporary = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", delete=False
        )
        with temporary:
            json.dump(contract, temporary)
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        return Path(temporary.name)

    def test_environment_url_accepts_https_origin_and_removes_trailing_slash(self):
        self.assertEqual(
            environment_url("https://example.crm4.dynamics.com/"),
            "https://example.crm4.dynamics.com",
        )

    def test_environment_url_rejects_non_origin_values(self):
        invalid_values = (
            "http://example.crm4.dynamics.com",
            "https://example.crm4.dynamics.com/api/data/v9.2",
            "https://example.crm4.dynamics.com/?target=other",
            "https://user@example.crm4.dynamics.com",
        )
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                environment_url(value)

    def test_environment_id_accepts_guid_and_normalizes_case(self):
        self.assertEqual(
            environment_id("ABCDEF12-3456-7890-ABCD-EF1234567890"),
            "abcdef12-3456-7890-abcd-ef1234567890",
        )

    def test_environment_id_rejects_non_guid(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            environment_id("PVE Dev")

    def test_extract_access_token_finds_jwt_in_pac_output(self):
        token = "eyJheader.eyJpayload.signature"
        self.assertEqual(extract_access_token(f"Access token:\n{token}\n"), token)

    def test_extract_access_token_rejects_missing_jwt(self):
        with self.assertRaisesRegex(RuntimeError, "did not return"):
            extract_access_token("Connected as user")

    def test_token_tenant_id_extracts_tid_claim(self):
        claims = base64.urlsafe_b64encode(
            json.dumps({"tid": "tenant-id"}).encode("utf-8")
        ).decode("ascii").rstrip("=")
        self.assertEqual(token_tenant_id(f"header.{claims}.signature"), "tenant-id")

    def test_checked_in_contract_loads_and_matches_release_order(self):
        contract = load_contract(DEFAULT_CONTRACT, self.release)
        self.assertEqual(contract["schemaVersion"], 1)
        self.assertEqual(
            [item["releaseKey"] for item in contract["artifacts"]["order"]],
            ["core", "credits", "codeApp"],
        )
        self.assertTrue(contract["installationAcceptance"]["required"])
        self.assertFalse(
            contract["browserValidation"]["requiredForInstallationAcceptance"]
        )
        self.assertTrue(
            contract["browserValidation"]["authenticatedFunctionalSmoke"][
                "independentGate"
            ]
        )
        self.assertEqual(
            contract["prerequisites"]["codeApps"]["environmentGroupRule"]["catalogNumber"],
            23,
        )
        self.assertIn(
            "--preflight-only",
            contract["prerequisites"]["codeApps"]["preflightCommand"],
        )
        self.assertEqual(
            contract["evidence"]["cleanup"]["completionCriteria"],
            {
                "allRequired": True,
                "targetAbsentFromTenantInventory": True,
                "targetDataverseNoLongerResolves": True,
            },
        )

    def test_code_apps_preflight_accepts_exact_effective_true(self):
        target = "abcdef12-3456-7890-abcd-ef1234567890"
        reader = SettingsReader(
            {"objectResult": [{"Id": target.upper(), "PowerApps_AllowCodeApps": True}]}
        )

        result = validate_code_apps_preflight(
            reader,
            target,
            self.contract["prerequisites"]["codeApps"],
        )

        self.assertTrue(result["effectiveValue"])
        self.assertEqual(
            reader.calls,
            [(target, "2024-10-01", "powerApps_AllowCodeApps")],
        )

    def test_code_apps_preflight_rejects_false_or_missing_setting(self):
        target = "abcdef12-3456-7890-abcd-ef1234567890"
        for row in ({"id": target, "powerApps_AllowCodeApps": False}, {"id": target}):
            with self.subTest(row=row), self.assertRaisesRegex(
                RuntimeError, "effective setting is not On"
            ):
                validate_code_apps_preflight(
                    SettingsReader({"objectResult": [row]}),
                    target,
                    self.contract["prerequisites"]["codeApps"],
                )

    def test_code_apps_preflight_rejects_wrong_environment(self):
        with self.assertRaisesRegex(RuntimeError, "does not match the target"):
            validate_code_apps_preflight(
                SettingsReader(
                    {
                        "objectResult": [
                            {
                                "id": "00000000-0000-0000-0000-000000000000",
                                "powerApps_AllowCodeApps": True,
                            }
                        ]
                    }
                ),
                "abcdef12-3456-7890-abcd-ef1234567890",
                self.contract["prerequisites"]["codeApps"],
            )

    def test_code_apps_preflight_rejects_ambiguous_response(self):
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            validate_code_apps_preflight(
                SettingsReader({"objectResult": []}),
                "abcdef12-3456-7890-abcd-ef1234567890",
                self.contract["prerequisites"]["codeApps"],
            )

    def test_contract_rejects_wrong_artifact_order(self):
        contract = copy.deepcopy(self.contract)
        contract["artifacts"]["order"][1:3] = reversed(
            contract["artifacts"]["order"][1:3]
        )
        with self.assertRaisesRegex(ValueError, "artifact order"):
            load_contract(self.write_contract(contract), self.release)

    def test_contract_rejects_unsupported_schema_version(self):
        contract = copy.deepcopy(self.contract)
        contract["schemaVersion"] = 2
        with self.assertRaisesRegex(ValueError, "schemaVersion must be 1"):
            load_contract(self.write_contract(contract), self.release)

    def test_contract_rejects_malformed_structural_requirements(self):
        contract = copy.deepcopy(self.contract)
        contract["structuralRequirements"]["customApis"] = "not-an-array"
        with self.assertRaisesRegex(ValueError, "customApis"):
            load_contract(self.write_contract(contract), self.release)

    def test_contract_rejects_stale_code_apps_group_rule_number(self):
        contract = copy.deepcopy(self.contract)
        contract["prerequisites"]["codeApps"]["environmentGroupRule"]["catalogNumber"] = 22
        with self.assertRaisesRegex(ValueError, "enablement paths"):
            load_contract(self.write_contract(contract), self.release)

    def test_contract_rejects_missing_gate_separation(self):
        cases = (
            ("installationAcceptance",),
            ("browserValidation", "launchAuthorizationAndRuntimeDelivery"),
            ("browserValidation", "authenticatedFunctionalSmoke"),
        )
        for path in cases:
            contract = copy.deepcopy(self.contract)
            parent = contract
            for part in path[:-1]:
                parent = parent[part]
            del parent[path[-1]]
            with self.subTest(path=path), self.assertRaises(ValueError):
                load_contract(self.write_contract(contract), self.release)

    def test_contract_rejects_malformed_gate_separation(self):
        cases = (
            (("installationAcceptance", "required"), False),
            (("browserValidation", "requiredForInstallationAcceptance"), True),
            (
                (
                    "browserValidation",
                    "launchAuthorizationAndRuntimeDelivery",
                    "criteria",
                ),
                "not-an-array",
            ),
            (
                (
                    "browserValidation",
                    "authenticatedFunctionalSmoke",
                    "independentGate",
                ),
                False,
            ),
        )
        for path, value in cases:
            contract = copy.deepcopy(self.contract)
            parent = contract
            for part in path[:-1]:
                parent = parent[part]
            parent[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                load_contract(self.write_contract(contract), self.release)

    def test_contract_requires_cleanup_completion_criteria(self):
        for key in (
            "allRequired",
            "targetAbsentFromTenantInventory",
            "targetDataverseNoLongerResolves",
        ):
            contract = copy.deepcopy(self.contract)
            del contract["evidence"]["cleanup"]["completionCriteria"][key]
            with self.subTest(key=key), self.assertRaisesRegex(
                ValueError, "cleanup completion"
            ):
                load_contract(self.write_contract(contract), self.release)

    def test_contract_requires_cleanup_convergence_rules(self):
        for key in (
            "operationNotStartableAfterSuccessfulDelete",
            "activeLifecycleCanInitiateDeleteFalse",
            "pacAdminStatusAuthoritative",
            "repeatDeleteWhileConvergingAllowed",
            "concurrentDeletesAllowed",
            "verificationMode",
        ):
            contract = copy.deepcopy(self.contract)
            del contract["evidence"]["cleanup"]["convergence"][key]
            with self.subTest(key=key), self.assertRaisesRegex(
                ValueError, "cleanup convergence"
            ):
                load_contract(self.write_contract(contract), self.release)


if __name__ == "__main__":
    unittest.main()