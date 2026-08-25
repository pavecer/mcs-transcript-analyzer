import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_transcripts import parse_transcript, plan_step_spans  # noqa: E402


class TranscriptOutcomeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()