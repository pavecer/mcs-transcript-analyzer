import json
import tempfile
import unittest
from pathlib import Path

from scripts.clean_output import keep_relative_paths, stale_files


def write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class CleanOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.addCleanup(self._temp.cleanup)

        write(self.root / "config/release-packages.json", json.dumps({
            "core": {"filename": "core-2.1.0.0.zip"},
            "codeApp": {"filename": "app-2.3.0.0.zip"},
        }))
        write(self.root / "site/downloads/release-manifest.json", json.dumps({
            "artifacts": {"codeApp": {"filename": "app-2.2.0.3.zip"}},
        }))

    def test_keeps_in_flight_and_published_packages(self) -> None:
        keep = keep_relative_paths(self.root)
        self.assertIn("candidate/app-2.3.0.0.zip", keep)
        self.assertIn("candidate/app-2.2.0.3.zip", keep)
        self.assertIn("candidate/core-2.1.0.0.zip", keep)

    def test_keeps_referenced_captures_without_editing_the_script(self) -> None:
        write(self.root / "docs/operations.md", "Inspect `output/transcript-source-registry.json` after a run.")
        self.assertIn("transcript-source-registry.json", keep_relative_paths(self.root))

    def test_reports_superseded_and_extracted_scratch_as_stale(self) -> None:
        write(self.root / "output/candidate/app-2.3.0.0.zip")
        write(self.root / "output/candidate/candidate-manifest-codeApp-2.3.0.0.json")
        write(self.root / "output/candidate/app-2.2.0.3.zip")
        write(self.root / "output/candidate/app-1.4.0.7.zip")
        write(self.root / "output/candidate/Other/Solution.xml")
        write(self.root / "output/pve-normalize/core/customizations.xml")
        write(self.root / "output/probe-capture.json")

        stale = {path.relative_to(self.root / "output").as_posix() for path in stale_files(self.root)}
        self.assertEqual(stale, {
            "candidate/app-1.4.0.7.zip",
            "candidate/Other/Solution.xml",
            "pve-normalize/core/customizations.xml",
            "probe-capture.json",
        })

    def test_keeps_candidate_manifests(self) -> None:
        write(self.root / "output/candidate/candidate-manifest-core-2.1.0.0.json")
        self.assertEqual(stale_files(self.root), [])

    def test_missing_output_directory_is_not_an_error(self) -> None:
        self.assertEqual(stale_files(self.root), [])


if __name__ == "__main__":
    unittest.main()
