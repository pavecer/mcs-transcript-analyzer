#!/usr/bin/env python3
"""Validate one or more tenant-neutral managed solution candidates."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from zipfile import ZipFile

import update_release_manifest as release


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "release-packages.json"
FULL_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PACKAGE_INPUTS = (
    "codeapp",
    "plugin",
    "pcf",
    "solution",
    "scripts/transcript_insights",
    "config/release-packages.json",
    ":(exclude,glob)**/*.md",
)
ARTIFACT_PACKAGE_INPUTS = {
    "core": (
        "plugin",
        "pcf",
        "solution/pvConversationInsights",
        "scripts/transcript_insights",
        ":(exclude,glob)**/*.md",
    ),
    "credits": (
        "solution/pvConversationInsightsCredits",
        ":(glob)scripts/transcript_insights/*credit*.py",
    ),
    "codeApp": (
        "codeapp",
        ":(exclude,glob)**/*.md",
    ),
}

FORBIDDEN_MARKERS = (
    "pvci_transcript_http_",
    "pvci_transcript_source_",
    "PVE Preview Sand US",
    "https://orga2778a15.crm.dynamics.com",
    "67203dc9-8a11-e6ef-9970-81e05021161c",
    "https://org760734c4.crm4.dynamics.com",
    "006cf8b9-27f8-e2f7-8a14-9be3642d8552",
)


def package_text(path: Path) -> str:
    parts: list[str] = []
    with ZipFile(path) as bundle:
        for name in bundle.namelist():
            if Path(name).suffix.lower() not in {".xml", ".json"}:
                continue
            parts.append(bundle.read(name).decode("utf-8", errors="ignore"))
    return "\n".join(parts)


def artifact_keys(artifact: str) -> tuple[str, ...]:
    return release.ARTIFACT_KEYS if artifact == "all" else (artifact,)


def package_source_commit(artifact: str = "all") -> str:
    inputs = PACKAGE_INPUTS if artifact == "all" else ARTIFACT_PACKAGE_INPUTS[artifact]
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", *inputs],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commits_match_artifact_inputs(artifact: str, first: str, second: str) -> bool:
    if (
        artifact not in ARTIFACT_PACKAGE_INPUTS
        or not FULL_COMMIT_PATTERN.fullmatch(first)
        or not FULL_COMMIT_PATTERN.fullmatch(second)
    ):
        return False
    result = subprocess.run(
        ["git", "diff", "--quiet", first, second, "--", *ARTIFACT_PACKAGE_INPUTS[artifact]],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def candidate_manifest_name(artifact: str, versions: dict[str, str]) -> str:
    unique_versions = set(versions.values())
    if artifact == "all" and len(unique_versions) == 1:
        return f"candidate-manifest-{next(iter(unique_versions))}.json"
    if artifact == "all":
        return "candidate-manifest-all.json"
    return f"candidate-manifest-{artifact}-{versions[artifact]}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", choices=("all", *release.ARTIFACT_KEYS), default="all")
    parser.add_argument("--version")
    parser.add_argument("--directory", type=Path, default=Path("output/candidate"))
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    selected_keys = artifact_keys(args.artifact)
    source_commit = args.source_commit or package_source_commit(args.artifact)
    if not FULL_COMMIT_PATTERN.fullmatch(source_commit):
        raise SystemExit("--source-commit must be a full 40-character lowercase Git commit SHA")

    directory = args.directory.resolve()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    versions = {key: config[key]["version"] for key in selected_keys}
    if args.version and set(versions.values()) != {args.version}:
        raise SystemExit(
            f"--version {args.version} does not match selected artifact versions: {versions}"
        )
    central_flow = "PVCI Collect Central Transcripts (scheduled)"
    if central_flow not in config["core"]["requiredWorkflows"]:
        config["core"]["requiredWorkflows"].append(central_flow)

    previous_downloads = release.DOWNLOADS
    release.DOWNLOADS = directory
    try:
        artifacts = {
            key: release.inspect_package(key, config[key]) for key in selected_keys
        }
    finally:
        release.DOWNLOADS = previous_downloads

    if "core" in selected_keys:
        core_path = directory / config["core"]["filename"]
        core_text = package_text(core_path)
        leaked = [marker for marker in FORBIDDEN_MARKERS if marker in core_text]
        if leaked:
            raise RuntimeError(f"Core candidate contains tenant-specific runtime markers: {leaked}")
        if "pvci_ImportCentralTranscriptBatch" not in core_text:
            raise RuntimeError("Core candidate does not contain pvci_ImportCentralTranscriptBatch")
        if "PvciTranscripts.ImportCentralTranscriptBatch" not in core_text:
            raise RuntimeError("Core candidate does not contain the central transcript plugin type")
        for marker in (
            "PVCI Collect Central Transcripts (scheduled)",
            "ListRecordsWithOrganization",
            "pvci_environmenturl",
            "pvci_transcriptcollectorenabled eq true",
            "pvci_centralcollector",
        ):
            if marker not in core_text:
                raise RuntimeError(f"Core candidate does not contain packaged collector marker: {marker}")

    manifest = {
        "schemaVersion": 2,
        "status": "ok",
        "artifactScope": list(selected_keys),
        "versions": versions,
        "directory": str(directory),
        "tenantNeutral": True,
        "artifacts": artifacts,
        "sourceCommit": source_commit,
    }
    if len(set(versions.values())) == 1:
        manifest["version"] = next(iter(versions.values()))
    manifest_path = directory / candidate_manifest_name(args.artifact, versions)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()