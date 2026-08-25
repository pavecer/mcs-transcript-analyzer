import json
import unittest
from pathlib import Path


DEFINITION = Path(__file__).resolve().parents[2] / "solution" / "pvConversationInsights" / "solution-definition.json"


class TranscriptAccessRequestContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.tables = {table["schemaName"]: table for table in definition["tables"]}

    def test_environment_projects_onboarding_state(self) -> None:
        columns = self.tables["pvci_EnvironmentInventory"]["columns"]
        expected = {
            "pvci_TranscriptOnboardingMode",
            "pvci_TranscriptOnboardingStatus",
            "pvci_TranscriptCollectorApplicationId",
            "pvci_TranscriptAccessLastVerifiedOn",
            "pvci_TranscriptAccessRoleVerified",
            "pvci_TranscriptElevationCleanupVerified",
            "pvci_TranscriptOnboardingLastError",
        }
        self.assertTrue(expected.issubset(columns))

    def test_request_is_user_owned_and_auditable(self) -> None:
        request = self.tables["pvci_TranscriptAccessRequest"]
        self.assertEqual("UserOwned", request["ownershipType"])
        self.assertEqual(
            ["pvci_requestkey"],
            request["alternateKeys"][0]["columns"],
        )
        self.assertEqual(
            "pvci_environmentinventory",
            request["lookups"][0]["referencedTable"],
        )

    def test_request_stores_no_credentials_or_transcripts(self) -> None:
        columns = {name.lower() for name in self.tables["pvci_TranscriptAccessRequest"]["columns"]}
        forbidden_fragments = {"secret", "password", "token", "transcriptjson", "rawjson"}
        self.assertFalse(any(fragment in column for column in columns for fragment in forbidden_fragments))


if __name__ == "__main__":
    unittest.main()