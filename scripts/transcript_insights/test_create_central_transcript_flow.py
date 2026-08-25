import unittest
from unittest.mock import Mock

from scripts.transcript_insights.create_central_transcript_flow import (
    BATCH_SIZE,
    COLLECTOR_REFERENCE,
    FLOW_NAME,
    IMPORT_API,
    build_definition,
    build_solution_workflow,
    ensure_flow_in_core_solution,
)


class CentralTranscriptFlowTests(unittest.TestCase):
    def setUp(self):
        self.result = build_definition()
        self.definition = self.result["definition"]
        self.actions = self.definition["actions"]
        self.loop = self.actions["Process_transcript_sources"]
        self.loop_actions = self.loop["actions"]
        self.probe_actions = self.loop_actions["Probe_source_access"]["actions"]
        self.collection_actions = self.loop_actions["Collect_source_transcripts"]["actions"]
        self.failure_actions = self.loop_actions["Handle_source_access_failure"]["actions"]

    def test_is_one_generic_packaged_flow_with_one_dataverse_reference(self):
        self.assertEqual(FLOW_NAME, self.result["name"])
        self.assertEqual([COLLECTOR_REFERENCE], list(self.result["references"]))
        self.assertEqual(
            "shared_commondataserviceforapps",
            self.result["references"][COLLECTOR_REFERENCE]["api"]["name"],
        )
        self.assertNotIn("pvci_transcript_http_", str(self.result))
        self.assertNotIn("shared_webcontents", str(self.result))

    def test_reads_inventory_then_uses_selected_environment_action(self):
        inventory = self.actions["List_transcript_sources"]
        self.assertEqual("ListRecords", inventory["inputs"]["host"]["operationId"])
        self.assertEqual(
            "pvci_environmentinventories",
            inventory["inputs"]["parameters"]["entityName"],
        )
        remote = self.collection_actions["Read_source_transcripts"]
        self.assertEqual(
            "ListRecordsWithOrganization",
            remote["inputs"]["host"]["operationId"],
        )
        self.assertIn("pvci_environmenturl", remote["inputs"]["parameters"]["organization"])
        self.assertEqual("conversationtranscripts", remote["inputs"]["parameters"]["entityName"])
        self.assertEqual(BATCH_SIZE, remote["inputs"]["parameters"]["$top"])

    def test_scheduled_run_reads_only_explicitly_enabled_sources(self):
        inventory_filter = self.actions["List_transcript_sources"]["inputs"]["parameters"]["$filter"]
        self.assertIn("pvci_transcriptcollectorenabled eq true", inventory_filter)

    def test_probes_source_access_before_reading_content(self):
        probe = self.probe_actions["Probe_source_transcript_access"]
        self.assertEqual("conversationtranscriptid", probe["inputs"]["parameters"]["$select"])
        self.assertEqual(1, probe["inputs"]["parameters"]["$top"])
        self.assertEqual(
            {"Probe_source_access": ["Succeeded"]},
            self.loop_actions["Collect_source_transcripts"]["runAfter"],
        )

    def test_imports_after_successful_read_and_readable_update(self):
        import_action = self.collection_actions["Import_source_batch"]
        self.assertEqual(
            {"Mark_source_readable": ["Succeeded"]},
            import_action["runAfter"],
        )
        parameters = import_action["inputs"]["parameters"]
        self.assertEqual(IMPORT_API, parameters["actionName"])
        self.assertIn("pvci_environmentid", parameters["item/SourceEnvironmentId"])
        self.assertIn("pvci_environmenturl", parameters["item/SourceDataverseUrl"])

    def test_records_probe_success_and_failure_in_inventory(self):
        self.assertEqual(
            "UpdateOnlyRecord",
            self.collection_actions["Mark_source_readable"]["inputs"]["host"]["operationId"],
        )
        unavailable = self.failure_actions["Mark_source_unavailable"]
        self.assertEqual(
            ["Failed", "TimedOut"],
            self.loop_actions["Handle_source_access_failure"]["runAfter"]["Probe_source_access"],
        )
        self.assertEqual(
            "access_denied",
            unavailable["inputs"]["parameters"]["item/pvci_transcriptaccessstatus"],
        )
        self.assertFalse(
            unavailable["inputs"]["parameters"]["item/pvci_transcriptcollectorenabled"]
        )

    def test_handled_probe_failure_can_complete_without_hiding_collection_failures(self):
        completion = self.loop_actions["Complete_source_iteration"]["runAfter"]
        self.assertEqual(["Succeeded", "Skipped"], completion["Collect_source_transcripts"])
        self.assertEqual(["Succeeded", "Skipped"], completion["Handle_source_access_failure"])
        self.assertNotIn("Failed", completion["Collect_source_transcripts"])

    def test_solution_workflow_wraps_the_tested_definition(self):
        artifact = build_solution_workflow(self.result)
        self.assertIs(artifact["properties"]["definition"], self.definition)
        self.assertEqual(
            self.result["references"],
            artifact["properties"]["connectionReferences"],
        )
        self.assertIsNone(artifact["properties"]["templateName"])

    def test_adds_existing_flow_to_core_solution_when_membership_is_missing(self):
        dv = Mock()
        dv.base = "https://collector/api/data/v9.1"
        dv.h = {"Authorization": "Bearer token"}
        dv.find.side_effect = [
            {"solutionid": "11111111-1111-1111-1111-111111111111"},
            None,
        ]
        dv.s.post.return_value = Mock(ok=True)

        added = ensure_flow_in_core_solution(
            dv,
            "22222222-2222-2222-2222-222222222222",
        )

        self.assertTrue(added)
        payload = dv.s.post.call_args.kwargs["json"]
        self.assertEqual("pvConversationInsights", payload["SolutionUniqueName"])
        self.assertEqual(29, payload["ComponentType"])
        self.assertEqual(
            "22222222-2222-2222-2222-222222222222",
            payload["ComponentId"],
        )


if __name__ == "__main__":
    unittest.main()
