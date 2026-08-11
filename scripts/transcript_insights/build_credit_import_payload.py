#!/usr/bin/env python3
"""Build a normalized credit import payload from a Power Platform admin HAR."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


HOST = "licensing.powerplatform.microsoft.com"
RESOURCE_PATH = "/entitlements/MCSMessages/resources"
CAPACITY_PATH = "/environments/entitlementConsumptions/MCSMessages"


def stable_key(*parts: object) -> str:
    normalized = "|".join("" if part is None else str(part).strip() for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def json_response(entry: dict[str, Any]) -> Any:
    text = ((entry.get("response") or {}).get("content") or {}).get("text") or ""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def tenant_from_path(path: str) -> str | None:
    parts = [part for part in path.split("/") if part]
    try:
        return parts[parts.index("tenants") + 1]
    except (ValueError, IndexError):
        return None


def resource_type(resource_id: str) -> str:
    try:
        import uuid

        uuid.UUID(resource_id)
        return "agent_or_flow"
    except (ValueError, AttributeError):
        return "service_or_group"


def get_rule(rules: list[dict[str, Any]], rule_type: str) -> dict[str, Any] | None:
    return next((rule for rule in rules if rule.get("ruleType") == rule_type), None)


def build_payload(document: dict[str, Any], source_name: str) -> dict[str, Any]:
    entries = document.get("log", {}).get("entries", [])
    resource_rows: list[dict[str, Any]] = []
    capacity_rows: list[dict[str, Any]] = []
    tenant_id: str | None = None

    for entry in entries:
        request = entry.get("request") or {}
        url = request.get("url") or ""
        parsed = urlsplit(url)
        if parsed.hostname != HOST or request.get("method") != "GET":
            continue
        body = json_response(entry)
        if body is None:
            continue
        tenant_id = tenant_id or tenant_from_path(parsed.path)

        if RESOURCE_PATH in parsed.path:
            groups = body if isinstance(body, list) else body.get("value", [])
            for group in groups:
                resource_rows.extend(group.get("resources", []))
        elif CAPACITY_PATH in parsed.path:
            capacity_rows.extend(body.get("value", []))

    if not tenant_id:
        raise ValueError("No licensing tenant was found in the HAR.")

    imported_on = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    agents: dict[str, dict[str, Any]] = {}
    usage: dict[str, dict[str, Any]] = {}

    for row in resource_rows:
        environment_id = str(row.get("environmentId") or "")
        resource_id = str(row.get("resourceId") or "")
        metadata = row.get("metadata") or {}
        display_name = str(metadata.get("ResourceName") or resource_id or "Unknown resource")
        agent_source_key = stable_key(tenant_id, environment_id, resource_id)
        agents[agent_source_key] = {
            "sourceKey": agent_source_key,
            "tenantId": tenant_id,
            "environmentId": environment_id,
            "resourceId": resource_id,
            "botId": resource_id if resource_type(resource_id) == "agent_or_flow" else None,
            "name": display_name,
            "displayName": display_name,
            "resourceType": resource_type(resource_id),
            "harness": "unknown",
            "classificationSource": "ppac_resource_aggregate",
            "classificationConfidence": "unresolved",
            "inventorySource": "PPAC MCSMessages resources",
            "lastSyncedOn": imported_on,
            "evidence": {
                "users": metadata.get("Users"),
                "asOfDate": row.get("asOfDate"),
            },
        }
        usage_date = row.get("asOfDate")
        usage_key = stable_key(
            tenant_id,
            environment_id,
            resource_id,
            usage_date,
            "MCSMessages",
            "PPAC resource aggregate",
        )
        usage[usage_key] = {
            "sourceKey": usage_key,
            "agentSourceKey": agent_source_key,
            "tenantId": tenant_id,
            "environmentId": environment_id,
            "resourceId": resource_id,
            "name": f"{display_name} - {str(usage_date)[:10]}",
            "agentName": display_name,
            "usageDate": usage_date,
            "entitlementId": "MCSMessages",
            "sourceUnit": row.get("unit") or "Messages",
            "billedCredits": row.get("consumed") or 0,
            "nonBilledCredits": metadata.get("NonBillableQuantity") or 0,
            "featureName": "PPAC resource aggregate",
            "users": metadata.get("Users"),
            "resourceType": resource_type(resource_id),
            "harness": "unknown",
            "resolutionStatus": "resource_id_only",
            "sourceApi": "/v2.0/tenants/{tenantId}/entitlements/MCSMessages/resources",
            "sourceSchemaVersion": "har-v1",
            "raw": row,
            "importedOn": imported_on,
        }

    capacity: dict[str, dict[str, Any]] = {}
    for row in capacity_rows:
        entitlement = row.get("entitlement") or {}
        capacity_values = entitlement.get("capacity") or {}
        pay_go = entitlement.get("payGo") or {}
        consumed = capacity_values.get("consumed") or {}
        environment_id = str(row.get("environmentId") or "")
        as_of_date = consumed.get("lastUpdatedOn") or imported_on
        rules = capacity_values.get("enforcementRules") or []
        tenant_pool = get_rule(rules, "TenantPool") or {}
        alert = get_rule(rules, "Alert") or {}
        source_key = stable_key(tenant_id, environment_id, "MCSMessages", as_of_date)
        capacity[source_key] = {
            "sourceKey": source_key,
            "tenantId": tenant_id,
            "environmentId": environment_id,
            "environmentName": row.get("environmentName"),
            "name": f"{row.get('environmentName') or environment_id} - {str(as_of_date)[:10]}",
            "entitlementId": "MCSMessages",
            "asOfDate": as_of_date,
            "entitled": ((capacity_values.get("allocated") or {}).get("value") or 0),
            "allocated": ((capacity_values.get("allocated") or {}).get("value") or 0),
            "autoAllocated": ((capacity_values.get("allocated") or {}).get("autoAllocated") or 0),
            "consumed": consumed.get("value") or 0,
            "available": capacity_values.get("availableQuantity") or 0,
            "payGoEntitled": ((pay_go.get("entitled") or {}).get("value") or 0),
            "payGoConsumed": ((pay_go.get("consumed") or {}).get("value") or 0),
            "status": capacity_values.get("status"),
            "drawFromTenantPool": tenant_pool.get("enabled") or False,
            "alertEnabled": alert.get("enabled") or False,
            "alertThreshold": ((alert.get("ruleData") or {}).get("value") or 0),
            "sourceApi": "/v2.0/tenants/{tenantId}/environments/entitlementConsumptions/MCSMessages",
            "raw": row,
            "capturedOn": imported_on,
        }

    all_dates = [row.get("usageDate") for row in usage.values() if row.get("usageDate")]
    file_hash = hashlib.sha256(json.dumps(document, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "tenantId": tenant_id,
        "agents": sorted(agents.values(), key=lambda row: row["sourceKey"]),
        "usage": sorted(usage.values(), key=lambda row: row["sourceKey"]),
        "capacity": sorted(capacity.values(), key=lambda row: row["sourceKey"]),
        "syncRun": {
            "runKey": stable_key("har", file_hash),
            "name": f"HAR credit import - {source_name}",
            "source": "PPAC HAR",
            "startedOn": imported_on,
            "completedOn": imported_on,
            "fromDate": min(all_dates) if all_dates else None,
            "toDate": max(all_dates) if all_dates else None,
            "pageCount": 1,
            "sourceCount": len(resource_rows) + len(capacity_rows),
            "schemaVersion": "har-v1",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har_file")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = Path(args.har_file)
    document = json.loads(source.read_text(encoding="utf-8"))
    payload = build_payload(document, source.name)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "tenantId": payload["tenantId"],
                "agents": len(payload["agents"]),
                "usage": len(payload["usage"]),
                "capacity": len(payload["capacity"]),
                "output": str(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()