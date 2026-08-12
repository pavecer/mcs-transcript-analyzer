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
SOLUTION_DEFINITION_PATH = ROOT / "solution" / "pvConversationInsights" / "solution-definition.json"
SOLUTION_XML_PATH = ROOT / "solution" / "pvConversationInsights" / "src" / "Other" / "Solution.xml"
GENERATED_SERVICES_PATH = ROOT / "codeapp" / "src" / "generated" / "services"


def service_filename(table_name: str) -> str:
    plural_name = f"{table_name[:-1]}ies" if table_name.endswith("y") else f"{table_name}s"
    return f"{plural_name[0].upper()}{plural_name[1:]}Service.ts"


def validate_release_config(config: dict[str, Any]) -> None:
    for key in ("core", "codeApp"):
        artifact = config[key]
        expected_filename = (
            f'{artifact["solutionUniqueName"]}-managed-{artifact["version"]}.zip'
        )
        if artifact["filename"] != expected_filename:
            raise RuntimeError(
                f"Unexpected {key} filename for version {artifact['version']}: "
                f"{artifact['filename']!r}; expected {expected_filename!r}"
            )

    core_version = config["core"]["version"]
    definition = json.loads(SOLUTION_DEFINITION_PATH.read_text(encoding="utf-8"))
    source_root = ET.parse(SOLUTION_XML_PATH).getroot()
    source_version = source_root.findtext(".//Version")
    if definition["solution"]["version"] != core_version or source_version != core_version:
        raise RuntimeError(
            "Core release version is not synchronized across release-packages.json, "
            "solution-definition.json, and src/Other/Solution.xml"
        )

    expected_services = {
        service_filename(table) for table in config["codeApp"]["requiredCoreTables"]
    }
    generated_services = {path.name for path in GENERATED_SERVICES_PATH.glob("*.ts")}
    if generated_services != expected_services:
        raise RuntimeError(
            "Code-app generated services do not match requiredCoreTables: "
            f"missing={sorted(generated_services - expected_services)}, "
            f"stale={sorted(expected_services - generated_services)}"
        )


def read_config() -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    validate_release_config(config)
    return config


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
        customizations = ET.fromstring(bundle.read("customizations.xml"))

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
        plugin_types = {
            item.get("Name")
            for item in customizations.findall(".//PluginType")
            if item.get("Name")
        }
        processing_steps = {
            item.get("Name")
            for item in customizations.findall(".//SdkMessageProcessingStep")
            if item.get("Name")
        }
        if "PvciTranscripts.ThresholdChangeRequestGuard" not in plugin_types:
            raise RuntimeError("Core package does not contain the threshold request guard plugin")
        if "PVCI Guard Threshold Change Request Create" not in processing_steps:
            raise RuntimeError("Core package does not contain the threshold request create guard step")
        actual_tables = {
            item.get("schemaName")
            for item in root_components
            if item.get("type") == "1" and item.get("schemaName")
        }
        actual_workflows = {
            item.get("Name")
            for item in customizations.findall(".//Workflows/Workflow")
            if item.get("Name")
        }
        actual_roles = {
            item.get("name")
            for item in customizations.findall(".//Roles/Role")
            if item.get("name")
        }
        expected_components = {
            "tables": set(config["requiredTables"]),
            "workflows": set(config["requiredWorkflows"]),
            "roles": set(config["requiredRoles"]),
        }
        actual_components = {
            "tables": actual_tables,
            "workflows": actual_workflows,
            "roles": actual_roles,
        }
        drift = {
            component: {
                "missing": sorted(expected_components[component] - actual),
                "unexpected": sorted(actual - expected_components[component]),
            }
            for component, actual in actual_components.items()
            if actual != expected_components[component]
        }
        if drift:
            raise RuntimeError(f"Core package components changed: {drift}")
    if key == "codeApp":
        if not any(
            item.get("type") == "300"
            and item.get("schemaName") == config["componentSchemaName"]
            for item in root_components
        ):
            raise RuntimeError("Code-app package does not contain the configured preview app")
        expected_tables = set(config["requiredCoreTables"])
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