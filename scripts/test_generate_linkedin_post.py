import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_linkedin_post import LINKEDIN_CHARACTER_LIMIT, generate_post


class GenerateLinkedInPostTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.changelog = self.root / "CHANGELOG.md"
        self.manifest = self.root / "release-manifest.json"
        self.changelog.write_text(
            "# Changelog\n\n"
            "## 1.4.0.15 - 2026-08-25\n\n"
            "Cross-environment transcript operations release.\n\n"
            "- Added central transcript collection.\n"
            "- Kept administrator bootstrap unavailable.\n\n"
            "Artifacts:\n\n"
            "- Core: `core.zip`\n\n"
            "## 1.3.1.0 - 2026-08-12\n",
            encoding="utf-8",
        )
        self.manifest.write_text(
            json.dumps(
                {
                    "artifacts": {
                        "core": {"version": "1.4.0.15"},
                        "codeApp": {"version": "1.4.0.15"},
                    }
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generates_release_details_and_public_links(self):
        post = generate_post(
            "1.4.0.15",
            "pavecer/mcs-transcript-analyzer",
            "https://pavecer.github.io/mcs-transcript-analyzer",
            self.changelog,
            self.manifest,
        )

        self.assertIn("MCS Transcript Analyzer 1.4.0.15 is now available.", post)
        self.assertIn("- Added central transcript collection.", post)
        self.assertIn("- Kept administrator bootstrap unavailable.", post)
        self.assertNotIn("core.zip", post)
        self.assertIn("https://pavecer.github.io/mcs-transcript-analyzer/", post)
        self.assertIn(
            "https://github.com/pavecer/mcs-transcript-analyzer/releases/tag/v1.4.0.15",
            post,
        )
        self.assertLessEqual(len(post), LINKEDIN_CHARACTER_LIMIT)

    def test_rejects_version_not_in_release_manifest(self):
        with self.assertRaisesRegex(ValueError, "does not match release manifest"):
            generate_post(
                "1.4.0.14",
                "pavecer/mcs-transcript-analyzer",
                "https://pavecer.github.io/mcs-transcript-analyzer",
                self.changelog,
                self.manifest,
            )


if __name__ == "__main__":
    unittest.main()