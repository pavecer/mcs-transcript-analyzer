import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFINITION = ROOT / "solution" / "pvConversationInsights" / "solution-definition.json"
PLUGIN = ROOT / "plugin" / "ImportCreditUsageBatch.cs"


class CreditGovernanceContractTests(unittest.TestCase):
    def test_threshold_and_sync_tables_are_declared(self) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        tables = {table["schemaName"]: table for table in definition["tables"]}

        threshold = tables["pvci_AgentThresholdSnapshot"]
        self.assertIn("pvci_Limit", threshold["columns"])
        self.assertIn("pvci_ResourceConsumption", threshold["columns"])
        self.assertIn("pvci_StopIfOverCapacity", threshold["columns"])
        self.assertEqual("pvci_agentinventory", threshold["lookups"][0]["referencedTable"])
        self.assertIn("pvci_GovernanceSyncRun", tables)

    def test_importer_keeps_thresholds_read_only_and_daily(self) -> None:
        source = PLUGIN.read_text(encoding="utf-8")

        self.assertIn('Json.Arr(Json.Get(root, "resourceThresholds"))', source)
        self.assertIn('DatePart(capturedOn)', source)
        self.assertIn('"/licensing/entitlements/MCSMessages/resourceThresholds"', source)
        self.assertNotIn("UpsertResourceThreshold", source)


if __name__ == "__main__":
    unittest.main()