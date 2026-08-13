import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_transcript_sources import classify_response, load_inventory


class ProbeTranscriptSourcesTests(unittest.TestCase):
    def test_classifies_readable_empty_without_exposing_data(self):
        response = Mock(status_code=200)
        response.json.return_value = {"value": []}

        self.assertEqual(("readable_empty", None, 0), classify_response(response))

    def test_classifies_readable_rows(self):
        response = Mock(status_code=200)
        response.json.return_value = {"value": [{"conversationtranscriptid": "secret"}]}

        self.assertEqual(("readable_with_rows", None, 1), classify_response(response))

    def test_classifies_dataverse_privilege_failure(self):
        response = Mock(status_code=403)

        self.assertEqual(
            ("access_denied", "dataverse_read_not_available", None),
            classify_response(response),
        )

    def test_loads_connector_value_shape(self):
        path = Mock()
        path.read_text.return_value = json.dumps({"value": [{"id": "env"}]})

        self.assertEqual([{"id": "env"}], load_inventory(path))


if __name__ == "__main__":
    unittest.main()