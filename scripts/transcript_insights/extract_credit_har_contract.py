#!/usr/bin/env python3
"""Extract a sanitized Copilot credit API contract from a PPAC HAR capture.

The output contains endpoint templates and JSON field shapes only. Request headers,
cookies, response values, tenant IDs, environment IDs, user IDs, and resource names
are never copied to the generated contract.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit


LICENSING_HOST = "licensing.powerplatform.microsoft.com"
TENANT_PATH = re.compile(r"/tenants/[^/]+", re.IGNORECASE)
ENVIRONMENT_PATH = re.compile(
    r"/environments/(?:[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|Default-[^/]+)(?=/)",
    re.IGNORECASE,
)
DOWNLOAD_PATH = re.compile(r"/Downloads/(?!getAll/)[^/?]+", re.IGNORECASE)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _schema(value: Any) -> dict[str, Any]:
    value_type = _type_name(value)
    if value_type == "object":
        properties = {key: _schema(item) for key, item in sorted(value.items())}
        return {
            "type": "object",
            "properties": properties,
            "required": sorted(properties),
        }
    if value_type == "array":
        item_schema: dict[str, Any] = {"type": "unknown"}
        for item in value:
            item_schema = _merge_schema(item_schema, _schema(item))
        return {"type": "array", "items": item_schema}
    return {"type": value_type}


def _schema_key(schema: dict[str, Any]) -> str:
    return json.dumps(schema, sort_keys=True, separators=(",", ":"))


def _merge_schema(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any] | None:
    if left is None:
        return right
    if right is None:
        return left
    if left == right:
        return left
    if left == {"type": "unknown"}:
        return right
    if right == {"type": "unknown"}:
        return left

    if left.get("type") == right.get("type") == "object":
        left_properties = left.get("properties", {})
        right_properties = right.get("properties", {})
        property_names = sorted(set(left_properties) | set(right_properties))
        properties = {
            name: _merge_schema(left_properties.get(name), right_properties.get(name))
            for name in property_names
        }
        required = sorted(set(left.get("required", [])) & set(right.get("required", [])))
        return {"type": "object", "properties": properties, "required": required}

    if left.get("type") == right.get("type") == "array":
        return {
            "type": "array",
            "items": _merge_schema(left.get("items"), right.get("items")),
        }

    alternatives: list[dict[str, Any]] = []
    for candidate in (left, right):
        alternatives.extend(candidate.get("anyOf", [candidate]))
    unique = {_schema_key(candidate): candidate for candidate in alternatives}
    return {"anyOf": [unique[key] for key in sorted(unique)]}


def _json_schema(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        return _schema(json.loads(text))
    except (json.JSONDecodeError, TypeError):
        return {"type": "non-json"}


def _endpoint_template(url: str) -> str:
    parsed = urlsplit(url)
    path = TENANT_PATH.sub("/tenants/{tenantId}", parsed.path)
    path = ENVIRONMENT_PATH.sub("/environments/{environmentId}", path)
    path = DOWNLOAD_PATH.sub("/Downloads/{downloadId}", path)
    query_names = sorted({name for name, _ in parse_qsl(parsed.query, keep_blank_values=True)})
    return path + ("?" + "&".join(query_names) if query_names else "")


def _path_values(url: str, segment: str) -> set[str]:
    parts = [part for part in urlsplit(url).path.split("/") if part]
    return {
        parts[index + 1]
        for index, part in enumerate(parts[:-1])
        if part.casefold() == segment.casefold()
    }


def _safe_report_observations(entry: dict[str, Any]) -> tuple[set[str], set[str]]:
    report_types: set[str] = set()
    report_statuses: set[str] = set()
    request = entry.get("request", {})
    response = entry.get("response", {})

    for text in (
        (request.get("postData") or {}).get("text") or "",
        (response.get("content") or {}).get("text") or "",
    ):
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = [payload]
        if isinstance(payload, dict):
            candidates.extend(payload.get("allDownloads") or [])
            candidates.extend(payload.get("value") or [])
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            report_type = candidate.get("downloadType")
            report_status = candidate.get("fileProcessingStatus")
            if isinstance(report_type, str):
                report_types.add(report_type)
            if isinstance(report_status, str):
                report_statuses.add(report_status)
    return report_types, report_statuses


def extract_contract(document: dict[str, Any]) -> dict[str, Any]:
    entries = document.get("log", {}).get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("HAR log.entries must be an array")

    endpoints: dict[tuple[str, str], dict[str, Any]] = {}
    meters: set[str] = set()
    api_versions: set[str] = set()
    report_types: set[str] = set()
    report_statuses: set[str] = set()
    analyzed = 0

    for entry in entries:
        request = entry.get("request", {})
        response = entry.get("response", {})
        url = request.get("url", "")
        parsed = urlsplit(url)
        method = str(request.get("method", "")).upper()
        if parsed.hostname != LICENSING_HOST or method == "OPTIONS":
            continue

        analyzed += 1
        template = _endpoint_template(url)
        key = (method, template)
        endpoint = endpoints.setdefault(
            key,
            {
                "method": method,
                "endpoint": template,
                "observations": 0,
                "statuses": set(),
                "requestSchema": None,
                "responseSchema": None,
            },
        )
        endpoint["observations"] += 1
        status = response.get("status")
        if isinstance(status, int):
            endpoint["statuses"].add(status)

        request_text = (request.get("postData") or {}).get("text") or ""
        response_text = (response.get("content") or {}).get("text") or ""
        endpoint["requestSchema"] = _merge_schema(endpoint["requestSchema"], _json_schema(request_text))
        endpoint["responseSchema"] = _merge_schema(endpoint["responseSchema"], _json_schema(response_text))

        meters.update(_path_values(url, "entitlements"))
        meters.update(_path_values(url, "capacityTypes"))
        path_parts = [part for part in parsed.path.split("/") if part]
        if path_parts and re.fullmatch(r"v\d+(?:\.\d+)?(?:-alpha)?", path_parts[0], re.IGNORECASE):
            api_versions.add(path_parts[0])
        observed_types, observed_statuses = _safe_report_observations(entry)
        report_types.update(observed_types)
        report_statuses.update(observed_statuses)

    serialized_endpoints = []
    for endpoint in endpoints.values():
        endpoint["statuses"] = sorted(endpoint["statuses"])
        serialized_endpoints.append(endpoint)
    serialized_endpoints.sort(key=lambda item: (item["endpoint"], item["method"]))

    return {
        "contractVersion": 1,
        "source": "Power Platform licensing HAR",
        "host": LICENSING_HOST,
        "entriesAnalyzed": analyzed,
        "coverage": {
            "apiVersions": sorted(api_versions),
            "meters": sorted(meters),
            "reportTypes": sorted(report_types),
            "reportJobStatuses": sorted(report_statuses),
        },
        "endpoints": serialized_endpoints,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har_file", help="Path to a Power Platform admin center HAR file")
    parser.add_argument("--output", help="Write JSON to this path instead of stdout")
    args = parser.parse_args()

    har_path = Path(args.har_file)
    document = json.loads(har_path.read_text(encoding="utf-8"))
    contract = extract_contract(document)
    output = json.dumps(contract, indent=2) + "\n"

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()