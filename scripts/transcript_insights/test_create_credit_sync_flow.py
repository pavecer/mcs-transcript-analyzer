import json
import unittest

from scripts.transcript_insights.create_credit_sync_flow import (
    API_NAME,
    DATAVERSE_REF_LOGICAL,
    HTTP_REF_LOGICAL,
    MAX_PAGES,
    PAGE_SIZE,
    TENANT_PARAMETER,
    TENANT_VARIABLE_SCHEMA,
    USER_CHUNK_SIZE,
    build_clientdata,
    build_definition,
    resolve_connection_id,
)


TENANT_ID = "11111111-2222-3333-4444-555555555555"


class CreditSyncFlowTests(unittest.TestCase):
    def test_definition_reads_only_expected_ppac_routes(self) -> None:
        definition = build_definition()
        until = definition["actions"]["Until_usage_complete"]
        usage = until["actions"]["Get_usage_page"]
        users = definition["actions"]["Get_user_usage"]
        capacity = definition["actions"]["Get_capacity"]

        self.assertEqual("GET", usage["inputs"]["parameters"]["request/method"])
        self.assertIn(f"parameters('{TENANT_PARAMETER}')", usage["inputs"]["parameters"]["request/url"])
        self.assertEqual("GET", capacity["inputs"]["parameters"]["request/method"])
        self.assertIn("/environments/entitlementConsumptions/MCSMessages", capacity["inputs"]["parameters"]["request/url"])
        self.assertEqual("GET", users["inputs"]["parameters"]["request/method"])
        self.assertIn(f"parameters('{TENANT_PARAMETER}')", users["inputs"]["parameters"]["request/url"])
        self.assertEqual({"Until_usage_complete": ["Succeeded"]}, users["runAfter"])
        self.assertEqual(
            {"Import_user_chunks": ["Succeeded", "Failed", "TimedOut"]},
            capacity["runAfter"],
        )
        self.assertEqual(MAX_PAGES, until["limit"]["count"])
        self.assertIn(f"pageSize={PAGE_SIZE}", usage["inputs"]["parameters"]["request/url"])
        self.assertIn(
            "body('Get_usage_page')?['value']",
            until["actions"]["Set_has_more"]["inputs"]["value"],
        )

    def test_definition_calls_existing_import_api(self) -> None:
        definition = build_definition()
        action = definition["actions"]["Import_credit_usage"]
        self.assertEqual(API_NAME, action["inputs"]["parameters"]["actionName"])
        self.assertFalse(action["inputs"]["parameters"]["item/DryRun"])
        self.assertNotIn("authentication", action["inputs"])
        self.assertEqual(
            "@variables('SourceCount')",
            definition["actions"]["Compose_import_payload"]["inputs"]["syncRun"]["sourceCount"],
        )

    def test_definition_chunks_user_usage_before_main_import(self) -> None:
        definition = build_definition()
        actions = definition["actions"]
        chunks = actions["Compose_user_chunks"]
        loop = actions["Import_user_chunks"]
        user_import = loop["actions"]["Import_user_chunk"]

        self.assertEqual(f"@chunk(outputs('Compose_user_rows'), {USER_CHUNK_SIZE})", chunks["inputs"])
        self.assertEqual("@outputs('Compose_user_chunks')", loop["foreach"])
        self.assertEqual(1, loop["runtimeConfiguration"]["concurrency"]["repetitions"])
        self.assertEqual(
            {"Import_user_chunks": ["Succeeded", "Failed", "TimedOut"]},
            actions["Get_capacity"]["runAfter"],
        )
        self.assertNotIn("ppacUsers", actions["Compose_import_payload"]["inputs"])
        self.assertEqual(API_NAME, user_import["inputs"]["parameters"]["actionName"])
        self.assertEqual(
            "@string(outputs('Compose_user_chunk_payload'))",
            user_import["inputs"]["parameters"]["item/PayloadJson"],
        )
        self.assertEqual(
            "@int(coalesce(body('Import_user_chunk')?['Created'], 0))",
            loop["actions"]["Increment_user_created_count"]["inputs"]["value"],
        )
        sync_run = actions["Compose_import_payload"]["inputs"]["syncRun"]
        self.assertEqual("@variables('UserCreatedCount')", sync_run["priorCreatedCount"])
        self.assertEqual("@variables('UserUpdatedCount')", sync_run["priorUpdatedCount"])
        self.assertEqual("@variables('UserRejectedCount')", sync_run["priorRejectedCount"])
        self.assertEqual("@variables('UserFailedChunkCount')", sync_run["priorFailedChunkCount"])
        self.assertEqual(
            {"Import_user_chunk": ["Failed", "TimedOut"]},
            loop["actions"]["Increment_user_failed_chunk_count"]["runAfter"],
        )

    def test_definition_uses_portable_tenant_environment_variable(self) -> None:
        definition = build_definition()
        parameter = definition["parameters"][TENANT_PARAMETER]
        serialized = json.dumps(definition)
        self.assertEqual("", parameter["defaultValue"])
        self.assertEqual({"schemaName": TENANT_VARIABLE_SCHEMA}, parameter["metadata"])
        self.assertNotIn(TENANT_ID, serialized)
        self.assertEqual(f"@parameters('{TENANT_PARAMETER}')", definition["actions"]["Compose_import_payload"]["inputs"]["tenantId"])

    def test_clientdata_uses_solution_connection_references(self) -> None:
        clientdata = json.loads(build_clientdata())
        references = clientdata["properties"]["connectionReferences"]
        self.assertEqual(HTTP_REF_LOGICAL, references["shared_webcontents"]["connection"]["connectionReferenceLogicalName"])
        self.assertEqual(DATAVERSE_REF_LOGICAL, references["shared_commondataserviceforapps"]["connection"]["connectionReferenceLogicalName"])

    def test_connection_id_prefers_deployment_input(self) -> None:
        self.assertEqual("provided", resolve_connection_id("provided", {"connectionid": "existing"}))

    def test_connection_id_reuses_target_environment_binding(self) -> None:
        self.assertEqual("existing", resolve_connection_id(None, {"connectionid": "existing"}))

    def test_connection_id_requires_a_deployment_binding(self) -> None:
        with self.assertRaises(SystemExit):
            resolve_connection_id(None, None)


if __name__ == "__main__":
    unittest.main()