import json
import unittest

from scripts.transcript_insights.create_inventory_sync_flow import (
    ADMIN_API_VERSION,
    ADMIN_REF_LOGICAL,
    DATAVERSE_REF_LOGICAL,
    ENVIRONMENT_PAGE_SIZE,
    MAX_ENVIRONMENT_PAGES,
    MAX_RESOURCE_PAGES,
    TENANT_PARAMETER,
    build_clientdata,
    build_definition,
    resolve_connection_id,
)


class InventorySyncFlowTests(unittest.TestCase):
    def test_definition_uses_verified_admin_v2_operations(self) -> None:
        definition = build_definition()
        environments = definition["actions"]["Until_environment_pages_complete"]
        resources = definition["actions"]["Until_resource_pages_complete"]
        environment_action = environments["actions"]["List_environment_page"]
        resource_action = resources["actions"]["Query_agent_resources"]

        self.assertEqual("ListEnvironmentsForUser", environment_action["inputs"]["host"]["operationId"])
        self.assertEqual(ADMIN_API_VERSION, environment_action["inputs"]["parameters"]["api-version"])
        self.assertEqual(ENVIRONMENT_PAGE_SIZE, environment_action["inputs"]["parameters"]["$top"])
        self.assertEqual("QueryResources", resource_action["inputs"]["host"]["operationId"])
        self.assertEqual("PowerPlatformResources", resource_action["inputs"]["parameters"]["body/TableName"])
        self.assertEqual(100, resource_action["inputs"]["parameters"]["body/Options/Top"])
        serialized = json.dumps(resource_action["inputs"]["parameters"]["body/Clauses"])
        self.assertIn("microsoft.copilotstudio/agents", serialized)
        self.assertNotIn("authentication", environment_action["inputs"])
        self.assertNotIn("authentication", resource_action["inputs"])

    def test_bounded_paging_and_page_level_imports(self) -> None:
        definition = build_definition()
        environments = definition["actions"]["Until_environment_pages_complete"]
        resources = definition["actions"]["Until_resource_pages_complete"]
        self.assertEqual(MAX_ENVIRONMENT_PAGES, environments["limit"]["count"])
        self.assertEqual(MAX_RESOURCE_PAGES, resources["limit"]["count"])
        self.assertIn("Import_environment_page", environments["actions"])
        self.assertIn("Import_agent_page", resources["actions"])
        self.assertEqual(
            "@string(outputs('Compose_environment_payload'))",
            environments["actions"]["Import_environment_page"]["inputs"]["parameters"]["item/PayloadJson"],
        )
        self.assertEqual(
            ENVIRONMENT_PAGE_SIZE,
            environments["actions"]["Increment_environment_skip"]["inputs"]["value"],
        )
        self.assertEqual(
            "@coalesce(body('Query_agent_resources')?['skipToken'], '')",
            resources["actions"]["Set_resource_skip_token"]["inputs"]["value"],
        )

    def test_inventory_audit_is_separate_from_credit_sync(self) -> None:
        actions = build_definition()["actions"]
        payload = actions["Compose_inventory_sync_payload"]["inputs"]
        self.assertIn("inventorySyncRun", payload)
        self.assertNotIn("syncRun", payload)
        self.assertIn(f"parameters('{TENANT_PARAMETER}')", payload["tenantId"])
        self.assertEqual(
            "@string(outputs('Compose_inventory_sync_payload'))",
            actions["Finalize_inventory_sync"]["inputs"]["parameters"]["item/PayloadJson"],
        )

    def test_clientdata_uses_solution_connection_references(self) -> None:
        references = json.loads(build_clientdata())["properties"]["connectionReferences"]
        self.assertEqual(ADMIN_REF_LOGICAL, references["shared_powerplatformadminv2"]["connection"]["connectionReferenceLogicalName"])
        self.assertEqual(DATAVERSE_REF_LOGICAL, references["shared_commondataserviceforapps"]["connection"]["connectionReferenceLogicalName"])

    def test_connection_resolution_requires_target_binding(self) -> None:
        self.assertEqual("provided", resolve_connection_id("provided", {"connectionid": "existing"}))
        self.assertEqual("existing", resolve_connection_id(None, {"connectionid": "existing"}))
        with self.assertRaises(SystemExit):
            resolve_connection_id(None, None)


if __name__ == "__main__":
    unittest.main()