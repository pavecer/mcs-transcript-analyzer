import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[2] / "plugin" / "ImportCreditUsageBatch.cs"


class InventoryHarnessContractTests(unittest.TestCase):
    def test_direct_cli_property_preserves_three_state_classification(self) -> None:
        source = PLUGIN.read_text(encoding="utf-8")

        self.assertIn('Json.Get(properties, "isCLIAgent")', source)
        self.assertIn('? "github_copilot" : "not_github_copilot"', source)
        self.assertIn('Put(agent, "harness", "unknown")', source)
        self.assertIn('"power_platform_inventory.isCLIAgent"', source)
        self.assertIn('"inventory_missing_harness_property"', source)


if __name__ == "__main__":
    unittest.main()