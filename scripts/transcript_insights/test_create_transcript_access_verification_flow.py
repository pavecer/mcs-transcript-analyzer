import unittest

from scripts.transcript_insights.create_transcript_access_verification_flow import (
    COLLECTOR_REFERENCE,
    FLOW_NAME,
    MAX_REQUESTS,
    build_definition,
)


class TranscriptAccessVerificationFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = build_definition()
        self.actions = self.result["definition"]["actions"]
        self.loop = self.actions["Process_verification_requests"]
        self.loop_actions = self.loop["actions"]

    def test_uses_only_packaged_dataverse_reference(self) -> None:
        self.assertEqual(FLOW_NAME, self.result["name"])
        self.assertEqual([COLLECTOR_REFERENCE], list(self.result["references"]))
        self.assertNotIn("shared_webcontents", str(self.result))

    def test_consumes_only_pending_verify_requests(self) -> None:
        listing = self.actions["List_pending_verification_requests"]
        parameters = listing["inputs"]["parameters"]
        self.assertEqual("pvci_transcriptaccessrequests", parameters["entityName"])
        self.assertEqual("pvci_status eq 'Pending' and pvci_action eq 'Verify'", parameters["$filter"])
        self.assertEqual(MAX_REQUESTS, parameters["$top"])

    def test_probe_is_id_only_and_uses_dynamic_source(self) -> None:
        probe = self.loop_actions["Probe_source_access"]["actions"]["Probe_source_transcript_access"]
        parameters = probe["inputs"]["parameters"]
        self.assertEqual("ListRecordsWithOrganization", probe["inputs"]["host"]["operationId"])
        self.assertEqual("conversationtranscriptid", parameters["$select"])
        self.assertEqual(1, parameters["$top"])
        self.assertIn("pvci_environmenturl", parameters["organization"])

    def test_success_projects_access_without_claiming_role_verification(self) -> None:
        verified = self.loop_actions["Project_verified_access"]["inputs"]["parameters"]
        self.assertEqual("Verified", verified["item/pvci_transcriptonboardingstatus"])
        self.assertFalse(verified["item/pvci_transcriptaccessroleverified"])
        self.assertFalse(verified["item/pvci_transcriptelevationcleanupverified"])

    def test_failure_disables_collection_and_is_handled(self) -> None:
        handler = self.loop_actions["Handle_verification_failure"]
        self.assertEqual(["Failed", "TimedOut"], handler["runAfter"]["Probe_source_access"])
        denied = handler["actions"]["Project_denied_access"]["inputs"]["parameters"]
        self.assertEqual("access_denied", denied["item/pvci_transcriptaccessstatus"])
        self.assertFalse(denied["item/pvci_transcriptcollectorenabled"])
        completion = self.loop_actions["Complete_verification_request"]["runAfter"]
        self.assertNotIn("Failed", completion["Project_verified_access"])


if __name__ == "__main__":
    unittest.main()