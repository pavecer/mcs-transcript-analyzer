import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_transcripts import attach_workflow_names, correlate_flow_runs, parse_transcript, plan_step_spans, session_payload_for_write  # noqa: E402


class TranscriptOutcomeTests(unittest.TestCase):
    def test_reprocess_clears_stale_derived_values(self) -> None:
        payload = {"pvci_topicname": None, "pvci_userid": None, "pvci_usererrorcount": 0}

        self.assertIn("pvci_topicname", session_payload_for_write(payload, updating=True))
        self.assertIn("pvci_userid", session_payload_for_write(payload, updating=True))
        self.assertNotIn("pvci_topicname", session_payload_for_write(payload, updating=False))
        self.assertNotIn("pvci_userid", session_payload_for_write(payload, updating=False))

    def test_attaches_real_workflow_names_to_flow_runs(self) -> None:
        runs = [{"workflowid": "FLOW-ID"}]

        attach_workflow_names(runs, [{"workflowid": "flow-id", "name": "ServiceNow Orchestrator"}])

        self.assertEqual("ServiceNow Orchestrator", runs[0]["workflowname"])

    def test_user_error_trace_reports_topic_failure_detail(self) -> None:
        row = {
            "conversationtranscriptid": "transcript-1",
            "content": """{
                "activities": [
                    {
                        "type": "event",
                        "name": "DynamicPlanStepTriggered",
                        "value": {
                            "stepId": "step-1",
                            "taskDialogId": "msdyn.ess.ResetPassword"
                        }
                    },
                    {
                        "type": "trace",
                        "valueType": "ErrorTraceData",
                        "value": {
                            "isUserError": true,
                            "errorCode": "ContentValidationError",
                            "errorMessage": "The expression on the 'ExpressionSegment' node failed."
                        }
                    },
                    {
                        "type": "event",
                        "valueType": "SessionInfo",
                        "value": {
                            "outcome": "Abandoned",
                            "outcomeReason": "UserError"
                        }
                    }
                ]
            }""",
        }

        parsed = parse_transcript(row)

        self.assertEqual("Abandoned", parsed["session_outcome"])
        self.assertEqual(
            "ContentValidationError: The expression on the 'ExpressionSegment' node failed.",
            parsed["outcome_reason"],
        )
        self.assertEqual(1, parsed["user_error_count"])
        self.assertEqual("ContentValidationError", parsed["primary_error_code"])
        self.assertEqual("Topic expression", parsed["error_category"])
        self.assertEqual("ResetPassword", parsed["primary_error_topic"])
        self.assertEqual("ResetPassword", parsed["topic_name"])
        self.assertEqual("msdyn.ess.ResetPassword", parsed["topic_id"])

    def test_knowledge_trace_reports_search_and_cited_sources(self) -> None:
        row = {
            "conversationtranscriptid": "transcript-knowledge",
            "content": """{
                "activities": [
                    {
                        "type": "event",
                        "name": "DynamicPlanStepTriggered",
                        "timestamp": 100,
                        "timestampMs": 100000,
                        "value": {
                            "stepId": "step-search",
                            "taskDialogId": "P:UniversalSearchTool"
                        }
                    },
                    {
                        "type": "trace",
                        "timestamp": 102,
                        "timestampMs": 102500,
                        "valueType": "KnowledgeTraceData",
                        "value": {
                            "completionState": "Answered",
                            "isKnowledgeSearched": true,
                            "citedKnowledgeSources": ["agent.topic.ServiceNowKB_source"],
                            "failedKnowledgeSourcesTypes": []
                        }
                    }
                ]
            }""",
        }

        parsed = parse_transcript(row)

        self.assertEqual(1, parsed["knowledge_call_count"])
        self.assertEqual(1, parsed["knowledge_source_count"])
        self.assertEqual(0, parsed["knowledge_failure_count"])
        self.assertEqual("P:UniversalSearchTool", parsed["knowledge_calls"][0]["task"])
        self.assertEqual("1970-01-01T00:01:40Z", parsed["knowledge_calls"][0]["started_utc"])
        self.assertEqual("Answered", parsed["knowledge_calls"][0]["completion_state"])
        self.assertEqual(2500, parsed["knowledge_calls"][0]["duration_ms"])
        self.assertEqual(["agent.topic.ServiceNowKB_source"], parsed["knowledge_calls"][0]["cited_sources"])

    def test_universal_search_is_not_a_flow_candidate(self) -> None:
        activities = [
            {
                "name": "DynamicPlanStepTriggered",
                "timestampMs": 100000,
                "value": {
                    "stepId": "step-search",
                    "taskDialogId": "P:UniversalSearchTool",
                },
            }
        ]

        self.assertEqual([], plan_step_spans(activities))

    def test_mcp_llm_skill_is_not_a_flow_candidate(self) -> None:
        activities = [
            {
                "name": "DynamicPlanStepTriggered",
                "timestampMs": 100000,
                "value": {
                    "stepId": "step-jira",
                    "taskDialogId": "MCP:pve_JiraMcpTokenLabAgent.action.Jira-JiraMCPServer:ListIssues",
                    "type": "LlmSkill",
                },
            }
        ]

        self.assertEqual([], plan_step_spans(activities))

    def test_unmatched_custom_topic_is_not_reported_as_a_flow_run(self) -> None:
        activities = [
            {
                "name": "DynamicPlanStepTriggered",
                "timestampMs": 100000,
                "value": {
                    "stepId": "step-topic",
                    "taskDialogId": "agent.topic.CreateTicket",
                    "type": "CustomTopic",
                },
            }
        ]

        spans = plan_step_spans(activities)
        self.assertEqual(1, len(spans))
        self.assertEqual([], correlate_flow_runs(spans, []))

    def test_matched_custom_topic_remains_a_flow_candidate(self) -> None:
        activities = [
            {
                "name": "DynamicPlanStepTriggered",
                "timestampMs": 100000,
                "value": {
                    "stepId": "step-topic",
                    "taskDialogId": "agent.topic.CreateTicket",
                    "type": "CustomTopic",
                },
            }
        ]
        run = {
            "flowrunid": "run-1",
            "name": "run",
            "_start_epoch": 105,
        }

        correlated = correlate_flow_runs(plan_step_spans(activities), [run])
        self.assertEqual(1, len(correlated))
        self.assertEqual("high", correlated[0]["confidence"])

    def test_incomplete_tool_trace_is_unknown_not_failed(self) -> None:
        activities = [
            {
                "name": "DialogTracing",
                "timestampMs": 100000,
                "value": {
                    "actions": [{
                        "actionId": "invoke-1",
                        "actionType": "InvokeConnectorAction",
                        "topicId": "agent.topic.GetTickets",
                    }]
                },
            }
        ]

        parsed = parse_transcript({
            "conversationtranscriptid": "incomplete-tool",
            "content": json.dumps({"activities": activities}),
        })
        self.assertEqual(1, parsed["tool_call_count"])
        self.assertEqual(0, parsed["tool_error_count"])
        self.assertFalse(parsed["tool_calls"][0]["completion_observed"])
        self.assertFalse(parsed["tool_calls"][0]["failed"])


if __name__ == "__main__":
    unittest.main()