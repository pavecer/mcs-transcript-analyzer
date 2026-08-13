import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_central_transcripts import composite_transcript_id, source_is_enabled  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()