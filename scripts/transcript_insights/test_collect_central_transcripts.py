import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_central_transcripts import (  # noqa: E402
    build_turn_payload,
    central_flow_unavailable_payload,
    composite_transcript_id,
    session_payload_for_write,
    source_is_enabled,
)


class CentralTranscriptCollectorTests(unittest.TestCase):
    def test_composite_key_is_stable_and_source_scoped(self):
        self.assertEqual(
            "tenant:environment:transcript",
            composite_transcript_id("Tenant", "Environment", "Transcript"),
        )

    def test_only_readable_sources_are_enabled(self):
        self.assertTrue(source_is_enabled({"enabled": True, "status": "readable_with_rows"}))
        self.assertTrue(source_is_enabled({"enabled": True, "status": "readable_empty"}))
        self.assertFalse(source_is_enabled({"enabled": True, "status": "access_denied"}))
        self.assertFalse(source_is_enabled({"enabled": False, "status": "readable_with_rows"}))

    def test_central_flow_telemetry_is_unavailable_not_zero(self):
        self.assertEqual(
            {
                "pvci_flowrunsjson": None,
                "pvci_flowruncount": None,
                "pvci_flowrunfailurecount": None,
                "pvci_flowrunmaxms": None,
            },
            central_flow_unavailable_payload(),
        )

    def test_reprocess_clears_all_stale_nullable_projections(self):
        payload = {
            "pvci_topicname": None,
            "pvci_userid": None,
            "pvci_firstresponsems": None,
            "pvci_primaryerrorcode": None,
            "pvci_flowrunmaxms": None,
            "pvci_usererrorcount": 0,
        }

        updating = session_payload_for_write(payload, updating=True)
        creating = session_payload_for_write(payload, updating=False)

        self.assertEqual(payload, updating)
        self.assertEqual({"pvci_usererrorcount": 0}, creating)

    def test_turn_payload_preserves_replay_text(self):
        payload = build_turn_payload(
            {"type": "message", "text": "Hello", "timestamp": 100, "from": {"role": 1}},
            1,
            "session-id",
            "composite-id",
        )

        self.assertEqual("Hello", payload["pvci_turntext"])


if __name__ == "__main__":
    unittest.main()