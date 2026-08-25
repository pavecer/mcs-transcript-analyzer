#!/usr/bin/env python3
"""Validate synchronized tenant-neutral managed solution candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile

import update_release_manifest as release


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "release-packages.json"

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
    args = parser.parse_args()

    directory = args.directory.resolve()
    base_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config = json.loads(json.dumps(base_config))
    for key in ("core", "codeApp"):
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
            "core": release.inspect_package("core", config["core"]),
            "codeApp": release.inspect_package("codeApp", config["codeApp"]),
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

    print(json.dumps({
        "status": "ok",
        "version": args.version,
        "directory": str(directory),
        "tenantNeutral": True,
        "artifacts": artifacts,
    }, indent=2))


if __name__ == "__main__":
    main()