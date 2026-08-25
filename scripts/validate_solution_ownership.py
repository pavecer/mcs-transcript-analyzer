#!/usr/bin/env python3
"""Validate the repository's exactly-two-solution product ownership contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "solution" / "pvConversationInsights" / "src"
CODE_APP_CONFIG = ROOT / "codeapp" / "power.config.json"
RELEASE_CONFIG = ROOT / "config" / "release-packages.json"
ALLOWED_PROGRAMMATIC_TENANT_ID = "1938ee32-a258-454c-b8db-3a928341bd69"

EXPECTED_CORE_FLOWS = {
    "PVCI Apply Credit Governance Requests (scheduled)",
    "PVCI Collect Central Transcripts (scheduled)",
    "PVCI Collect Copilot Credit Usage (scheduled)",
    "PVCI Collect Credit Governance (scheduled)",
    "PVCI Collect Tenant Agent Inventory (scheduled)",
    "PVCI Sync Conversation Transcripts (scheduled)",
    "PVCI Verify Transcript Source Access (scheduled)",
}
EXPECTED_CUSTOM_APIS = {
    "pvci_ImportCentralTranscriptBatch",
    "pvci_ImportCreditUsageBatch",
    "pvci_SyncConversationTranscripts",
}
EXPECTED_PLUGIN_TYPES = {
    "PvciTranscripts.CreditUserDisclosure",
    "PvciTranscripts.ImportCentralTranscriptBatch",
    "PvciTranscripts.ImportCreditUsageBatch",
    "PvciTranscripts.SyncConversationTranscripts",
    "PvciTranscripts.ThresholdChangeRequestGuard",
}
EXPECTED_CORE_REFERENCES = {
    "pvci_centralcollector",
    "pvci_dataversesync",
    "pvci_licensinghttp",
    "pvci_powerplatformadminv2",
    "pvci_powerplatformapi",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    release = json.loads(RELEASE_CONFIG.read_text(encoding="utf-8"))
    if set(release) != {"core", "codeApp"}:
        fail(f"Expected exactly core and codeApp release artifacts, got {sorted(release)}")
    if release["core"]["solutionUniqueName"] != "pvConversationInsights":
        fail("Core solution unique name changed")
    if release["codeApp"]["solutionUniqueName"] != "pvConversationInsightsCodeApp":
        fail("Code-app solution unique name changed")

    workflow_names = {
        ET.parse(path).getroot().attrib["Name"]
        for path in (CORE / "Workflows").glob("*.json.data.xml")
    }
    if workflow_names != EXPECTED_CORE_FLOWS:
        fail(
            "Core workflow ownership drift: "
            f"missing={sorted(EXPECTED_CORE_FLOWS - workflow_names)}, "
            f"unexpected={sorted(workflow_names - EXPECTED_CORE_FLOWS)}"
        )

    custom_apis = {path.name for path in (CORE / "customapis").iterdir() if path.is_dir()}
    if custom_apis != EXPECTED_CUSTOM_APIS:
        fail(f"Core Custom API ownership drift: {sorted(custom_apis)}")

    assembly_data = next((CORE / "PluginAssemblies").glob("*/plugin.dll.data.xml"))
    plugin_types = {
        item.attrib["Name"]
        for item in ET.parse(assembly_data).getroot().findall(".//PluginType")
    }
    if plugin_types != EXPECTED_PLUGIN_TYPES:
        fail(f"Core plugin ownership drift: {sorted(plugin_types)}")

    customizations = ET.parse(CORE / "Other" / "Customizations.xml").getroot()
    references = {
        item.attrib["connectionreferencelogicalname"]
        for item in customizations.findall(".//connectionreference")
    }
    if references != EXPECTED_CORE_REFERENCES:
        fail(f"Core connection-reference ownership drift: {sorted(references)}")
    if any(name.startswith(("pvci_transcript_http_", "pvci_transcript_source_")) for name in references):
        fail("Per-source central transcript references are forbidden")

    central_flow = next((CORE / "Workflows").glob("PVCICollectCentralTranscripts*.json"))
    central_text = central_flow.read_text(encoding="utf-8")
    for marker in (
        "ListRecordsWithOrganization",
        "pvci_environmenturl",
        "pvci_centralcollector",
        "pvci_ImportCentralTranscriptBatch",
    ):
        if marker not in central_text:
            fail(f"Packaged central collector is missing {marker}")

    app_modules = list((CORE / "AppModules").glob("**/AppModule.xml"))
    if len(app_modules) != 1:
        fail(f"Expected one core model-driven app, found {len(app_modules)}")

    code_app = json.loads(CODE_APP_CONFIG.read_text(encoding="utf-8"))
    if code_app.get("appType") != "CodeApp":
        fail("Preview solution source is not a Power Apps code app")
    required_tables = set(release["codeApp"]["requiredCoreTables"])
    configured_tables = {
        value["logicalName"]
        for value in code_app["databaseReferences"]["default.cds"]["dataSources"].values()
    }
    if configured_tables != required_tables:
        fail(
            "Code-app dependency ownership drift: "
            f"missing={sorted(required_tables - configured_tables)}, "
            f"unexpected={sorted(configured_tables - required_tables)}"
        )

    candidate_workflow = (ROOT / ".github" / "workflows" / "candidate-release.yml").read_text(
        encoding="utf-8"
    )
    for forbidden in ("test_environment_url", "pac solution import", "--publish-changes"):
        if forbidden in candidate_workflow:
            fail(f"Candidate workflow must be artifact-only; found {forbidden}")

    refresh_workflow = (ROOT / ".github" / "workflows" / "refresh-packages.yml").read_text(
        encoding="utf-8"
    )
    if f"ALLOWED_PROGRAMMATIC_TENANT_ID: {ALLOWED_PROGRAMMATIC_TENANT_ID}" not in refresh_workflow:
        fail("Release refresh workflow is missing the immutable tenant write allowlist")
    if 'POWER_PLATFORM_TENANT_ID" != "$ALLOWED_PROGRAMMATIC_TENANT_ID' not in refresh_workflow:
        fail("Release refresh workflow does not reject non-allowlisted tenants")

    print(
        "PASS: exactly two product solutions; core owns all backend/runtime components and "
        "the separate preview solution owns only the code app dependency surface; candidate "
        "automation is artifact-only and development writes are tenant-ID guarded"
    )


if __name__ == "__main__":
    main()