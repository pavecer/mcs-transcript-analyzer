import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOLUTION = json.loads(
    (ROOT / "solution" / "pvConversationInsights" / "solution-definition.json").read_text(encoding="utf-8")
)
PLUGIN = (ROOT / "plugin" / "ImportCentralTranscriptBatch.cs").read_text(encoding="utf-8")
SYNC_PLUGIN = (ROOT / "plugin" / "SyncConversationTranscripts.cs").read_text(encoding="utf-8")
TRANSCRIPT_ANALYSIS = (ROOT / "plugin" / "TranscriptAnalysis.cs").read_text(encoding="utf-8")


class CentralTranscriptContractTests(unittest.TestCase):
    def test_environment_inventory_carries_collector_state(self):
        table = next(
            table for table in SOLUTION["tables"]
            if table["schemaName"] == "pvci_EnvironmentInventory"
        )

        for column in (
            "pvci_TranscriptAccessStatus",
            "pvci_TranscriptAccessReason",
            "pvci_TranscriptProbeOn",
            "pvci_TranscriptSampleCount",
            "pvci_TranscriptCollectorEnabled",
            "pvci_TranscriptLastCollectedOn",
            "pvci_TranscriptLastCollectionStatus",
            "pvci_TranscriptLastCollectionError",
        ):
            self.assertIn(column, table["columns"])

    def test_plugin_declares_bounded_source_scoped_import(self):
        self.assertIn("class ImportCentralTranscriptBatch", PLUGIN)
        self.assertIn('GetInput<string>(context, "SourceEnvironmentId"', PLUGIN)
        self.assertIn('GetInput<string>(context, "SourceTenantId"', PLUGIN)
        self.assertIn('GetInput<string>(context, "PayloadJson"', PLUGIN)
        self.assertIn("MaxBatchSize", PLUGIN)
        self.assertIn("CompositeTranscriptId", PLUGIN)

    def test_core_solution_owns_structured_runtime_diagnostics(self):
        table = next(
            table for table in SOLUTION["tables"]
            if table["schemaName"] == "pvci_TranscriptSession"
        )

        for column in (
            "pvci_TopicName",
            "pvci_TopicId",
            "pvci_UserErrorCount",
            "pvci_PrimaryErrorCode",
            "pvci_PrimaryErrorMessage",
            "pvci_PrimaryErrorTopic",
            "pvci_ErrorCategory",
            "pvci_KnowledgeCallCount",
            "pvci_KnowledgeSourceCount",
            "pvci_KnowledgeFailureCount",
            "pvci_KnowledgeCallsJson",
        ):
            self.assertIn(column, table["columns"])

    def test_default_sync_retains_user_error_traces(self):
        self.assertIn("TranscriptAnalysis.IsUserErrorTrace(a)", SYNC_PLUGIN)
        self.assertIn('"ErrorTraceData"', TRANSCRIPT_ANALYSIS)
        self.assertIn('turn["pvci_eventname"] = Trim(name ?? Json.Str(a, "valueType")', SYNC_PLUGIN)

    def test_local_sync_prefers_inventory_environment_display_name(self):
        self.assertIn("ResolveInventoryEnvironmentName(service, context6.EnvironmentId)", SYNC_PLUGIN)
        self.assertIn('ColumnSet = new ColumnSet("pvci_displayname")', SYNC_PLUGIN)
        self.assertIn("Name = inventoryName ?? friendlyName", SYNC_PLUGIN)


if __name__ == "__main__":
    unittest.main()