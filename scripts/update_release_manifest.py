#!/usr/bin/env python3
"""Validate managed solution exports and write the Pages release manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
CORE_SOLUTION_SOURCE_PATH = ROOT / "solution" / "pvConversationInsights" / "src"
FULL_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ARTIFACT_KEYS = ("core", "credits", "codeApp")


def service_filename(table_name: str) -> str:
    plural_name = f"{table_name[:-1]}ies" if table_name.endswith("y") else f"{table_name}s"
    return f"{plural_name[0].upper()}{plural_name[1:]}Service.ts"


def validate_release_config(config: dict[str, Any]) -> None:
    if set(config) != set(ARTIFACT_KEYS):
        raise RuntimeError(f"Expected release artifacts {ARTIFACT_KEYS}, got {sorted(config)}")
    for key in ARTIFACT_KEYS:
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
        service_filename(table)
        for table in (
            config["codeApp"]["requiredCoreTables"]
            + config["codeApp"].get("requiredSystemTables", [])
        )
    }
    generated_services = {path.name for path in GENERATED_SERVICES_PATH.glob("*.ts")}
    if generated_services != expected_services:
        raise RuntimeError(
            "Code-app generated services do not match requiredCoreTables: "
            f"missing={sorted(generated_services - expected_services)}, "
            f"stale={sorted(expected_services - generated_services)}"
        )

    forbidden_topology_markers = (
        "pvci_transcript_http_",
        "pvci_transcript_source_",
    )
    violations: list[str] = []
    central_flow_files: list[Path] = []
    for path in CORE_SOLUTION_SOURCE_PATH.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if path.name.startswith("PVCICollectCentralTranscripts") and path.suffix.lower() == ".json":
            central_flow_files.append(path)
        if path.suffix.lower() not in {".xml", ".json"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(marker in text for marker in forbidden_topology_markers):
            violations.append(relative)
    if violations:
        raise RuntimeError(
            "Core solution source contains tenant-specific central transcript topology: "
            + ", ".join(sorted(set(violations)))
        )
    if len(central_flow_files) != 1:
        raise RuntimeError(
            "Core solution source must contain exactly one PVCI Collect Central Transcripts flow"
        )
    central_flow = central_flow_files[0].read_text(encoding="utf-8")
    required_collector_markers = (
        "ListRecordsWithOrganization",
        "pvci_environmentinventories",
        "pvci_environmenturl",
        "pvci_centralcollector",
        "pvci_ImportCentralTranscriptBatch",
    )
    missing = [marker for marker in required_collector_markers if marker not in central_flow]
    if missing:
        raise RuntimeError(
            f"Core central transcript flow is missing required generic behavior: {missing}"
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
        package_names = bundle.namelist()
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
        if any(
            name.lower().endswith(
                "/pvci_creditreportingtenantid/environmentvariabledefinition.xml"
            )
            for name in package_names
        ):
            raise RuntimeError("Core package contains the credit reporting tenant variable")
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
    if key == "credits":
        packaged_values = [
            name
            for name in package_names
            if name.lower().endswith("/environmentvariablevalues.json")
        ]
        if packaged_values:
            raise RuntimeError(
                f"Credit add-on contains tenant-specific environment variable values: {packaged_values}"
            )
        unexpected_roots = [item for item in root_components if item.get("type") != "29"]
        if unexpected_roots:
            raise RuntimeError(f"Credit add-on contains non-workflow root components: {unexpected_roots}")
        actual_workflows = {
            item.get("Name")
            for item in customizations.findall(".//Workflows/Workflow")
            if item.get("Name")
        }
        expected_workflows = set(config["requiredWorkflows"])
        if actual_workflows != expected_workflows:
            raise RuntimeError(
                "Credit add-on workflows changed: "
                f"missing={sorted(expected_workflows - actual_workflows)}, "
                f"unexpected={sorted(actual_workflows - expected_workflows)}"
            )
        actual_references = {
            item.get("connectionreferencelogicalname")
            for item in customizations.findall(".//connectionreference")
        }
        expected_references = set(config["requiredConnectionReferences"])
        if actual_references != expected_references:
            raise RuntimeError(
                "Credit add-on connection references changed: "
                f"missing={sorted(expected_references - actual_references)}, "
                f"unexpected={sorted(actual_references - expected_references)}"
            )
        actual_variables = {
            Path(name).parent.name
            for name in package_names
            if name.lower().endswith("/environmentvariabledefinition.xml")
        }
        expected_variables = set(config["requiredEnvironmentVariables"])
        if actual_variables != expected_variables:
            raise RuntimeError(
                "Credit add-on environment variables changed: "
                f"missing={sorted(expected_variables - actual_variables)}, "
                f"unexpected={sorted(actual_variables - expected_variables)}"
            )
    if key == "codeApp":
        if not any(
            item.get("type") == "300"
            and item.get("schemaName") == config["componentSchemaName"]
            for item in root_components
        ):
            raise RuntimeError("Code-app package does not contain the configured code app")
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


def existing_artifact_source_commit(manifest: dict[str, Any], key: str) -> str | None:
    artifact = manifest.get("artifacts", {}).get(key, {})
    if isinstance(artifact, dict) and FULL_COMMIT_PATTERN.fullmatch(
        str(artifact.get("sourceCommit", ""))
    ):
        return str(artifact["sourceCommit"])
    legacy = manifest.get("sourceCommit")
    return str(legacy) if FULL_COMMIT_PATTERN.fullmatch(str(legacy or "")) else None


def release_artifacts_for_update(
    config: dict[str, Any],
    previous_manifest: dict[str, Any],
    selected_key: str,
    source_commit: str,
) -> dict[str, Any]:
    previous_artifacts = previous_manifest.get("artifacts", {})
    artifacts: dict[str, Any] = {}
    for key in ARTIFACT_KEYS:
        if key == selected_key:
            artifact = inspect_package(key, config[key])
            artifact["sourceCommit"] = source_commit
            artifacts[key] = artifact
            continue

        previous = previous_artifacts.get(key)
        if not isinstance(previous, dict):
            raise RuntimeError(f"Cannot preserve missing unchanged artifact {key}")
        artifact = dict(previous)
        artifact_source_commit = existing_artifact_source_commit(previous_manifest, key)
        if not artifact_source_commit:
            raise RuntimeError(f"Cannot preserve source provenance for unchanged artifact {key}")
        artifact.setdefault("sourceCommit", artifact_source_commit)
        artifacts[key] = artifact
    return artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True, help="Commit represented by the packages")
    parser.add_argument("--artifact", choices=ARTIFACT_KEYS, required=True)
    args = parser.parse_args()
    if not FULL_COMMIT_PATTERN.fullmatch(args.source_commit):
        raise SystemExit("--source-commit must be a full 40-character lowercase Git commit SHA")

    config = read_config()
    previous_manifest = (
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if MANIFEST_PATH.is_file()
        else {}
    )
    artifacts = release_artifacts_for_update(
        config,
        previous_manifest,
        args.artifact,
        args.source_commit,
    )
    manifest = {
        "schemaVersion": 2,
        "generatedAtUtc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "artifacts": artifacts,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()