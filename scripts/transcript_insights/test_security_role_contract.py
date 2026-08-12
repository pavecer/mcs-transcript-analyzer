import json
import unittest
from pathlib import Path


DEFINITION = Path(__file__).resolve().parents[2] / "solution" / "pvConversationInsights" / "solution-definition.json"


class SecurityRoleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.roles = {role["name"]: role for role in definition["securityRoles"]}

    def test_reader_and_approver_roles_are_declared(self) -> None:
        self.assertEqual({"PVCI Analyst", "PVCI Privacy Approver", "PVCI Credit Administrator"}, set(self.roles))
        self.assertTrue(all(role["baseRole"] == "App Opener" for role in self.roles.values()))

    def test_analyst_cannot_change_disclosure_or_user_facts(self) -> None:
        privileges = self.roles["PVCI Analyst"]["tablePrivileges"]
        self.assertEqual(["Read"], privileges["pvci_creditprivacysetting"])
        self.assertEqual(["Read"], privileges["pvci_credituserusage"])
        self.assertNotIn("systemuser", privileges)

    def test_approver_can_complete_audited_disclosure_sweep(self) -> None:
        privileges = self.roles["PVCI Privacy Approver"]["tablePrivileges"]
        self.assertEqual(["Read", "Write"], privileges["pvci_creditprivacysetting"])
        self.assertEqual(["Read", "Write"], privileges["pvci_credituserusage"])
        self.assertEqual(["Read"], privileges["systemuser"])

    def test_all_reporting_tables_are_readable_by_both_roles(self) -> None:
        expected = {
            "pvci_transcriptsession",
            "pvci_transcriptturn",
            "pvci_transcriptidentitymap",
            "pvci_flowrundetail",
            "pvci_syncstate",
            "pvci_environmentinventory",
            "pvci_inventorysyncrun",
            "pvci_agentthresholdsnapshot",
            "pvci_governancesyncrun",
            "pvci_thresholdchangerequest",
            "pvci_agentinventory",
            "pvci_creditusage",
            "pvci_creditcapacitysnapshot",
            "pvci_creditsyncrun",
            "pvci_credituserusage",
            "pvci_creditprivacysetting",
        }
        for role in self.roles.values():
            readable = {
                table for table, privileges in role["tablePrivileges"].items() if "Read" in privileges
            }
            self.assertTrue(expected.issubset(readable))

    def test_credit_administrator_can_submit_but_not_process_requests(self) -> None:
        privileges = self.roles["PVCI Credit Administrator"]["tablePrivileges"]
        self.assertEqual(["Create", "Read", "Append"], privileges["pvci_thresholdchangerequest"])
        self.assertEqual(["Read", "AppendTo"], privileges["pvci_agentinventory"])
        self.assertNotIn("Write", privileges["pvci_thresholdchangerequest"])


if __name__ == "__main__":
    unittest.main()