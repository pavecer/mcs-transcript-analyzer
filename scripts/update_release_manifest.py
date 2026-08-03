#!/usr/bin/env python3
"""Validate managed solution exports and write the Pages release manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "release-packages.json"
DOWNLOADS = ROOT / "site" / "downloads"
MANIFEST_PATH = DOWNLOADS / "release-manifest.json"


def read_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def inspect_package(key: str, config: dict[str, Any]) -> dict[str, Any]:
    package = DOWNLOADS / config["filename"]
    if not package.is_file():
        raise FileNotFoundError(f"Missing {key} package: {package.relative_to(ROOT)}")

    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    with ZipFile(package) as bundle:
        corrupt = bundle.testzip()
        if corrupt:
            raise RuntimeError(f"Corrupt file in {package.name}: {corrupt}")
        root = ET.fromstring(bundle.read("solution.xml"))

    unique_name = root.findtext(".//UniqueName")
    version = root.findtext(".//Version")
    managed = root.findtext(".//Managed")
    if (unique_name, version, managed) != (
        config["solutionUniqueName"],
        config["version"],
        "1",
    ):
        raise RuntimeError(
            f"Unexpected {key} package identity: "
            f"name={unique_name!r}, version={version!r}, managed={managed!r}"
        )

    root_components = [item.attrib for item in root.findall(".//RootComponent")]
    missing_dependencies = [
        item.find("Required").attrib
        for item in root.findall(".//MissingDependency")
        if item.find("Required") is not None
    ]
    if key == "core":
        if not any(
            item.get("type") == "66"
            and item.get("schemaName") == "pvci_PvciControls.JsonViewer"
            for item in root_components
        ):
            raise RuntimeError("Core package does not contain the JSON Viewer PCF")
        if any(item.get("type") == "66" for item in missing_dependencies):
            raise RuntimeError("Core package still has an unresolved PCF dependency")
    if key == "codeApp":
        if not any(
            item.get("type") == "300"
            and item.get("schemaName") == config["componentSchemaName"]
            for item in root_components
        ):
            raise RuntimeError("Code-app package does not contain the configured preview app")
        expected_tables = {
            "pvci_flowrundetail",
            "pvci_transcriptsession",
            "pvci_transcriptturn",
        }
        required_tables = {
            item.get("schemaName")
            for item in missing_dependencies
            if item.get("type") == "1"
        }
        unexpected = [item for item in missing_dependencies if item.get("type") != "1"]
        if required_tables != expected_tables or unexpected:
            raise RuntimeError(
                "Code-app package dependencies changed: "
                f"tables={sorted(required_tables)}, other={unexpected}"
            )

    return {
        "filename": config["filename"],
        "managed": True,
        "sha256": digest,
        "solutionUniqueName": unique_name,
        "version": version,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True, help="Commit represented by the packages")
    args = parser.parse_args()

    config = read_config()
    manifest = {
        "schemaVersion": 1,
        "sourceCommit": args.source_commit,
        "generatedAtUtc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "artifacts": {
            "core": inspect_package("core", config["core"]),
            "codeApp": inspect_package("codeApp", config["codeApp"]),
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()