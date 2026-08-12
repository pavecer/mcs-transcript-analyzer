import json
import unittest

from scripts.transcript_insights.create_credit_governance_flow import (
    API_NAME,
    DATAVERSE_REF_LOGICAL,
    HTTP_REF_LOGICAL,
    SCHEMA_VERSION,
    TENANT_PARAMETER,
    THRESHOLD_PATH,
    build_clientdata,
    build_definition,
    resolve_connection_id,
)


class CreditGovernanceFlowTests(unittest.TestCase):
    def test_definition_is_read_only_against_power_platform_api(self) -> None:
        definition = build_definition()
        action = definition["actions"]["Get_resource_thresholds"]
        serialized = json.dumps(definition)

        self.assertEqual("GET", action["inputs"]["parameters"]["request/method"])
        self.assertEqual(
            f"@concat('/v1.0/tenants/', parameters('{TENANT_PARAMETER}'), '/entitlements/MCSMessages/resourceThresholds')",
            action["inputs"]["parameters"]["request/url"],
        )
        self.assertIn("/v1.0/tenants/", action["inputs"]["parameters"]["request/url"])
        self.assertIn("/entitlements/MCSMessages/resourceThresholds", action["inputs"]["parameters"]["request/url"])
        self.assertNotIn('"PUT"', serialized)
        self.assertNotIn('"PATCH"', serialized)
        self.assertNotIn("/threshold?", serialized)

    def test_definition_imports_thresholds_with_separate_health(self) -> None:
        actions = build_definition()["actions"]
        payload = actions["Compose_governance_payload"]["inputs"]
        importer = actions["Import_governance_snapshot"]

        self.assertEqual("@body('Get_resource_thresholds')", payload["resourceThresholds"])
        self.assertIn("governanceSyncRun", payload)
        self.assertEqual(f"@parameters('{TENANT_PARAMETER}')", payload["tenantId"])
        self.assertEqual(API_NAME, importer["inputs"]["parameters"]["actionName"])
        self.assertEqual(SCHEMA_VERSION, importer["inputs"]["parameters"]["item/SourceSchemaVersion"])

    def test_clientdata_uses_dedicated_power_platform_reference(self) -> None:
        references = json.loads(build_clientdata())["properties"]["connectionReferences"]
        self.assertEqual(HTTP_REF_LOGICAL, references["shared_webcontents"]["connection"]["connectionReferenceLogicalName"])
        self.assertEqual(DATAVERSE_REF_LOGICAL, references["shared_commondataserviceforapps"]["connection"]["connectionReferenceLogicalName"])

    def test_connection_binding_is_required(self) -> None:
        self.assertEqual("provided", resolve_connection_id("provided", {"connectionid": "existing"}))
        self.assertEqual("existing", resolve_connection_id(None, {"connectionid": "existing"}))
        with self.assertRaises(SystemExit):
            resolve_connection_id(None, None)


if __name__ == "__main__":
    unittest.main()