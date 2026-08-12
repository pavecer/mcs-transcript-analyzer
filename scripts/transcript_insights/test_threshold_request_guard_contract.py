import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "plugin" / "ThresholdChangeRequestGuard.cs"
REGISTRATION = ROOT / "scripts" / "transcript_insights" / "register_credit_plugin.py"


class ThresholdRequestGuardContractTests(unittest.TestCase):
    def test_guard_forces_processor_owned_state_on_create(self) -> None:
        source = GUARD.read_text(encoding="utf-8")
        self.assertIn('context.MessageName, "Create"', source)
        self.assertIn("context.Stage != 20", source)
        self.assertIn('target["pvci_status"] = "Pending"', source)
        self.assertIn('target["pvci_requestedon"] = DateTime.UtcNow', source)
        for field in ("pvci_processedon", "pvci_beforejson", "pvci_afterjson", "pvci_error"):
            self.assertIn(f'target.Attributes.Remove("{field}")', source)

    def test_guard_enforces_server_side_request_policy(self) -> None:
        source = GUARD.read_text(encoding="utf-8")
        self.assertIn("decimal.Truncate(requestedLimit) != requestedLimit", source)
        self.assertIn("justification.Trim().Length < 10", source)
        self.assertIn('entitlement, "MCSMessages"', source)
        self.assertIn("notificationThreshold > 100", source)

    def test_guard_is_registered_synchronously_before_create(self) -> None:
        source = REGISTRATION.read_text(encoding="utf-8")
        self.assertIn('REQUEST_GUARD_PLUGIN_TYPE = "PvciTranscripts.ThresholdChangeRequestGuard"', source)
        self.assertIn('create_message = dv.find("sdkmessages", "name eq \'Create\'"', source)
        self.assertIn('"stage": 20', source)
        self.assertIn('"mode": 0', source)
        self.assertIn("pvci_thresholdchangerequest", source)


if __name__ == "__main__":
    unittest.main()