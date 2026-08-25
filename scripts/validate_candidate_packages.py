#!/usr/bin/env python3
"""Validate synchronized tenant-neutral managed solution candidates."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from zipfile import ZipFile

import update_release_manifest as release


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "release-packages.json"
FULL_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--directory", type=Path, default=Path("output/candidate"))
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    if args.source_commit and not FULL_COMMIT_PATTERN.fullmatch(args.source_commit):
        raise SystemExit("--source-commit must be a full 40-character lowercase Git commit SHA")

    directory = args.directory.resolve()
    base_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config = json.loads(json.dumps(base_config))
    for key in release.ARTIFACT_KEYS:
        solution_name = config[key]["solutionUniqueName"]
        config[key]["version"] = args.version
        config[key]["filename"] = f"{solution_name}-managed-{args.version}.zip"
    central_flow = "PVCI Collect Central Transcripts (scheduled)"
    if central_flow not in config["core"]["requiredWorkflows"]:
        config["core"]["requiredWorkflows"].append(central_flow)

    previous_downloads = release.DOWNLOADS
    release.DOWNLOADS = directory
    try:
        artifacts = {
            key: release.inspect_package(key, config[key]) for key in release.ARTIFACT_KEYS
        }
    finally:
        release.DOWNLOADS = previous_downloads

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
        "status": "ok",
        "version": args.version,
        "directory": str(directory),
        "tenantNeutral": True,
        "artifacts": artifacts,
    }
    if args.source_commit:
        manifest["sourceCommit"] = args.source_commit
    manifest_path = directory / f"candidate-manifest-{args.version}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()