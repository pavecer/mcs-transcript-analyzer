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
    load_contract,
    token_tenant_id,
)


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
            contract["evidence"]["cleanup"]["completionCriteria"],
            {
                "allRequired": True,
                "targetAbsentFromTenantInventory": True,
                "targetDataverseNoLongerResolves": True,
            },
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