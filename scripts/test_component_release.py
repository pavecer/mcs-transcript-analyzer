import unittest
import sys
import re
import textwrap
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_candidate_packages import (
    ARTIFACT_PACKAGE_INPUTS,
    artifact_keys,
    candidate_manifest_name,
    commits_match_artifact_inputs,
)
from update_release_manifest import existing_artifact_source_commit, release_artifacts_for_update
from validate_release_promotion import PROMOTABLE_ARTIFACTS, candidate_scope_errors, published_source_commit
from validate_release_evidence import (
    REQUIRED_GATES,
    published_source_commit as evidence_source_commit,
    required_gates,
    valid_candidate_run_id,
)
from validate_site import (
    PUBLIC_COPY_FORBIDDEN_PHRASES,
    expected_published_artifacts,
    public_copy_violations,
)


ROOT = Path(__file__).resolve().parents[1]
REFRESH_WORKFLOW = (ROOT / ".github" / "workflows" / "refresh-packages.yml").read_text(encoding="utf-8")
BUILD_WORKFLOW = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
PROMOTION_WORKFLOW = (ROOT / ".github" / "workflows" / "release-promotion.yml").read_text(encoding="utf-8")
LINKEDIN_WORKFLOW = (ROOT / ".github" / "workflows" / "linkedin-release.yml").read_text(encoding="utf-8")
CURRENT_CODE_APP_SUPPORT_SURFACES = (
    ROOT / "README.md",
    ROOT / "codeapp" / "README.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "clean-install.md",
    ROOT / "docs" / "credit-reporting.md",
    ROOT / "docs" / "operations.md",
    ROOT / "docs" / "permissions-and-inventory.md",
    ROOT / "docs" / "release-automation.md",
    ROOT / "scripts" / "transcript_insights" / "README.md",
    ROOT / "site" / "README.md",
    ROOT / "site" / "index.html",
    ROOT / ".github" / "instructions" / "solution-boundaries.instructions.md",
    ROOT / ".github" / "agents" / "release-maintainer.agent.md",
    ROOT / ".github" / "skills" / "central-transcript-collector" / "SKILL.md",
)
OBSOLETE_CODE_APP_SUPPORT_LABELS = (
    "unsupported preview code app",
    "code apps are preview",
    "Preview · unsupported",
)


class ComponentReleaseTests(unittest.TestCase):
    def test_current_code_app_surfaces_reject_obsolete_preview_support_labels(self) -> None:
        for path in CURRENT_CODE_APP_SUPPORT_SURFACES:
            content = path.read_text(encoding="utf-8").casefold()
            for label in OBSOLETE_CODE_APP_SUPPORT_LABELS:
                with self.subTest(path=path.relative_to(ROOT), label=label):
                    self.assertNotIn(label.casefold(), content)

    def test_public_site_rejects_internal_release_details(self) -> None:
        for phrase in PUBLIC_COPY_FORBIDDEN_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertEqual([phrase], public_copy_violations(f"<p>{phrase}</p>"))

    def test_public_site_allows_maker_facing_environment_terms(self) -> None:
        html = "<p>Test in a sandbox, choose your tenant, and complete validation.</p>"

        self.assertEqual([], public_copy_violations(html))

    def test_public_site_contains_no_internal_release_details(self) -> None:
        html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")

        self.assertEqual([], public_copy_violations(html))

    def test_refresh_embedded_python_blocks_compile(self) -> None:
        blocks = re.findall(r"python3 - <<'PY'\n(.*?)\n\s*PY", REFRESH_WORKFLOW, re.DOTALL)

        self.assertGreaterEqual(len(blocks), 2)
        for block in blocks:
            compile(textwrap.dedent(block), "refresh-packages.yml", "exec")

    def test_linkedin_embedded_python_blocks_compile(self) -> None:
        blocks = re.findall(r"python3 .*? <<'PY'\n(.*?)\n\s*PY", LINKEDIN_WORKFLOW, re.DOTALL)

        self.assertGreaterEqual(len(blocks), 1)
        for block in blocks:
            compile(textwrap.dedent(block), "linkedin-release.yml", "exec")

    def test_refresh_runs_each_artifact_independently(self) -> None:
        self.assertIn("artifact: [core, credits, codeApp]", REFRESH_WORKFLOW)
        self.assertIn('artifact="${{ matrix.artifact }}"', REFRESH_WORKFLOW)
        self.assertNotIn('artifact="${{ inputs.artifact || \'all\' }}"', REFRESH_WORKFLOW)

    def test_credits_provenance_excludes_shared_core_and_version_inputs(self) -> None:
        credits_inputs = ARTIFACT_PACKAGE_INPUTS["credits"]

        self.assertIn("solution/pvConversationInsightsCredits", credits_inputs)
        self.assertIn(":(glob)scripts/transcript_insights/*credit*.py", credits_inputs)
        self.assertNotIn("plugin", credits_inputs)
        self.assertNotIn("scripts/transcript_insights", credits_inputs)
        self.assertNotIn("config/release-packages.json", credits_inputs)

    def test_core_and_code_app_provenance_exclude_documentation(self) -> None:
        markdown_exclusion = ":(exclude,glob)**/*.md"

        self.assertIn(markdown_exclusion, ARTIFACT_PACKAGE_INPUTS["core"])
        self.assertIn(markdown_exclusion, ARTIFACT_PACKAGE_INPUTS["codeApp"])
        self.assertIn(
            "scripts/transcript_insights ':(exclude,glob)**/*.md'",
            REFRESH_WORKFLOW,
        )
        self.assertIn("codeapp ':(exclude,glob)**/*.md'", REFRESH_WORKFLOW)

    @patch("validate_candidate_packages.subprocess.run")
    def test_equivalent_candidate_provenance_requires_no_artifact_diff(self, run) -> None:
        run.return_value.returncode = 0

        self.assertTrue(commits_match_artifact_inputs("core", "a" * 40, "b" * 40))
        command = run.call_args.args[0]
        self.assertEqual(["git", "diff", "--quiet", "a" * 40, "b" * 40, "--"], command[:6])
        self.assertIn(":(exclude,glob)**/*.md", command)

        run.return_value.returncode = 1
        self.assertFalse(commits_match_artifact_inputs("core", "a" * 40, "b" * 40))
        self.assertFalse(commits_match_artifact_inputs("unknown", "a" * 40, "b" * 40))

    def test_component_release_regressions_run_in_ci(self) -> None:
        self.assertIn("scripts.test_component_release", BUILD_WORKFLOW)

    def test_promotion_requires_one_artifact(self) -> None:
        self.assertNotIn("          - all\n", PROMOTION_WORKFLOW)
        self.assertEqual(("core", "credits", "codeApp"), PROMOTABLE_ARTIFACTS)

    def test_promotion_rejects_missing_or_extra_candidate_scope(self) -> None:
        self.assertEqual(
            [
                "candidate manifest artifact scope does not match the requested scope",
                "candidate manifest artifacts do not exactly match the requested scope",
            ],
            candidate_scope_errors({"artifacts": {"core": {}, "credits": {}}}, ("core",)),
        )
        self.assertEqual(
            [],
            candidate_scope_errors(
                {"artifactScope": ["core"], "artifacts": {"core": {}}},
                ("core",),
            ),
        )
        self.assertEqual(
            ["candidate manifest artifact scope does not match the requested scope"],
            candidate_scope_errors(
                {"artifactScope": ["core", "core"], "artifacts": {"core": {}}},
                ("core",),
            ),
        )

    def test_manifest_update_inspects_only_selected_artifact(self) -> None:
        legacy_commit = "a" * 40
        previous = {
            "sourceCommit": legacy_commit,
            "artifacts": {
                "core": {"filename": "old-core.zip", "version": "2.0.0.5"},
                "credits": {"filename": "stable-credits.zip", "version": "2.0.0.5"},
                "codeApp": {"filename": "stable-code-app.zip", "version": "2.0.0.5"},
            },
        }
        config = {
            "core": {"filename": "new-core.zip"},
            "credits": {"filename": "candidate-credits.zip"},
            "codeApp": {"filename": "candidate-code-app.zip"},
        }

        with patch("update_release_manifest.inspect_package") as inspect:
            inspect.return_value = {"filename": "new-core.zip", "version": "2.1.0.0"}
            artifacts = release_artifacts_for_update(config, previous, "core", "b" * 40)

        inspect.assert_called_once_with("core", config["core"])
        self.assertEqual("new-core.zip", artifacts["core"]["filename"])
        self.assertEqual("stable-credits.zip", artifacts["credits"]["filename"])
        self.assertEqual("stable-code-app.zip", artifacts["codeApp"]["filename"])
        self.assertEqual(legacy_commit, artifacts["credits"]["sourceCommit"])

    def test_three_package_stable_manifest_survives_candidate_version_divergence(self) -> None:
        configured = {"core", "credits", "codeApp"}
        published = {
            "core": {"version": "2.0.0.5"},
            "credits": {"version": "2.0.0.5"},
            "codeApp": {"version": "2.0.0.5"},
        }

        self.assertEqual(
            configured,
            expected_published_artifacts(configured, published, "2.1.0.0"),
        )

    def test_legacy_two_package_manifest_remains_supported(self) -> None:
        configured = {"core", "credits", "codeApp"}
        published = {
            "core": {"version": "1.4.0.15"},
            "codeApp": {"version": "1.4.0.15"},
        }

        self.assertEqual(
            {"core", "codeApp"},
            expected_published_artifacts(configured, published, "2.1.0.0"),
        )

    def test_single_artifact_scope(self) -> None:
        self.assertEqual(("codeApp",), artifact_keys("codeApp"))
        self.assertEqual(
            "candidate-manifest-codeApp-2.1.0.0.json",
            candidate_manifest_name("codeApp", {"codeApp": "2.1.0.0"}),
        )

    def test_mixed_all_artifact_scope(self) -> None:
        self.assertEqual(
            "candidate-manifest-all.json",
            candidate_manifest_name(
                "all",
                {"core": "2.0.0.5", "credits": "2.0.0.5", "codeApp": "2.1.0.0"},
            ),
        )

    def test_legacy_synchronized_manifest_name_remains_supported(self) -> None:
        self.assertEqual(
            "candidate-manifest-2.0.0.5.json",
            candidate_manifest_name(
                "all",
                {"core": "2.0.0.5", "credits": "2.0.0.5", "codeApp": "2.0.0.5"},
            ),
        )

    def test_legacy_manifest_provenance_is_inherited(self) -> None:
        legacy = {"sourceCommit": "a" * 40, "artifacts": {"core": {}}}

        self.assertEqual("a" * 40, existing_artifact_source_commit(legacy, "core"))
        self.assertEqual("a" * 40, published_source_commit(legacy, "core"))

    def test_artifact_provenance_overrides_legacy_manifest_commit(self) -> None:
        manifest = {
            "sourceCommit": "a" * 40,
            "artifacts": {"codeApp": {"sourceCommit": "b" * 40}},
        }

        self.assertEqual("b" * 40, existing_artifact_source_commit(manifest, "codeApp"))
        self.assertEqual("b" * 40, published_source_commit(manifest, "codeApp"))
        self.assertEqual("b" * 40, evidence_source_commit(manifest, "codeApp"))

    def test_schema_two_requires_clean_install_evidence(self) -> None:
        self.assertIn("cleanInstall", REQUIRED_GATES)
        self.assertEqual(REQUIRED_GATES, required_gates(2))
        self.assertNotIn("cleanInstall", required_gates(1))

    def test_schema_two_candidate_run_id_must_be_positive_integer(self) -> None:
        self.assertTrue(valid_candidate_run_id(33154920938))
        for invalid in (None, 0, -1, True, "33154920938"):
            with self.subTest(invalid=invalid):
                self.assertFalse(valid_candidate_run_id(invalid))


if __name__ == "__main__":
    unittest.main()