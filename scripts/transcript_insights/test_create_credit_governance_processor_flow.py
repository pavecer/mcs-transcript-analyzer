import json
import unittest

from scripts.transcript_insights.create_credit_governance_processor_flow import (
    MAX_REQUESTS,
    REQUEST_TABLE,
    THRESHOLD_URL,
    build_clientdata,
    build_definition,
)


class CreditGovernanceProcessorFlowTests(unittest.TestCase):
    def test_processor_is_bounded_and_serial(self) -> None:
        definition = build_definition()
        trigger = definition["triggers"]["Every_minute"]
        listing = definition["actions"]["List_pending_requests"]
        loop = definition["actions"]["Process_pending_requests"]

        self.assertEqual(1, trigger["runtimeConfiguration"]["concurrency"]["runs"])
        self.assertEqual(MAX_REQUESTS, listing["inputs"]["parameters"]["$top"])
        self.assertEqual("pvci_status eq 'Pending'", listing["inputs"]["parameters"]["$filter"])
        self.assertEqual(REQUEST_TABLE, listing["inputs"]["parameters"]["entityName"])
        self.assertEqual(1, loop["runtimeConfiguration"]["concurrency"]["repetitions"])

    def test_processor_reads_and_compares_before_put(self) -> None:
        actions = build_definition()["actions"]["Process_pending_requests"]["actions"]
        scope = actions["Apply_request"]
        scoped = scope["actions"]
        condition = scoped["Current_state_matches_request"]
        applied = condition["actions"]["Apply_threshold"]
        serialized_condition = json.dumps(condition["expression"])

        self.assertEqual("GET", scoped["Get_current_thresholds"]["inputs"]["parameters"]["request/method"])
        self.assertEqual(THRESHOLD_URL, scoped["Get_current_thresholds"]["inputs"]["parameters"]["request/url"])
        self.assertEqual("PUT", applied["inputs"]["parameters"]["request/method"])
        self.assertIn("pvci_expectedlimit", serialized_condition)
        self.assertIn("pvci_expectednotificationthreshold", serialized_condition)
        self.assertIn("pvci_expectedstopresource", serialized_condition)
        self.assertIn("pvci_justification", serialized_condition)
        self.assertIn("resourceConsumption", applied["inputs"]["parameters"]["request/body"])

    def test_processor_records_success_stale_and_failure(self) -> None:
        loop = build_definition()["actions"]["Process_pending_requests"]
        actions = loop["actions"]
        scope = actions["Apply_request"]
        condition = scope["actions"]["Current_state_matches_request"]
        success = condition["actions"]["Mark_succeeded"]
        stale = condition["else"]["actions"]["Mark_stale"]
        failed = actions["Mark_processor_failed"]

        self.assertEqual("Succeeded", success["inputs"]["parameters"]["item/pvci_status"])
        self.assertIn("item/pvci_beforejson", success["inputs"]["parameters"])
        self.assertIn("item/pvci_afterjson", success["inputs"]["parameters"])
        self.assertEqual("Stale", stale["inputs"]["parameters"]["item/pvci_status"])
        self.assertEqual("Failed", failed["inputs"]["parameters"]["item/pvci_status"])
        self.assertEqual({"Apply_request": ["Failed", "TimedOut"]}, failed["runAfter"])

    def test_processor_does_not_change_environment_allocations(self) -> None:
        serialized = json.dumps(build_definition())
        self.assertNotIn("allocationsByEnvironment", serialized)
        self.assertNotIn("TenantPool", serialized)
        self.assertNotIn("PayGo", serialized)

    def test_clientdata_reuses_solution_references(self) -> None:
        references = json.loads(build_clientdata())["properties"]["connectionReferences"]
        self.assertEqual("pvci_powerplatformapi", references["shared_webcontents"]["connection"]["connectionReferenceLogicalName"])
        self.assertEqual("pvci_dataversesync", references["shared_commondataserviceforapps"]["connection"]["connectionReferenceLogicalName"])


if __name__ == "__main__":
    unittest.main()
