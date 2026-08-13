import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOLUTION = json.loads(
    (ROOT / "solution" / "pvConversationInsights" / "solution-definition.json").read_text(encoding="utf-8")
)
PLUGIN = (ROOT / "plugin" / "ImportCentralTranscriptBatch.cs").read_text(encoding="utf-8")


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


if __name__ == "__main__":
    unittest.main()