#!/usr/bin/env python3
"""Validate the repository's exactly-three-solution product ownership contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "solution" / "pvConversationInsights" / "src"
CREDITS = ROOT / "solution" / "pvConversationInsightsCredits" / "src"
CODE_APP_CONFIG_SAMPLE = ROOT / "codeapp" / "power.config.sample.json"
CODE_APP_SERVICES = ROOT / "codeapp" / "src" / "generated" / "services"
RELEASE_CONFIG = ROOT / "config" / "release-packages.json"
ALLOWED_PROGRAMMATIC_TENANT_ID = "1938ee32-a258-454c-b8db-3a928341bd69"

EXPECTED_CORE_FLOWS = {
    "PVCI Collect Central Transcripts (scheduled)",
    "PVCI Collect Tenant Agent Inventory (scheduled)",
    "PVCI Sync Conversation Transcripts (scheduled)",
    "PVCI Verify Transcript Source Access (scheduled)",
}
EXPECTED_CREDIT_FLOWS = {
    "PVCI Apply Credit Governance Requests (scheduled)",
    "PVCI Collect Copilot Credit Usage (scheduled)",
    "PVCI Collect Credit Governance (scheduled)",
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
    "pvci_powerplatformadminv2",
}
EXPECTED_CREDIT_REFERENCES = {"pvci_licensinghttp", "pvci_powerplatformapi"}
EXPECTED_CREDIT_VARIABLES = {"pvci_CreditReportingTenantId"}
WRITE_GUARDED_SCRIPTS = {
    "collect_central_transcripts.py",
    "create_app_views.py",
    "create_central_transcript_flow.py",
    "create_credit_forms.py",
    "create_credit_governance_flow.py",
    "create_credit_governance_processor_flow.py",
    "create_credit_sync_flow.py",
    "create_forms.py",
    "create_inventory_sync_flow.py",
    "create_model_driven_app.py",
    "create_security_roles.py",
    "create_sync_flow.py",
    "create_transcript_access_verification_flow.py",
    "fetch_flow_run_details.py",
    "import_transcript_source_registry.py",
    "invoke_central_transcript_import.py",
    "invoke_credit_import.py",
    "provision_dataverse_solution.py",
    "provision_dataverse_solution_webapi.py",
    "register_central_transcript_plugin.py",
    "register_credit_plugin.py",
    "register_plugin.py",
    "smoke_test_transcript_access_verification.py",
    "sync_transcripts.py",
    "validate_source_access_onboarding.py",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def service_filename(table_name: str) -> str:
    plural_name = f"{table_name[:-1]}ies" if table_name.endswith("y") else f"{table_name}s"
    return f"{plural_name[0].upper()}{plural_name[1:]}Service.ts"


def main() -> None:
    release = json.loads(RELEASE_CONFIG.read_text(encoding="utf-8"))
    if set(release) != {"core", "credits", "codeApp"}:
        fail(f"Expected exactly core, credits, and codeApp release artifacts, got {sorted(release)}")
    if release["core"]["solutionUniqueName"] != "pvConversationInsights":
        fail("Core solution unique name changed")
    if release["credits"]["solutionUniqueName"] != "pvConversationInsightsCredits":
        fail("Credit add-on solution unique name changed")
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

    credit_workflow_names = {
        ET.parse(path).getroot().attrib["Name"]
        for path in (CREDITS / "Workflows").glob("*.json.data.xml")
    }
    if credit_workflow_names != EXPECTED_CREDIT_FLOWS:
        fail(
            "Credit add-on workflow ownership drift: "
            f"missing={sorted(EXPECTED_CREDIT_FLOWS - credit_workflow_names)}, "
            f"unexpected={sorted(credit_workflow_names - EXPECTED_CREDIT_FLOWS)}"
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
    core_variables = {
        path.parent.name
        for path in (CORE / "environmentvariabledefinitions").glob("*/environmentvariabledefinition.xml")
    }
    if core_variables:
        fail(f"Core contains optional credit environment variables: {sorted(core_variables)}")
    if any(name.startswith(("pvci_transcript_http_", "pvci_transcript_source_")) for name in references):
        fail("Per-source central transcript references are forbidden")

    credit_customizations = ET.parse(CREDITS / "Other" / "Customizations.xml").getroot()
    credit_references = {
        item.attrib["connectionreferencelogicalname"]
        for item in credit_customizations.findall(".//connectionreference")
    }
    if credit_references != EXPECTED_CREDIT_REFERENCES:
        fail(f"Credit add-on connection-reference ownership drift: {sorted(credit_references)}")
    credit_variables = {
        path.parent.name
        for path in (CREDITS / "environmentvariabledefinitions").glob("*/environmentvariabledefinition.xml")
    }
    if credit_variables != EXPECTED_CREDIT_VARIABLES:
        fail(f"Credit add-on environment-variable ownership drift: {sorted(credit_variables)}")

    forbidden_credit_directories = {
        "AppModules",
        "AppModuleSiteMaps",
        "Controls",
        "customapis",
        "Entities",
        "PluginAssemblies",
        "Roles",
        "SdkMessageProcessingSteps",
    }
    unexpected_credit_directories = {
        path.name for path in CREDITS.iterdir()
        if path.is_dir() and path.name in forbidden_credit_directories
    }
    if unexpected_credit_directories:
        fail(f"Credit add-on contains forbidden backend/schema roots: {sorted(unexpected_credit_directories)}")

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

    inventory_flow = next((CORE / "Workflows").glob("PVCICollectTenantAgentInventory*.json"))
    if "pvci_CreditReportingTenantId" in inventory_flow.read_text(encoding="utf-8"):
        fail("Core inventory flow depends on the optional credit tenant variable")

    app_modules = list((CORE / "AppModules").glob("**/AppModule.xml"))
    if len(app_modules) != 1:
        fail(f"Expected one core model-driven app, found {len(app_modules)}")

    code_app = json.loads(CODE_APP_CONFIG_SAMPLE.read_text(encoding="utf-8"))
    if code_app.get("appType") != "CodeApp":
        fail("Code-app solution source is not a Power Apps code app")
    expected_services = {
        service_filename(table)
        for table in (
            release["codeApp"]["requiredCoreTables"]
            + release["codeApp"].get("requiredSystemTables", [])
        )
    }
    generated_services = {path.name for path in CODE_APP_SERVICES.glob("*.ts")}
    if generated_services != expected_services:
        fail(
            "Code-app dependency ownership drift: "
            f"missing={sorted(expected_services - generated_services)}, "
            f"unexpected={sorted(generated_services - expected_services)}"
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
    if "--source-commit" not in refresh_workflow or "steps.changes.outputs.source_sha" not in refresh_workflow:
        fail("Release refresh workflow does not persist candidate source provenance")

    promotion_workflow = (ROOT / ".github" / "workflows" / "release-promotion.yml").read_text(
        encoding="utf-8"
    )
    for required in (
        "validate_release_promotion.py",
        "validate_release_evidence.py",
        "candidate_run_id",
    ):
        if required not in promotion_workflow:
            fail(f"Release promotion workflow is missing {required}")
    for forbidden in ("pac solution import", "--publish-changes"):
        if forbidden in promotion_workflow:
            fail(f"Release promotion workflow must be read-only; found {forbidden}")

    transcript_scripts = ROOT / "scripts" / "transcript_insights"
    unguarded = [
        name
        for name in sorted(WRITE_GUARDED_SCRIPTS)
        if "require_authorized_" not in (transcript_scripts / name).read_text(encoding="utf-8")
    ]
    if unguarded:
        fail(f"Dataverse write entry points are missing the tenant-ID guard: {unguarded}")
    token_helper = (transcript_scripts / "dv_token.py").read_text(encoding="utf-8")
    if ALLOWED_PROGRAMMATIC_TENANT_ID not in token_helper:
        fail("Shared Dataverse token helper is missing the immutable tenant write allowlist")

    print(
        "PASS: exactly three product solutions; core owns transcript/shared runtime, the optional "
        "credit add-on owns only licensing references and credit flows, and the separate optional "
        "code-app solution owns only the app dependency surface; candidate "
        "automation is artifact-only and development writes are tenant-ID guarded"
    )


if __name__ == "__main__":
    main()